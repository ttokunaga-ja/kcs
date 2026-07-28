# Step 4b 完了時 backlog と MVP Done 判定 (2026-07-22)

## 0. MVP Done 判定 (09-mvp-scope.md §4.3)

**Done 条件「synthetic で各シナリオ Recall@10 >= 0.8」を達成** (commit `58cea60` 時点、
fresh corpus / `eval/run_eval.py` 全 3 シナリオ):

| シナリオ (北極星) | Recall@10 | 目標 | p95 | 目標 |
|---|---|---|---|---|
| M3-1 「3ヶ月前の根拠を 5 秒以内に」 | **0.944** (18問) | >= 0.8 | 78ms | < 5s |
| M3-2 「リネーム済み過去版を含めて検索」 | **1.000** (16問) | >= 0.8 | 81ms | < 7s |
| M3-3 「削除したはずの数字を再発見」 | **1.000** (16問) | >= 0.8 | 79ms | < 7s |

履歴網羅ガード (rename 双方向 / deleted / pointer attestation 148 件) 全通過。
テスト 1,123 passed / 0 failed、clippy -D warnings / fmt クリーン。
実装監査 R23 (5 系統パネル) を 1 ラウンド通過 — fatal 0、major 30 件修正済み
(裁定の全記録はセッション作業域 kio-r23/adjudication.md、要旨は `58cea60` コミットメッセージ)。

**残るユーザー側 Done 手続き (実データが必要な 2 点 — 09 §4.1/§4.2)**:
1. M3-1 Q_hard の一回限り増補 (18 → 20 問以上) + 再凍結 (件数と digest を 09 §5.5 #5 行へ追記)
2. 実コーパスでの対 Spotlight (mdfind) / ripgrep-all baseline 比較 (Kio >= 0.8 かつ差 >= 0.3)

## 0.5 実データ fixture での M3-1 増補ゲートと online 実走 (2026-07-23)

**M3-1 合算ゲート PASS: 23/26 = 0.885 >= 0.8** (run_eval 合成 17/18 + qhard 実データ 6/8。
qhard 8 問は測定前に凍結投入 — miss 2 問 (qa02 hard1 / qa07 hard3) は真の困難例として記録)。
実走の要点:
- 登録: 20 人格 400 leaf + qhard 8 leaf、failures 0。pending online 235 = manifest 期待一致。
- batch OCR (裁定 = Batch のみ): 251 task 全成功 (実 API 契約試験を兼ねる — submit/poll/collect/
  upload 削除/token NULL 化まで実機確認)。台帳 $1.17 (pricing 未宣言のため §5.4 estimated 縮退の
  安全側過大 — 実請求は Mistral 側で約 $0.5 以下見込み)。
- 厳密 bijection が **ObjStm 盲目の頁数切り詰めバグを検出** (`1257069` で修正、prepare 1.2.0 /
  markdownize 1.3.0)。登録が炙り出した 2 バグ (`acf4f23`) と合わせ、実データが監査 19 ラウンドの
  盲点 3 つを 1 日で回収。
- embedding (sync): 2,321 task 全成功、$0.0096。検索時 query embedding で hard 自然文が
  vector レーン解答 (run_qhard --online-query)。
- **1-A3 残余追加**: (6) batch reject 後の task 再駆動動線 — reset-violations は台帳のみで、
  invalid_input 化した task の復活が未配線 (fixture では手動 flip で代替した)。(7) built-in
  mistral の tools.toml pricing 宣言ガイダンス (`pages = 0.002`) — 無宣言だと確定記帳が常に
  estimated 縮退で過大計上。
- **baseline 比較を実測 (2026-07-23、`eval/run_baseline.py` + 凍結 24 問 `golden-queries-fixture-b.jsonl`)**:
  Recall@10 = **Kio 8/24 (0.333) / mdfind 0/24 / rga 0/24** (rga は pandoc 導入 + 断片採点の
  上振れ運用でも 0 — Q_hard の設計どおり字句エンジンは全滅)。**差 >= 0.3 は両者に対し成立、
  Kio >= 0.8 の腕が未達 = ゲート OPEN**。クラス別 Kio: hard1 3/8・hard2 5/8・hard3 0/8。
  診断 (実験 = 多様化 off / vector 単独 / text 単独の順位追跡): 候補には入るが**ランキングで
  20 位圏外** — vector 単独でも圏外 (自然文 query と thin 文書 + boilerplate filler 群の
  embedding 近接が answer を上回る)、text は漢字複合断片 (切替判断/時間条件 等) が
  それ以上分解されず不一致。qhard 環境の 6/8 は競合 24 ファイルの小ささによる。
  **次ラウンド = 検索品質 (実データ規模)**: 候補 (a) 漢字複合語の構成語 OR 展開
  (スクリプト境界細分の深化 — FB#2 の延長線)、(b) ファイル名 token の索引/加点、
  (c) fusion 重みと boilerplate 抑制 (df ペナルティ等)。凍結 24 問は変更せず、
  改善は一般規則のみ (golden 過適合禁止) で再測定する。
- **検索品質ラウンド r1 = contextual chunk embedding を実装・実測 (2026-07-24、`451431c`)**:
  chunk の埋め込み入力を `{人間化ファイル名}\n\n{本文}` に変更 (07 §5.3 addendum)。fixture 全
  2,321 chunk を新 profile (`09ff0784`) で再埋め込み ($0.0096)。**凍結 24 問を再測定 = Kio
  9/24 (hard1 4・hard2 1・hard3 4)** — 8→9 の微増、かつ hard2 が 5→1 に**後退**。差 >= 0.3 は
  両 baseline に対し成立継続、`Kio >= 0.8` は依然 OPEN。
  - **診断 (airtight)**: 各解答文書の**スコープ内** vector 順位を測ると、`--all-scopes ヒット
    ⟺ スコープ内順位 == 1` が 24/24 で完全一致。9 ヒットは全て within-rank 1、15 ミスは全て
    within-rank >= 2。contextual 化は within-scope の vector 品質を確かに改善し (解答が
    rank 2〜4 に浮上)、単一スコープ検索・完全一致テキスト検索は正しく解答を rank 1 に返す。
    しかし **`--all-scopes` の cross-scope マージが per-scope RRF の rrf_score (順位由来) で
    プールを整列する**ため、あるスコープの rank-2 は他スコープ約 20 個の rank-1 に必ず負けて
    top-10 圏外に沈む。cosine はプロファイル同一で cross-scope 比較可能なのに順位 RRF が
    その絶対情報を捨てている。
  - **なぜ contextual 化単体では閉じないか**: 事前プレビュー (global file-level max-cosine =
    score ベース擬似マージ) は non-contextual 14/24 → contextual **23/24**。つまり
    contextual 化の利得は「score ベース cross-scope マージ」を前提に初めて顕在化する。
    現行の rank-1-only マージ下では利得がマスクされ、意味の近いファイル名の decoy
    (例: 「修復作業」query に対し `service-restoration.md`) が同スコープ内で解答を rank-2 に
    押し下げると逆効果になり得る (hard2 後退の正体)。
  - **次ラウンド = cross-scope マージの score 化 (05 §1.8)**: vector/hybrid で cross-scope
    プールを global cosine (プロファイル同一で比較可能) で再ランク、または global RRF
    (各 backend の順位をスコープ横断でプールしてから融合)。**カーソル/RRF/MMR の
    決定性契約 (PC8〜PC50・214 本の step3 契約) に触れる spec レベル変更**のため独立
    ラウンドで慎重に設計・検証する。contextual 化 (`451431c`) はその土台として維持。
    測定は `eval/baseline-results-2026-07-24.json`。
- **検索品質ラウンド r2 = cross-scope マージの vector score 化を実装・実測 (2026-07-24、`06e327e`)**:
  05 §1.8 step 3 を改訂 = cross-scope RRF の **vector 項のみ global cosine 順位で振り直す**
  (`regrade_vector_rank_globally`)。text 項は per-scope rank 維持 (BM25 非比較 = CT3-MULTI-002 不変)。
  全 scope は単一 embedding profile を共有 (03 §7) するため cosine は cross-scope 比較可能、という
  原理。決定的・ページ跨ぎ安定 (query vector は R23-01 でバイト同一 replay)。**単一 scope は
  global==per-scope なので振り直さない** (浮動小数 tie-flip 回避) → 既存単一 scope vector テスト不変、
  text-only 不変 → **workspace 1268/0・回帰ゼロ**。単体テスト
  `cross_scope_merge_regrades_vector_term_by_global_cosine` で「scope A rank-2 (高 cosine) が
  scope B rank-1 (低 cosine) を上回る」を basis vector で固定。
  - **凍結 24 問を再測定 = Kio 8→9→**`22/24 (0.917)`** — hard1 8/8・hard2 8/8・hard3 6/8。
    差 >= 0.3 両成立 + `Kio >= 0.8` 達成 = 09 §4.1 baseline ゲート PASS (`gate.pass=true`)**。
    残 2 ミスは hard3 の画像系 (qb23=OCR 抽出不能の画像 husk・qb09)。測定
    `eval/baseline-results-2026-07-24b.json`。
  - **合算 M3-1 ゲートも改善**: qhard `6/8 → 8/8`。synthetic M3-1 (18 問・text-only・本変更の対象外)
    と合算 = 17+8=25/26 >= 21 で PASS 継続 (`eval/qhard-results.json`)。
  - **2 ラウンドの相補性**: contextual embedding (within-scope 品質) + cross-scope score 化
    (絶対 cosine を横断で活かす) の**両方が揃って初めて**利得が顕在化 (プレビュー 14→23 の実機再現)。
- 残るユーザー側 Done: **baseline ゲート充足済み (`22/24`, `06e327e`)**。残 = dogfood (ユーザー実フォルダ)。

## 1. 残余契約 84 件 (QA 65 + QB 19 = P0 45 / P1 32 / P2 7) の選別

棚卸し方法: 契約書の全 ID − crates/ 内の実装参照 (2026-07-22 grep)。ID 一覧は
`tasks/step4b-contract-tests-p3a.md` / `-p3b.md` の該当節。

### 1-A. オンライン Adapter/課金/承認機構 (QA 系の大半) — v1.0 スコープ判断待ち
eval (offline) と北極星 3 シナリオはこれら無しで Done に到達済み。**online 課金運用を
始める前には必須**の層。優先席:
- ~~**安全性直結 P0 (先行推奨)**: QA21/22/25-27/29-31/16-19~~ → **2026-07-22 実装完了
  (`5dba4e5`)**: 送信 gate AND 化 (未設定 = 不成立)・approvals[] の scope.json 移設
  (QA23/24 field 同梱、consents.jsonl は移行せず再承認方針)・`kio adapter revoke` +
  APPROVAL-CONFLICT-001/exit 5 + pending 4 組不問除去 + marker 消費・`--online|--offline`
  4 コマンド配線・AdapterRun error 3 field + usage one-of・pricing 表 + USD 換算。
  toml_edit で config boolean を書式保存書込。Step 2 世代の `ct2_network_004` は 07 §3 (b)
  初回 materialize 例外 (最終規範) に合わせて反転更新。
- ~~**破壊的変更を伴う P0**: QA2/3 (task 状態機械) — 単独ラウンド推奨。**同梱予定の残り 2 点**
  (5dba4e5 で意図的見送り): (1) AdapterRun.retry_after_ms → `next_retry_at` スケジューリング
  結線、(2) 07 §3 のフル crash self-heal (任意コマンドからの pending 完遂 — 現状は revoke の
  pending 除去 + publish 直前 CAS のみ)。~~ → **2026-07-22 単独ラウンドで実装完了 (`ba6de8a`)**:
  auth_error → `Paused(hold_reason=auth)` (解除 = `batch resume`、exit 5 維持)・rate_limit →
  `Pending + next_retry_at` (attempts 非消費、Retry-After 実値結線 + headerless +2s 縮退、
  exit 3 維持)・embedding 選別の Pending `task_retry_due` ゲート追加・auth Paused の再駆動遮断・
  07 §3 self-heal (pending 完全一致の verbatim publish / CAS 競合 = 非発火 / legacy pending
  除去 + marker 消費 / pending 存在中の materialize 抑止)。ledger 演算不変 (auth = settle+clear、
  rate_limit = row open 維持 — r16_7 課金 1 行が生存)。既存テスト 18 本を最終規範へ反転、
  +12 本 (qa2/qa3 ×4・selfheal_01-04・scope 単体 ×4)。1,172/0。
- ~~idempotency key (QA13)、ledger バックアップ/復元 (QA14/15)、orphan 帰属 (QA15)~~ →
  **2026-07-22 実装完了 (`b1a815b`)**: ProviderIdempotency 宣言 (非 identity field) ×
  intent_token 送出の条件分岐 (両 built-in は NotProvided = 縮退 2 相のみ、seam で機構実証)・
  user_version + companion file の復元検知 → KIO-E-BATCH-RESTORE-RECONCILE-001 ゲート
  (Reused 行は通す)・`kio ledger reconcile` 新設 (sync 回復 + batch 回復 walk 初配線 +
  10 §7.5.2 帰属規則の orphan/unknown 逆方向照合、報告のみ・冪等)。既知の残し:
  migrate.rs の JSONL cutover import は write_seq 非 bump (方向安全・一回性の歴史 import)。
- その他: render_params identity (QA34) ほか

### 1-A2. Office 変換層 (棚卸し漏れの未実装要件 — 2026-07-23 発見・同日実装完了 `9f58cab`)
p3a/p3b カタログに変換層本体の契約が無かった (QB27 が sheet 名の角のみ)。要件正本 =
11 §90 / 04 §2 表 (DOCX = 変換 PDF 経由) / 07 §5.1-5.2。**実装済み**: soffice headless 変換
(07 §5.1 追記 = 実装フィードバック枠)・決定論化 (揮発メタデータ同長固定 — 実 LibreOffice
26.2.4.2 で 2 回変換バイト同一を実証)・DOCX→page:N / PPTX→slide:N・offline text-layer 検索・
OCR へ変換 bytes 送出・変換器欠如 = enqueue 抑止 + `office_conversion_unavailable` 可視化・
変換失敗 = contract_violation・**QB41 同梱** (prepared_hash ドリフト → `--yes` 確認付き
offline gen+1。判定は鋳造点ガード 2 枚 = 空 prepare 非判定 + key 集合同一時のみ)。
**残余 (順に優先度高)**:
1. ~~**FlateDecode 展開の決定論抽出器対応**~~ → **2026-07-23 実装完了 (`28a6c6d`)**。
   当初の「`miniz_oxide` 追加が最小構成」は**不正確だった**: 実 PDF (lualatex/soffice) は
   glyph index + ToUnicode CMap + (TeX Live は) `/Type /ObjStm` 格納のため、展開だけでは
   1 文字も読めない。実装 = `kio-adapter/src/pdf_decode.rs` の有界 graph decoder
   (object index + ObjStm 展開 + Page→Font→ToUnicode 解決 + bfchar/bfrange + content-op
   復号、fail-empty で legacy 経路とバイト同一共存、inflate 16 MiB 上限のみ hard error)。
   deterministic profile は 1.0.0→1.1.0 bump (意味論変更 = 新 tool_profile_hash、07 §2.1
   追記 = FB 枠)。実機実証: eval-gen の lualatex PDF (luatexja) が offline 索引され
   `read`/`境界`/`3600` 全ヒット、実 soffice 変換 PDF の抽出アサーション追加。
   テスト 1,237/0・eval 回帰ゼロ
2. QB41 の online 再結線 — enqueue dedup が (input_path, input_hash) キーで新 gen の
   online 再 enrichment を塞ぐ (offline gen+1 は生成済み。online lane の gen 認識は独立変更)
3. PPTX online 往復の専用テスト (offline は office_02、DOCX online は office_03 で被覆済み)
4. 頁数が変わる renderer 更新のドリフトは非検知 (`kio reindex --force` の領分 — ガード (b) の
   意図的帰結)。office incremental は mode=Full 固定 (identity 対応関係が未定義のため)
5. XLSX (sheet 描画意味論 + QB27) / 音声 — 変換機構未定義のまま繰延 (07 §5.1 追記に明記)

### 1-A3. Mistral Batch 送信レーン (2026-07-23 実装完了 `18b9a7f` — 「OCR はバッチのみ許可」裁定の前提実装)
§5.8 台帳状態機械は QA13-15 時点で完全実装済みだったが相 2a/2b の本番 caller はゼロ =
送信レーンだけが未実装だった。**実装済み**: 07 §5.7 の client 契約 8 操作 (実 REST +
hermetic mock seam `KIO_TEST_MISTRAL_BATCH`、実 API 形状は experiments/ocr-verification の
2026-07-03 実測が正)・§5.8 書込順序どおりの submit (1 job = 1 task、metadata 5 key、
custom_id = input_hash、filename = kio-<token>.jsonl)・poll/collect を batch resume + 書込系
preamble 4 箇所に配線 (回収は sync と同一 materialize 経路を共有)・cleanup-first (upload 削除
完了まで intent_token 保持)・bbox 有効 task も batch (bbox 既定 ON のため例外化は裁定の空文化)・
TIMEOUT_EXCEEDED = expired で予約額 estimated 記帳 / FAILED・CANCELLED = 0 記帳。
07 §5.7 に FB 追記。契約テスト 5 本 (submit 順序 / collect+検索 / crash 窓→reconcile found→
回収 / failed 終端 / in-flight exit 3)。テスト 1,260/0・eval 回帰ゼロ。
**残余 (順に優先度高)**:
1. **実 API 契約試験** (provider_scope_id / list_uploads / pagination — 07 §5.2 既記載の
   Step 3 実測分。初回オンライン実行 = eval corpus の batch OCR pass で消化するのが最短。
   v1 の provider_scope_id は `KIO_MISTRAL_WORKSPACE_ID` 上書き + 既定 "mistral:default")
2. incremental Markdownize の batch 化 (v1 は Full 送信へ縮退 — 小差分編集の再 enrichment が
   全頁課金になる。sync 時代の頁 prorate を回復するには collect 側 acceptance の非同期化が必要)
3. batch 出力に埋め込まれた画像の CAS 保存 (sync レーンとの成果物差 — bbox annotation は
   レーン非依存で機能するが、埋め込み画像の evidence 開封が batch 経由分だけ欠ける)
4. tasks.jsonl 喪失時の台帳のみからの persist 回復 (§5.8 の gen 規則再導出) — poll は task
   記述子なし行を skip (reconcile/abandon の領分)
5. 相 2a 着手済み・upload_id 未記録行の list_uploads 照合掃除 (現状 reconcile は報告のみ、
   abandon が脱出路)

### 1-B. QB 残 18 (26/27/34-40/42-48/63-65 — 41 は 1-A2 で消化)
import/export (fork/kioz)・observability 深部・J 領域残。MVP 機能面への影響なし。

### 1-C. 監査で存在が再確認された既知未実装 (backlog 済み)
- **PC33/PC44**: `--all-history`/`--include-deleted` の per-binding ancestry gate (R23 で
  sol/terra 2 系統が指摘 = 実装コメント自認どおり)。遅着 publication の遡及混入を閉じる。
  PC38/PC40 の SQL ゲートは配線済みで、per-binding の呼び出し形だけが未実装。
- PC20 残契機 / PC25/26。

## 2. R23 監査の残件 (fix wave 対象外)
- R23-31 [minor]: human 表示の local TZ 変換 + TTY 色付け (06 §4/§12) — 表示層。
- ledger 形状 migration 本体 (R23-24 は canonical 比較 fail-closed 検出のみ実装 —
  in-place migration は将来の schema 変更時に必要、10 §7.5.3)。
- `fallback_reason` の専用値 `budget_denied` (cap Denied は現在 vec-unavailable 系縮退に合流。
  05 §1.1 enum の拡張判断)。
- log/diff/inspect の cross-marker canonical 共有 (son1 補足 — search/open/view/restore/verify
  は共有済み。実害シナリオ未構成のため優先度低)。

## 3. spec への追記提案 (実装フィードバック枠・未適用分)
1. `kio log --at/--since` の意味論明文化 (p3b Z5 — QB50-58 は確立フラグ意味論からの類推で
   実装済み。06-cli-spec §1 での規範化を推奨)
2. purged 終端 × contract_violation_count の 1 句 (Phase 3 メモ)
3. `kio batch abandon --yes` (非対話運用)
4. ALTER TABLE 系 lint (10 §7.5.3 隣接)
5. 10 §12.1 の BATCH 表へ `KIO-E-BATCH-RESTORE-RECONCILE-001` を追記 (QA14 ゲート —
   CLEANUP-PENDING と同型、exit 1)
6. 06-cli-spec §1 へ `kio ledger reconcile` を追記 (JSON 形状・冪等・network opt-in 不要)
7. 10 §7.5.2 へ復元検知の具体機構 1 句 (PRAGMA user_version 書込カウンタ + `.write-seq`
   companion 照合 — 挙動規範は既存のまま、検知手段の明文化)

適用済み: #1 決定的 query 正規化 (`1c6a55d`) / #2 スクリプト境界細分 + 短語 drop (`d6e8e85`) +
・U+30FB 補正 (`58cea60`) / #3 FTS 有界エスカレーション (`58cea60`)。

## 3.5 Embedding のコスト記帳と Batch レーン (2026-07-24)

**進捗 (2026-07-24 同日)**: #1 #3 は修正済み、#4 は Adapter 層まで実装済み。**残るのは CLI の
enrichment ドライバ (下記「残作業」)** — これが入るまで実効レーンは sync であり、
`active_embedding_send_lane()` が sync を返すことで**記帳は実際に使うレーンの単価**を保つ。

- ✅ `estimate_embedding_cost` をレーン別単価 ($0.20 sync / $0.10 batch) + `tools.toml`
  `[embedding.*.pricing] tokens_in` 優先に変更 (定数 $0.15 = 別モデル価格を撤去)。
- ✅ トークン換算を CJK 対応に変更 (`estimate_embedding_tokens` — CJK 1 文字 1 token、
  その他 4 文字 1 token)。日本語の過少計上を解消。
- ✅ query 用 embedding は**常に sync 単価** (`query_embedding_send_lane`) — 検索は batch の
  turnaround を待てないため。
- ✅ `EmbeddingAdapter::preferred_request_kind()` を追加 (既定 Sync / Gemini は Batch)。
- ✅ `kio_adapter::gemini_batch_client` を新規実装 — `:asyncBatchEmbedContent` (inline 入力・
  **upload 相なし**)、`GeminiBatchClient` trait / `EnvGeminiBatchClient` / hermetic mock
  (`KIO_TEST_GEMINI_BATCH`)、inline 上限の局所強制、`displayName` への intent_token 埋め込み。
  単体 16 本 green。
- ✅ 07 §5.3 に「Vertex はバッチ推論非対応」の**根拠訂正**とレーン契約を追記。

**残作業 (CLI ドライバ)**: `run_embedding_enrichment` を「submit して返る」形にし、
`kio batch resume` に embedding の poll/collect を追加する。相 1 / 相 2b / 相 3 は
`batch_requests` (adapter_kind 汎用・schema 変更不要) をそのまま使う。
着手前に**既定レーンの裁定**が必要 — 下記 §3.5.1。

### 3.5.1 既定レーンの裁定 (2026-07-24 確定)

**案 B — Batch 既定 + 明示 opt-in の即時レーン**。追加の裁定 2 点:

1. **OCR と embedding は必ず同一レーン。** 片方だけ Batch という組み合わせは作らない。
   したがってレーンは adapter 単位ではなく **invocation 単位で 1 つ**決まる。
2. **即時性の指定に `--online` を流用しない。** API 経由である以上 online は前提であり、
   `--online` は「送ってよいか」(network opt-in)、新引数は「いつ返ってくるか」(turnaround)。
   → **`--realtime`** を新設 (`index` / `batch resume` / `batch retry`)。

これは 2026-07-23 の「OCR 課金は Batch レーンのみ」を**明示的に上書き**する
(既定は従来どおり Batch のみで、倍額は明示 opt-in でしか発生しない)。

**実装済み (2026-07-24)**: `--realtime` 引数 3 コマンド / invocation lane
(`effective_invocation_lane`) / `markdownize_send_lane` のレーン上書き (飛行中の batch 行は
乗り換えない) / OCR 予約見積りの倍額化 / 07 §5.3 + 06 §1 への規範追記。単体 4 本追加。

**残 = embedding の CLI ドライバのみ**。これが入った時点で `active_embedding_send_lane()` を
`effective_invocation_lane()` へ差し替える (それまでは実効 sync のままにして記帳の正確性を保つ)。

以下は判明した事実の記録 (裁定の入力)。

## 3.5-old Embedding のコスト記帳 (2026-07-24 追加 — dogfood 索引化計画の調査で判明)

根拠と再現は [dogfood-index-phase-plan.md §6](dogfood-index-phase-plan.md)。公式ドキュメントで
`gemini-embedding-2` = 標準 $0.20/1M text・**Batch $0.10/1M (50% off)** を確認済み。

1. **[P1] 単価定数が別モデルの価格** — `estimate_embedding_cost()` (`kio-cli/src/main.rs:14651`)
   は `$0.15/1M` をハードコードしている。これは `gemini-embedding-001` の価格で、
   Kio が pin する `gemini-embedding-2` は $0.20/1M。**25% 過少**。
   `tools.toml [embedding.*.pricing] tokens_in` は読まれないため設定では直らない。
   03 §11 の設定例 (`tokens_in = 0.00000015`) も同じ誤り。
2. **[P1] 見積りがそのまま確定記帳になる** — `:batchEmbedContents` の応答にトークン数が無く
   adapter は `usage: None` を返す (`gemini_embedding.rs:437-441`)。したがって cost_ledger に
   載るのは実測ではなく見積りで、provider 側と突合できる数値が存在しない。#1 と合わさり
   **budget cap が守る対象の金額自体が系統的に過少**になる。
3. **[P2] `chars / 4.0` のトークン換算が日本語で成立しない** — dogfood コーパスの正規化
   Markdown (936,873 文字) は CJK 9.3% で既に約 1.28 倍の乖離。OCR 後は日本語比率が上がる。
4. **[P2] embedding に Batch レーンが無い** — `PreferredRequestKind` は `MarkdownizeAdapter`
   のみ (`traits.rs:40-44`)。07 §5.3 の根拠は「Vertex はバッチ推論非対応」だが、実装先は
   Vertex ではなく Gemini API (`generativelanguage.googleapis.com/v1beta`) で、そちらには
   embeddings 対応の Batch API がある (`client.batches.create_embeddings()`、24h)。
   **根拠と実装先が食い違っている**ので、まず 07 §5.3 の記述を実装に合わせて訂正する。
   レーン実装自体は金額効果が小さい (dogfood 規模で差 $0.1–0.4) ため優先度は低い。

## 3.6 CLI 引数の整理 (2026-07-24 完了)

引数の軸が混線し、8 コマンドが `--help` に何も出さない状態だったため A/B/C 一括で整理した。

**A — 自動化の穴**
- `[adapter] lane = "batch" | "realtime"` を config へ新設 (`config.schema.json` / 03 §11)。
  解決順は network opt-in と同形 = **CLI > scope config > user config > 既定 (batch)**。
  毎回 `--realtime` を打つ必要がなくなった。
- 逆向き上書きの `--batch` を新設 (`--online/--offline` と同じ対称形)。
- online 送信を駆動する全コマンドへレーン引数を伝播 — `repair --rebuild-db` / `reindex` が
  受けていなかった (「両方バッチか両方即時」の裁定を表明できない穴だった)。

**B — `--help` が機能していなかった問題**
- `repair` / `search` / `open` / `view` / `gc` / `reindex` / `move` / `evidence` の 8 コマンドが
  `UnsupportedArgs` (`trailing_var_arg`) で受けて手書きパースしていた。**clap 宣言へ全面移行**。
  `search` 16 / `repair` 10 / `reindex` 7 個の引数が help に出るようになり、打ち間違いも検出される。
- 手書きパーサ 3 本 (`parse_search_args` / `parse_repair_args` / `historical_reindex::parse_args`)
  と補助 4 本 (`split_flag_value` / `reject_inline_value` / `flag_value` / `without_json`) を削除。
- `--json` を raw operand から拾い直す `command_captured_json_flag` も不要になり削除
  (clap の `global = true` が全コマンドで効く)。
- **回帰を 1 件検出**: 移行時に PC59/PC60 (`--at` は単一 `--scope` 必須) と
  `TimeSelectorFlags::canonicalize` の検証が落ちたが、既存の契約テストが捕捉して復旧済み。

**C — 語彙の整理** (**Stable 前のため alias は残さず旧名は削除**。呼び出し側は全て更新済み)
- `reindex --force` → **`--regenerate`**。`restore --force` = 出力先の上書き、という別軸の
  同名衝突を解消。旧名は削除 (`reindex --force` は usage error)。
- `search --text|--vector|--hybrid|--no-vector` → **`--mode <auto|text|vector|hybrid>` 単独**。
  1 つの enum を 4 boolean で表していたのをやめ、config の `[search] default_mode` と 1 対 1 にした。
  値を取るフラグになったため「boolean への inline value」の危険自体が構造的に消えた。
- `repair` の 3 操作は **sub-command 化** (`kio repair rebuild-db|verify-objects|registry-prune`)。
  exactly-one と入れ子 (`--prune-orphans` は verify-objects の下、online/offline・realtime/batch は
  rebuild-db の下) が**構造で保証**され、手書きの排他・入れ子検証を全廃した。
  clap の `requires` が `ArgAction::SetTrue` で効かない (sibling が既定値で常に present 扱い)
  問題も、sub-command 化で回避される。
- **死んでいた `repair --yes` を削除**。06 §1 の確認プロンプトが未実装でスキップ対象が存在せず、
  受理して何もしない引数だった。プロンプト実装時に改めて追加する。

**意図的な挙動変更 2 件**
1. 引数の重複指定が「may be specified once」エラーではなく last-wins になった。clap 宣言済み
   コマンド (`index --online --online`) は元々受理していたため、**不一致の解消**であって新たな
   不整合ではない。R12-7 (`--flag=value` 受理) と R16-6 (boolean への inline value は usage error)
   は clap 側で維持される。
2. 旧フラグ名は**互換 alias を残さず削除**した (ユーザー裁定: Stable 前で破壊的変更を許容)。
   契約テスト・仕様書 (`docs/02-10`) の呼び出しは全て新名へ更新済み。
   `tasks/exploratory-audit-runbook.md` 等の**過去の監査記録は当時の名前のまま残す** (履歴の改竄になるため)。

**残る確認プロンプト未実装**: 06 §1 は `repair verify-objects --prune-orphans` と
`repair registry-prune` に確認プロンプトを要求しているが実装が無い。`--yes` は削除したので、
プロンプト実装時にセットで追加する。

検証: 1,301 tests green / clippy clean / fmt clean。

## 4. eval 由来の既知残余
- M3-1 の 1 問 (英語 query 「vector database managed pricing around 0.12 dollars per million
  vectors」 vs 日本語本文) — 固定 5 語対訳辞書の範囲外で一致 unit が `0.12` のみ。ゲート非阻害
  (0.944)。辞書拡張は feedback #1 の枠内で可能だが golden 過適合と表裏。
- 上記 §0 のユーザー側 Done 手続き 2 点。

## 5. 監査運用の学び (R23)
- glm-5.2 は巨大ファイル探索型監査で wal 267,832 バイトの同一点凍結を 2 連続 — 打ち切り。
  glm は文書埋め込み型 (パス渡しでなく `--file`/本文貼付) 専用に戻す。
- codex fatal インフレは実装監査でも健在 (fatal 10 → 確定 0)。反証はコード読解でなく
  **実機再現** (purge → 復活 → search) が最短だった。
- Sonnet は「指摘ゼロ地帯の確認声明」+「反証」で価値を出す (son1 の canonical 反証が
  codex 2 系統の fatal を落とした)。

## 6. R24 / R24b 監査の残件 (2026-07-25)

裁定の全文は [r24-audit-adjudication.md](r24-audit-adjudication.md)、
各系統の報告書は [audit-reports/](audit-reports/) に退避してある。
**修正済み 6 件は本節に載せない。** 以下は認容したが未修正の分。

### 6.1 `repair` の破壊的操作 — preview が本実行を拘束しない → **修正済み (2026-07-25)**

R24b で 3/3 系統一致、うち 2 件が fatal だった **H2-3 / H2-4 / H2-5 / H2-6 は解消済み**。
`prune_orphans` / `registry_prune` を **plan / apply に分割**し、apply は plan に載った対象しか
触らない。確認プロンプトは対象を列挙する (先頭 20 件 + 残数)。blocked の JSON には
`KIO-E-PRUNE-ORPHANS-BLOCKED-001` が載る。

**`repair` の破壊的実行を避ける必要はなくなった。**

不変条件は単体テスト `apply_removes_only_what_the_plan_listed` が固定している
(preview 取得 → **新しい orphan を作る** → apply → 新しい方は残る)。

### 6.2 その他の認容分

| ID | 内容 | 一致 |
|---|---|---|
| F5 | batch client 不可時に OCR=Batch / embedding=Sync とレーンが分裂する (ユーザー裁定「両方バッチか両方即時」違反) | 2/6 |
| F6 | 1 job のメンバ数を 512 固定で切っており、inline 20MB 上限を**サイズで**守っていない | 1/6 |
| F7 | 飛行中行の profile と現在 profile の一致を collect 時に確認していない | 2/6 |
| F8 | 未知の provider state を永久に in-flight 扱いする | 1/6 |
| F9 | `list_jobs` の 5,000 件打ち切りで §5.8 回復走査が取りこぼしうる | 1/6 (要調査) |
| G1 の派生 | Gemini job は task_key を持たないため、逆方向の orphan 走査では常に `unknown` 止まり (upload と同じ report-only 姿勢)。帰属は intent_token で成立するので実害は無いが、将来 metadata を運べるようになったら task key 4 組を載せる | — |
| F10 | `active_embedding_send_lane` の doc コメントが「driver は未着手」のまま陳腐化 | 3/6 |
| H2-7 | reachability 読取り失敗を無視し、参照中オブジェクトを orphan 扱いしうる | 1/3 (要調査・fatal 候補) |
| H2-8 | 契約テストが `registry-prune` の拒否経路を網羅していない (列挙・拘束・blocked は §6.1 で充足) | 3/3 |

## 7. Phase 2 canary が実 API で検出した欠陥 (2026-07-25)

**7 系統の静的監査も 13 本の契約テストも通り抜けた**。いずれも実 API へ 1 scope 投げた
時点で即座に露出した。詳細と正本は [07-adapter-spec.md §5.3](../docs/07-adapter-spec.md) の
「実物の wire 形」訂正ブロック。

### 7.1 修正済み (2026-07-25)

| ID | 内容 | 影響 |
|---|---|---|
| I1 | `parse_inlined_results` が実応答の**二重ネスト** `inlinedResponses.inlinedResponses[]` を解決できない | **実 job が 1 件も回収できない。** 終端した job が診断なしで永久に in-flight。G2 の「その行だけ保持」規則がエラーを飲み込むため無症状 |
| I2 | `list_jobs` が一覧キーを `batches` で読む (実物は `operations`) | 回復走査の inventory が**常に空**。相 2b 中断行が恒久に宙吊り |
| I3 | モック seam が `{"inlinedResponses": [...]}` という**実 API が返さない形**をパーサへ直接与えていた | I1/I2 を契約テストで検出できなかった原因。`list_jobs` も封筒を迂回していた |
| I5 | `get_job` が poll 応答を **metadata 級 (1 MB)** として読む。実際は `GET /v1beta/{name}` が唯一の endpoint で、成功した job の応答は**全 inline 結果を 2 重に**載せる (実測 47,905 B/member) | **メンバ数に比例して踏む。** p01 の 33 メンバ job が 40 回のポーリングで一度も回収されず、provider 側には全ベクトルが揃っていた。小さい scope では通るため規模を上げるまで出ない |
| I6 | 「読めなかったので保持」が `tasks_inflight` に混ざり、**正常な待機と区別できない** | I1 と I5 の両方をこの沈黙が隠した。`tasks_inflight_unreadable` を追加し、保持理由を stderr に出す |
| I7 | **XLSX が黙って pending のまま滞留する。** task は `status: pending` / `fallback_reason: "network_opt_in_required"` (opt-in 済みでも変わらない) のまま残り、`unsupported_inputs: []` ・ `task_errors: []` ・ `tasks_complete: true` が異常なしと報告していた | ユーザー裁定 (2026-07-25) = **案 B: PDF 変換を経ずローカルで直接抽出**。07 §5.1 の「対象外」を解除し `kio_adapter::xlsx_extract` を実装。読めない workbook は `KIO-E-PREPARE-XLSX-EXTRACT-001` で落とす (空成功にしない) |
| I4 | 応答の `usageMetadata.promptTokenCount` を捨てており、embedding は常に `estimated=1` で記帳される | 台帳が実額を映さない。`GeminiBatchEmbedOutput` に token 数を載せ、全単射が成立し全行が usage を報告した時だけ `estimated: false` へ移す。**全単射不成立・usage 欠落・一部行のみ報告の 3 経路は予約見積りへ退避** (部分合計は静かに過少になる)。実 API で検算: 853 tokens × $0.0000001 = $0.00008530、`estimated=0` 一致 |
| I8 | `get_job` と `fetch_inlined_results` が**同じ URL を 2 回叩く** (成功 job では 1.5 MB を二重にダウンロード) | 上限が分岐したのはこの構造が原因。`poll_job` が 1 回取得して record と results を同時に返す形へ寄せ、I5 の再発経路自体を消した |

修正: 封筒解決を `batch_object` / `parse_job_listing` / `inlined_response_lines` に集約し、
**モックを provider と同じ封筒へ通した**。採取した実応答そのものを固定する回帰テスト 4 本
(`real_poll_response_*` / `real_listing_response_*` / `the_documented_listing_key_is_still_accepted`)。

I4 と同時に、確定記帳の**レーン非対応**も塞いだ。両記帳経路が `registered_declared_pricing`
を素で読んでおり、markdownize は宣言値がたまたま Batch 単価だったため batch でだけ正しく見えて
いた — **`--realtime` の OCR は実額の半分で記帳されていた**。過少記帳は budget cap が構造的に
防げない方向 (cap は小さい方の数字しか見ない) なので、`lane_adjusted_pricing` を単一の適用点に
統一した。

### 7.2 未修正

| ID | 内容 |
|---|---|
| I21 | **replica の更新を「読み手が検知する」から「書き手が伝える」へ (write-through、ユーザー裁定 2026-07-25・実装完了)。I20 の同型欠陥があと 3 つ埋まっていた。** ユーザーの問い「読み取りはそもそも必要ですか？トランザクション性を維持して、各フォルダの Kio への新規登録と同じ処理内でグローバル APP 配下にも Insert すれば処理漏れは発生しないのでは？」に対し、方式 B (別 transaction + generation スタンプを commit marker) / 全 8 経路 を裁定。<br>**I20 の修正 (回転を足す) では足りないことが実装調査で判明した。** 回転は**コマンドの上端**にあり、順序・早期 return・条件分岐に晒される。実際 `run_batch` は `poll_batch_embedding_jobs` (I20 で回転を追加) を **10654 行で呼び、その後 10690/10769 で `execute_pending_tasks` → `run_embedding_enrichment` (同期レーン、回転なし) を走らせる** — 回転を足しても後段の書き込みは取りこぼす。同型の未検出経路は計 3:<br>  ① **同期レーンの埋め込み** (`--realtime`、および `batch resume` 内の enrichment) — `chunk_vec` に in-place 書き込み、回転なし<br>  ② **内容アドレス再利用の link** (`link_reused_chunks`、API 呼び出し無しの dedup ヒット) — 同上。Batch 送信経路にも同じ再利用があり、こちらは早期 return する<br>  ③ **`reindex --at <commit>`** (`historical_reindex::project_selected_snapshot`) — live `sqlite.db` を temp+rename 無しで開き **`chunks` 本文を投影**して回転しない。**ベクタではなく本文が丸ごと corpus から欠ける**、3 つで最も重い<br>**修正 = write-through を呼び出しグラフの下端に置く。** `persist_group_vector` は両レーンが共有する唯一の書き込み点、`rebuild_sqlite_index` の rename は再構築 3 コマンドが共有する唯一の入れ替え点。書き手が知っていることを書き手が伝えるので、検知の積み残しが原理的に生じない。全置換 (`refresh_scope`) = 再構築・`reindex --at`・purge / 差分 (`apply_delta`) = `chunk_vec` だけ触る経路。差分はパス全体で溜めて末尾で 1 回流す (dogfood fixture で 2,321 group、group ごとに別 DB の transaction を張るのは無駄)。<br>**副次的に見つかった安全性の穴 2 つ**:<br>  (a) **purge が replica の本文を消していなかった。** replica は chunk 本文を持ち cache root に居る。回転が次の検索に再射影させるので*順位*は自然に直るが、**誰も検索しない間、purge した本文が device の cache に読める形で残る**。本文を消すのが purge の目的そのものなので、purge 成功時に全再射影を追加した (05 §3.5 の「消すもの」にも明記)<br>  (b) **差分が「replica に無い scope」にスタンプを押すと危険。** 差分は変化分しか運ばないので scope を新規に作れず、それでスタンプだけ押すと**一度も複製されていない本文について「最新」と検索に告げる**。`apply_delta` は scope 不在なら何も書かず `false` を返す (単体テストで固定)<br>**秘匿の連鎖も塞いだ**: `link_chunk_vecs_to_content_vector` / `link_chunk_vec` の戻り値を「件数」から「実際に link された chunk_id」へ変更。R20-10 の secrets hold と width 不一致は**この 1 箇所で判定される**ので、replica が `held` を自前で再評価する形にすると、両者が乖離した日に **hold 中の chunk が vector 検索へ露出**する (03 §4 不変条件 8)。replica は結果に従い、規則を複製しない。<br>**契約テスト**: `ct3_multi_013` (索引しただけで両 scope が replica に載り、検索前に単一コーパスの BM25 が両 scope をまたぐ) — hook を外すと `left: 0 / right: 2` で落ちることを確認済み。`ct3_multi_010` は「単一 scope 検索は replica を作らない」から「**replica があっても単一 scope 検索は再ランクされない**」へ意味を修正 — scope は自分が単独かを知り得ない (`kio index` は 1 つの `.kio` の中で動く) ので、write-through を条件付きにすると 2 つ目の scope が現れた瞬間に 1 つ目が欠ける。<br>**未解決 (cursor 契約単独)**: 同期レーンと `reindex --at` は順位を変えうるが回転しない。replica 側は write-through で塞がったので、残るのは LC25 の outstanding cursor 無効化のみ |
| I20 | **replica の staleness 検出が `batch` レーンの埋め込みを取りこぼしていた (I19 Stage 1 が開けた穴・修正済み)。** ユーザーの「読み取りは要るのか / write-through すれば漏れないのでは」という問いを検証する過程で発見。<br>`kio batch resume` / `collect` は `persist_group_vector` で **live index の `chunk_vec` に直接ベクタを書く**が、`run_batch` は `run_index`/`run_reindex` と違い**索引を再構築しない** (2 段まで呼び出しを追って確認)。`index_generation` が変わるのは (a) 再構築が新しい temp DB に `ensure_index_metadata` で新 ULID を入れる経路と (b) lifecycle/purge の `rotate_index_generation` だけなので、**batch 回収後もスタンプは埋め込み前のまま**だった。replica はこのスタンプ 1 本で staleness を決めるので、**回収したベクタが永久に replica へ届かない**。既定 hybrid の順位が静かに劣化する。<br>影響が今回の dogfood 計測に出なかったのは、replica を**全 enrichment 完了後に**作り直したため初回射影がベクタを見ていたから。**「動いている」ことが検出器の正しさを意味しない**典型。<br>修正 = `poll_batch_embedding_jobs` の末尾で、実際に persist した場合だけ `rotate_index_generation_unconditionally`。LC25 の「outstanding cursor を無効化しうる変更では回転する」規範にも合致する (ベクタが増えれば順位は変わるので、cursor は retire されるべき)。no-op poll では回転しない。<br>**学び**: cache の鮮度キーは「正本のどの変化で動くか」を経路ごとに数えること。I19 は `index_generation` を「あらゆる索引変更で回転する」と要約したが、**実際には再構築と lifecycle の 2 経路でしか動かない**。要約を実装で検算していなかった |
| I19 | **横断検索を scatter-gather から replication へ変更 (ユーザー裁定 2026-07-25)。Stage 1 完了・Stage 2/3 未着手。** 経緯: I17 の調査中に「per-scope sqlite の情報を APP 配下 DB へレプリケーションして一括検索・権限管理する想定」だったことが判明。**docs はそう書いていなかった** — `aggregator` の記述は全 8 箇所すべて「**将来の** global aggregator は検索キャッシュ・発見補助に過ぎない」の 1 文の反復で、役割も「探索対象一覧 / stale 検出 / UI 統合」に限定されていた。git 履歴でも初出コミット `1491910` から 4 世代すべて同一文言で、replication を記述した版は存在しない。逆に 05 §1.8 は「各 `.kio` は独立した index を持つため」の scatter-gather を明記し、**「text backend の rank は per-scope のまま融合する」= I17 で直した欠陥そのものを規範として要求していた**。<br>**spec 変更**: 05 §1.8 の実行モデルを replication へ / 旧規範 CT3-MULTI-002 を撤回 (fallback 経路にのみ残存) / 03 §4 に不変条件 6-8 を追加 (**6** aggregator は安全性判定の最終権限を持たない・**7** liveness 判定を再実装せず解決済み集合だけ持つ・**8** 権限の書き込みは常に `.kio`) / SQLite ファイル 3 → 4 / 05 §1.9 に権限の横断管理 / 01・10・README の二層構造から「将来の」を除去。設計書 = `tasks/aggregator-design.md`。<br>**実装 Stage 1**: `kio_index::global_text` → `kio_index::aggregator` (`$XDG_CACHE_HOME/kio/aggregator.sqlite`、4 表)。text だけだった replica に **vector** を追加し、**両レーンの rank を単一コーパス上の global rank に統一**。`regrade_vector_rank_globally` は fallback 専用に降格。vector は `chunk_vec` から射影する — `embeddings` から引くと 07 §5.3 の contextual 選択を再実装することになり、不変条件 7 と同型の重複になるため。<br>**実測 (428 scope / 3,851 chunk / 3,851 vector)**: hybrid **rank1 7 → 8・top5 22 → 24**、text/vector は不変。改善分は「vector 順位が *候補プール*の順位から*コーパス全体*の順位になった」効果 — 旧 `regrade_vector_rank_globally` は fan-out が返した候補の中でしか順位を付けられず、どの scope の local top-N にも入らなかった chunk は順位を持たずに他候補の順位をずらしていた。<br>**性能は変わらない (1.20 秒 → 1.19 秒)。** Stage 1 では候補取得の fan-out が残るため。**この 1.2 秒はほぼ全部 428 scope を開くコスト**であり、Stage 3 (replica が候補も返す) まで行かないと縮まない。⚠️ 途中で「fan-out は 0.02 秒」と報告したが**誤り** — `not a kio scope` のエラー経路を計測していた。scope 外の cwd から `--json search` は exit 0 でエラー JSON を返すので、時間だけ見ていると成功に見える。**計測は必ず出力を確認すること。**<br>**実装中に自分で開けた穴を 1 つ塞いだ**: `retain_scopes` を `searched` で駆動したため、`--scope`/`--descendants` の絞り込み検索が**触れなかった scope を replica から全消し**していた (実測 3 scope → 2)。narrowed search は collection を*読む*のであって*定義し直す*のではない。prune は all-scopes 検索に限定した。契約テスト `ct3_multi_012` はガードを外すと実際に落ちることを確認済み。**「fix が開けた穴」の定番脈がここでも出た** — I17 の fix (global 索引) が持ち込んだ prune が、別の入口 (scope 絞り込み) を壊していた。<br>**残り**: Stage 2 = `agg_approvals` の追加と横断コマンド (**表ごと未作成** — 読み手のいない列・表は置かない方針)。Stage 3 = replica が候補選択も担い、安全性再確認 (05 §1.8 手順 3) を実装する。**手順 3 は Stage 1 では per-scope 経路が候補を出す以上すでに満たされている**が、Stage 3 で replica が候補を返し始めた瞬間に必須になる。**spec は Stage 3 の姿を書いており、現状の実装より先行している** — この乖離自体が I17 で批判した「コメントが前提を書きながら実装が破る」形なので、Stage 3 完了まで本行を未修正欄に置く |
| I18 | **`.kio` をフォルダごとコピーすると store が壊れて索引できない。再 OCR 回避という設計意図が、絶対パス 1 箇所で成立していない。** 実測 (2026-07-25): 実コーパスの 1 scope を `cp -R` して別 XDG 環境で `kio index --yes` → **`KIO-E-STORE-CORRUPT-001`** で即死。原因は `tasks.jsonl` の `output_ref` が**絶対パス** (20 行中 3 行) で、コピー先から見ると元 `.kio` を指すため `validate_task_output_ref` (`kio-pipeline/src/task.rs:861`) が弾く。生成元は `normalized_output_ref` (`main.rs:18288`) で、`repo.kio_dir()` を `display()` してそのまま格納している。<br>**CAS 層自体は正しく可搬**: `tasks.jsonl` を外すだけで `indexed` が通り、chunks 17 / embeddings 16 がそのまま残り、**ネットワーク無し・API キー無しで OCR 済み本文が検索できた** (「障害切替を承認した閾値は 17 分。」がヒット)。成果物は `.kio/objects/normalized/<raw_hash>.<tool_profile_hash>.g0.md` に content-addressed で載っており、フォルダコピーで確かに運ばれている。**壊しているのは tasks.jsonl だけ。**<br>しかも 03 §4.1 は tasks.jsonl を「**喪失許容の JSONL**」と定めている — 失っても良いはずのファイルが store 全体を fail-closed で落としている。<br>修正 = `output_ref` を `.kio` 相対で格納する (validator は現行のまま通る)。移行は「絶対パスで `.kio` 配下に解決できる行は相対へ読み替える」で足りるが、**後方互換不要の段階なので単純に相対化してよい**。併せて、可搬性の契約テスト (copy → index → search がネットワーク無しで通る) が 1 本も無いことも塞ぐ |
| I17 | **RRF が per-scope の text rank と global の vector rank を同一スケールで加算していた。既定の hybrid が vector 単独に全指標で負けていた。** Phase 3 の 32 契約実測 (2026-07-25): rank1 **hybrid 6 vs vector 14**、top5 **21 vs 30**、発見 **27 vs 30**。しかも**劣化は OCR と埋め込みが可能にしたクラスに集中**していた (hard1 は vector 12/12 top5 に対し hybrid 8/12)。$1.21 かけて到達可能にした文書が既定モードで沈むという、最も避けたい形。<br>**原因は RRF の性質ではなく実装**。`fuse_rrf` 自体 (rrf.rs) は教科書どおり正しい。壊れていたのは `regrade_vector_rank_globally` の再融合 (main.rs:1978-1986) で、`vector_term` は **global** cosine rank、`text_term` は **per-scope** BM25 rank を使い、それを加算していた。実測で分解: hybrid #1 = `1/61 + 1/130` = 「自フォルダで text 1 位」+「global vector 70 位」= 0.024085、正解 qa01 = `1/61` のみ = 「**global vector 1 位**」= 0.016393。**「6 チャンクのフォルダで 1 位」が「3,851 チャンク全体で 1 位」と同額**で、428 scope あるのでそういうチャンクが最大 428 個できる。検算: `w_text = 0` にすると正解のスコアは 0.016393 のまま**順位だけ 38 → 1** — 正解は何も変わらず、上に 37 個の per-scope 項が積まれていただけ。<br>コメント自身が前提を書いていた — 「`text_rank` stays per-scope (**BM25 is not cross-corpus comparable** — CT3-MULTI-002)」。**比較不能と明記した上で、比較可能な項と足していた。** per-scope で保持すること自体は妥当で、global 項との加算で破綻する。<br>**ユーザー裁定 = 方針 A (text も global rank へ揃える)。** 手法調査の結論: 「複数コーパスがある限り BM25 は比較不能」なので、**コーパスを 1 つにする**のが唯一恣意性ゼロの解 (分散 IR の古典解、Elasticsearch の `dfs_query_then_fetch` と同じ問題・同じ答え。ES 側も「各シャードが 1〜2 文書しか持たないとスコアが不正確」と明記しており、**428 scope・中央値 6 チャンクはその最悪ケース**)。per-scope Min-Max (Weaviate/OpenSearch の Relative Score Fusion) は**この問題には不適** — 母集団の大きさの差を正規化で消すので症状が残る。Bayesian BM25 (Jeong 2026) は「BM25 とベクタのスコアをどう足すか」には効くが scope 横断問題は解かない。<br>**実装 = `kio_index::global_text`**: `$XDG_CACHE_HOME/kio/global-text.sqlite` に全 scope の chunk を 1 つの FTS5 として持ち、`bm25()` を corpus 全体で計算する。正規化関数もチューニング定数も無い。**この索引は候補を返さない** — 統計と採点のみを供給し、候補選択と liveness 判定は per-scope 経路に一本化 (liveness 述語を 2 箇所に複製すると必ず乖離する)。更新は `index_generation` 比較の遅延方式。**開けない・読めない・採点できない各経路は per-scope 順位のまま続行**し stderr に理由を出す (実際この経路は開発中に発動し、検索は正常に応答し続けた)。<br>実測: 428 scope・3,851 chunk のキャッシュ構築 3.0 秒、**qa01 は 38 位 → 7 位**、hybrid の発見 **27 → 30/32** で vector 単独と並んだ。text 単独も rank1 1 → 3 に改善 (同じ欠陥が text の横断順位にも効いていた)。<br>**残る限界**: hybrid は依然 vector 単独に及ばない (rank1 7 vs 14)。両項が global になっても **RRF は「テキストで見つかるはずのない文書」に 1 項しか与えない** — hard1/hard3 は語彙の重なりがゼロになるよう作られているので構造上テキスト項を得られない。これは実装の不備ではなく RRF がそのケースを想定していないという設計の限界で、対処は別軸 (片レーン専用文書への補正 / enrichment 済み device での既定モード / Cross-Encoder 再ランク — 上位に入るようになった今なら意味を持つ) |
| I15 | **到達不能な scope が 1 つあるだけで、device 全体のベクタ経路が落ちる。しかも報告される理由が原因と違う。** Phase 3 受け入れ検証 (2026-07-25) で実測: 実装検証用に `mktemp -d` で作って索引化し `rm -rf` した一時 scope 3 件が registry に残っていた (431 登録中 3 件)。結果、**428 scope 分の埋め込みが 1 件も使われず**、全 32 契約が text へフォールバックした。除去したら復旧。**この状態で 1 度、測定を丸ごと無駄にした** (text と hybrid が同一の 6/32 になり、あやうく「埋め込みは効果なし」と結論するところだった)。<br>**同じ scope について 2 つの機構が食い違っている**: (1) `resolve_vector_availability` → `scope_embedding_state` は `sqlite.db` が無ければ `Absent` (main.rs:1592-1594)、そして `any_compatible && any_absent` で device 全体を `Incompatible` に倒す (main.rs:1668)。(2) `search_one_scope_inner` は `Repository::open_for_search` の失敗を `Excluded("unreachable")` にして**その scope だけ飛ばして検索を続行**する (main.rs:3462-3466)。**(1) が先に走って経路を殺すので (2) は出番が無い。** 実際 `--mode vector` は `excluded_scopes: [{reason: "unreachable"}]` を返して正常に検索できるのに、`--mode hybrid` / `auto` は同じ状態で全滅する — **モードによって同じ事実の解釈が違う。**<br>設計意図 (PC52) は「部分的にしか埋め込まれていない device で hybrid を返すと結果が偏る」で、それ自体は正しい。だが**「削除された scope」は中身がゼロなので偏りを生まない** — 「chunk はあるがベクタが無い」と「そもそも存在しない」を `Absent` 1 語に畳んだのが原因。<br>加えて **`fallback_reason` が `embedding_profile_incompatible`** になる。`VectorAvailability::Incompatible` が profile 不一致と absent の両方の受け皿なので、**到達性の問題を profile の問題として報告する** — 私はこれで原因究明を誤らせられた。<br>修正案: `scope_embedding_state` に `Unreachable` を足し、device 判定では `any_absent` に数えず (2) と同じく除外扱いにする。`fallback_reason` は原因別に分ける。registry の陳腐エントリを剪定する経路 (`last_seen_at` は既にある) も別途要る |
| I16 | **batch collect の失敗が原因を捨てる。行は永久に in-flight。** Phase 3 で実測: realtime で先に埋め込んだ chunk の batch job (provider 側は `BATCH_STATE_SUCCEEDED` / 10-of-10 成功) を回収しようとすると `KIO-E-CONFIG-SCHEMA-001: embedding batch collect failed to persist: ContractViolation` で失敗し、**何度叩いても同じ**。`persist_group_vector` の 2 箇所が `map_err(\|_\| TaskExecutionFailure { retry_kind: ContractViolation, .. })` で**下位のエラーを丸ごと捨てている** (main.rs:14701, 14711) ため、`write_chunk_embedding` が落ちたのか `link_chunk_vecs_to_content_vector` が落ちたのか、なぜ落ちたのかが CLI から一切分からない。<br>結果として行は `state=1` のまま残り、予約を握り続ける。**provider は実際に課金しているのに台帳はそれを記録できない** (過少記帳)。唯一の出口は `batch abandon` (対話確認必須) で、予約額を `unknown_settled` として確定させること — 金額としてはそれが正しい (provider は課金済み) が、**「なぜ回収できないか」を知る手段が無いまま諦めるしかない**のが問題。<br>修正 = 両サイトで下位エラーを保持して診断に載せる。`ContractViolation` という分類自体は 07 §5.3 の規則どおりでよいが、**原因を捨てる必要はない** |
| I14 | **sync レーンを「1 呼び出し = 1 グループ = 1 台帳行」にした (I12 の残件)。按分は採用せず、実装ごと削除した。** `:batchEmbedContents` は CALL 単位で 1 つの token 数を返す。旧構造は `EMBEDDING_BATCH_SIZE = 32` により 1 回の送信が最大 32 行をまたぎ、**行単位で正直に確定できるものが何も無かった**。I12 の初版は「行が 1 本のときだけ実測」としたが、被覆率は **sync 30 行中 1 行 (3%)** — クエリ埋め込みは本質的に 1 行なので機能する一方、**realtime のチャンク埋め込みは常に複数行**で 1 件も実測されていなかった (dogfood 実行では 1 呼び出しあたり 9〜12 グループ)。<br>**ユーザー裁定 (2026-07-25): `--realtime` は今後も既定にしない。** これが決め手になった。按分は「合計だけは正確」という妥協で、行単位の数字は最後まで導出値のままだったが、既定にならない経路なら**往復回数を払って質問自体を消せる**。両レーンが再び「課金単位 = 記帳単位」で揃う — Batch は job を task にすることで (07 §5.7)、sync は call を row にすることで。<br>実装 = `send_embed_batch` → `send_embed_group` (1 グループ 1 呼び出し)。`apportion` / `SyncEmbedReport` / `token_weights` を削除。QA13 の「複数グループには代表 token を通す」回避策も**問題ごと消滅**した (1 呼び出し = 1 グループなので、各送信が自分の予約 token を持つ)。`EMBEDDING_BATCH_SIZE` は adapter 呼び出しの粒度ではなくなり、plan/reserve の 1 サイクルの大きさだけを縛る (doc も訂正)。<br>**失敗時の意味も改善した**: 途中で失敗しても、既に送った行は送信・確定・done のまま残る (実際に課金されている)。到達しなかった行だけが failed になる — 1 呼び出し 1 バッチの旧構造では全行まとめて失敗させるしかなかった。<br>被覆率 3% → **100%**、全行 `estimated=0`。契約テストは合計だけでなく**行ごとに** 4 倍関係を検算する (按分は合計を合わせながら各行を外しうるため) |
| I13 | **OCR の予約見積りが過大すぎて、実支出の 45 倍に設定した cap を予約だけでほぼ使い切る。** Phase 2 本走 (2026-07-25、384 scope) で実測: 確定支出 **$0.13** に対し in-flight 予約が **$4.87**、コミット合計 $4.9996 / 上限 $5.00 — **残り headroom $0.0004**。**実害が出た: 最後に処理された p19/p20 の 16 ファイルが `hold_reason: "budget"` で保留され、索引から落ちた** (p20 が 15、p19 が 1)。予約が解放された後は headroom $3.81 が空いており、実支出は最終 $1.19 — **上限の 24% しか使っていないのに、過大予約だけで 16 ファイルを落とした**。<br>**しかも実行は成功として報告した。** `batch resume` の `tasks_failed` は 0 のまま、`FAILED-TASK` も `held_unreadable` も 1 件も出ず、8 パス回しても保留は解けない。<br>**復帰手段が「cap を無視する」しかない。** `run_batch` の Paused→Pending 復帰は `override_budget || fallback_reason != "budget_exceeded"` という条件で、**budget 保留だけが名指しで除外**されている (main.rs:10393)。したがって `index --approve --online` も `batch retry --online` も拾わない (実測: どちらも `tasks_attempted: 0`)。markdownize の明示的な復帰集合 `auth_revivable` は `RetryErrorKind::AuthError` だけを admit し、budget 相当が無い — **embedding 側の `reconcile_committed_embedding_tasks` には `budget_paused` の扱いがある**ので、レーン間で非対称。唯一効くのは `batch resume --override-budget`。<br>設計としては「budget 保留の解除は明示的なオペレータ判断」で筋は通るが、**欲しいのは「cap を無視する」ではなく「cap を再評価する — 今は通る」**である。今回の復旧がまさにそれで、実支出は上限の 24% ($1.19/$5.00)、headroom $3.81 が空いているのに、回収するには cap を丸ごと無視するフラグを立てるしかなかった。→ **予約解放後に再評価だけを行う復帰経路 (`--recheck-budget` 相当) を用意するか、budget 保留を「予約が取れる状態になったら自動で Pending へ戻す」扱いにする。****I6 で `tasks_inflight_unreadable` を足して塞いだのと同じ沈黙が、budget 保留という別の口で開いていた** — 「保留されている」ことを呼び出し側へ返す集計が無い。検出は索引化とは独立の生成物突合でしか効かなかった。→ **`batch resume` / `index` の JSON に `tasks_held_budget` (と保留理由の内訳) を出すこと。**<br>加えて **生成物の有無だけでは検出できない**: 16 件のうち 8 件は Phase 1 の決定論ベースライン生成物が残っているため「生成物あり」に見え、突合スクリプトは 8 件しか拾えなかった。OCR 済みかどうかは生成物の存在ではなく tool_profile_hash か task の状態で判定する必要がある。確定済み **235 job** での実測: 予約 $4.3876 → 実額 $0.8840 = **集計 4.96 倍の過大**。にもかかわらず **72/235 (31%) が過少見積り**だった。「平均 5 倍も余らせているのに 3 件に 1 件は足りない」— 推定器が保守側なのではなく、単にばらついている。これは **I10 の鏡像** — embedding は平均 +20.5% 過大で 24% が過少、markdownize は平均 2.37 倍過大でやはり一部が過少。どちらも「平均では安全側に見えるが個別では両方向へ外れる」同じ壊れ方で、原因はどちらも粗い推定器 (markdownize は 3,000 bytes/page 仮定、embedding は `estimate_embedding_tokens`)。**cap の実用性を壊している点が I10 より重い**: 上限を実支出の 45 倍に置いてなお予約で埋まるなら、ユーザーは cap を意味のある値に設定できない。加えて in-flight job は 1 件あたり予約が p01/p02 の確定済み job の 2.1 倍あり (ファイルサイズ差か、docx/pptx → PDF 変換で byte ベースのページ推定が膨らむか未切り分け)。対応候補: ページ数を推定でなく実測する (PDF は page tree を読む、office は変換後に数える)、cap 判定を予約でなく確定 + 未確定の期待値で行う、予約の解放を待たずに再試行できる小額の予備枠を持つ |
| I12 | **I4 を Batch レーンにだけ適用し、sync レーン 2 経路を取り残した。しかも「取り残す理由」として、私が実 API で反証した事実が 4 箇所に残っている。** adapter は `gemini_embedding.rs:485` で実測 token を `usage` に載せているのに、**`catalog.rs:788` の `Ok(response.vectors)` が境界で捨てる** — sync の呼び出し側は実測を見ることすらできず、`estimated=1` で予約額を記帳する。影響は 2 経路で桁が違う: (a) **query embedding** (`main.rs:13666`) — `kio search` 1 回ごとに device scope へ 1 行。$0.000001 級だが、**ユーザーが最も高頻度で踏む経路**。(b) **`--realtime` の chunk embedding** (`main.rs:14274`) — 実コンテンツを 2 倍単価で送る経路。ここが本命で、**I10 と噛み合うと過少記帳になる**: I10 が示したとおり予約見積りは保守側ではなく **8/33 (24%) が過少**、`--realtime` は単価 2 倍なので誤差も 2 倍に効く。過少記帳は budget cap が構造的に防げない唯一の方向 (cap は小さい方の数字しか見ない) — 6731061 の commit message で自分がそう書いた当のリスクを、同じコミットで sync 側に残した。**単価自体は正しい** (`query_embedding_send_lane()` = Sync。R24 で塞いだレーン穴の再発ではない)。<br>**陳腐化した宣言 8 面** (いずれも 6731061 で偽になった。同コミットで実 endpoint をプローブし `usageMetadata` が per-call 合計として返ることを確認済み): `types.rs:415`・`main.rs:13667`・`main.rs:14271`・`main.rs:15624` が「この endpoint は usage を返さない」と明言し、さらに `main.rs:14758`・`main.rs:14973`・`main.rs:15568`・`tests/step5_embedding_batch_lane.rs:368` が同じ前提の上に別の結論を積んでいた (「予約が確定額そのものだから R24 のバグは高くついた」「context 分の過少見積りは settle 時に永久に訂正されない」等)。**数えるたびに増えた: 4 → 8 → 9。** 最後の 1 面は `active_embedding_send_lane` の doc で、原文が「the adapter reports\n/// no usage」と**行の途中で折り返されていた** — `grep` は行単位なので、正しい検索語を使っても構造的にすり抜ける。→ **陳腐化した宣言の掃き出しは、コメント記号を剥がして全文を 1 行に潰してから検索すること** (`grep`/`rg` 単体では不可能)。正しい事実はテストのコメント (`the_reported_token_count_becomes_a_billable_unit`) にだけ書き、宣言側へ 1 面も伝播させていなかった — **spec 監査 r38-r41 で「同一 § 内の同種文は全数列挙」と結論した失敗を、そのままコードで再演している**。<br>修正 = `run_adopted_embedding` が `AdoptedEmbeddingOutcome { vectors, usage }` を返し、`embedding_billed_from_usage` を **3 送信サイト共通の単一の価格付け点**にする (Batch collect / sync query / sync chunk — 1 つの adapter を 3 箇所で価格付けしたことが原因そのものなので)。9 面の doc は同じコミットで直した |
| I11 | **terminal 化した行を `batch resume` のたびに再送・再課金する。** 非再試行エラー (auth 等) は `unknown_settled` で予約額を実額として記帳し state=3 で終端するが、次の `batch resume` が新しい `submission_seq` で予約を切り直して同じことを繰り返す。実測: 鍵を読ませずに `batch resume` を 3 回叩いただけで `submission_seq` 2→4→6、**$0.001934 × 3 が積み上がった** (provider は 401 を返しており 1 円も課金していない)。`unknown_settled` 自体は「post-hoc 照会能力のない Adapter は常に unknown 精算」という CL45 の設計どおりで、旧 JSONL 設計が AuthError を 0 へ戻していたのを意図的に捨てた結果 (`settle_task_charge_unknown` の doc comment に明記) — 争点はそこではなく、**終端後に無制限へ再試行が走ること**。ポーリングは 1 実行で数十パス回るので、鍵が切れた状態で長時間回すと monthly cap まで空課金で埋まりうる。同一 (key, mode) の `unknown_settled` 回数に上限を持たせるか、terminal 行の再駆動に backoff を課す |
| I10 | **予約見積りは保守側ではない。** 33 実ジョブの実測トークンと突き合わせた結果、`estimate_embedding_tokens` の誤差は **-32% 〜 +52%**、**8/33 (24%) が過少見積り**だった (集計では +20.5% 過大なので総額は安全側に見えるが、個別ジョブは違う)。確定記帳は I4 で実測に移ったので台帳は正しくなったが、**budget cap の事前判定は依然この見積りを使う** — 過少なジョブは cap を素通りしうる。`--realtime` は 2 倍単価なので影響も 2 倍。安全側へ倒す (例: 見積りに margin、または送信前に token 数を数える) か、cap 判定側で margin を持つか |
| I9 | **sheet に埋め込まれた chart / 画像が読めない。** 直接抽出の原理的な穴で、`XlsxDocument::media_paths` が件数だけ報告する。塞ぐには「file X の sheet M の中の image N」という evidence 上の同一性が要り、`image_object_hashes` は 3 構造体に**宣言があるだけで書き手も読み手も無い**。dogfood corpus は 20/20 が chart 0 件なので今回の索引化には影響しないが、**実世界の Excel には普通に入る** |

### 7.3 運用上の学び

**モック seam が wire から乖離すると、その経路のテストは何も保証しない。** I3 は
「テストが通っている」ことを根拠に I1/I2 を見逃させた。静的監査 7 系統も、
モックが定義する形を正としたため検出できていない。

→ **外部 API を持つ経路は、採取した実応答を固定する回帰テストを最低 1 本持つこと。**
→ **モックは provider と同じ封筒を通すこと** (パース済みの内側を直接与えない)。

**検証スクリプトの「無い」は、検証対象より先に疑うこと。** Phase 3 で未発見 5 件を調べた際、
突合スクリプトが 5 件すべてを「生成物なし = 索引に入っていない」と報告した。実際は 5 件とも
生成物があり、**スクリプトが非再帰の `glob` を使っていた**だけだった (生成物は
`objects/normalized/XX/YY/` に分散配置される)。Phase 2 の突合が `find` で 311/311 を報告して
いたので突き合わせて気づけたが、**片方しか無ければ「OCR が動いていない」と誤結論していた**。
実際の診断は正反対で、5 件とも自 scope 内では rank 1〜9 に出る = 抽出ではなく横断順位の問題。

→ **「見つからない」と報告する突合は、既知の陽性例で先に自己検証すること** (必ず見つかるはずの
   1 件を通す)。→ **同じ事実を 2 つの独立した方法で測ったら、食い違いは対象ではなく計測を先に疑う。**
