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
(裁定の全記録はセッション作業域 kcs-r23/adjudication.md、要旨は `58cea60` コミットメッセージ)。

**残るユーザー側 Done 手続き (実データが必要な 2 点 — 09 §4.1/§4.2)**:
1. M3-1 Q_hard の一回限り増補 (18 → 20 問以上) + 再凍結 (件数と digest を 09 §5.5 #5 行へ追記)
2. 実コーパスでの対 Spotlight (mdfind) / ripgrep-all baseline 比較 (KCS >= 0.8 かつ差 >= 0.3)

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
  Recall@10 = **KCS 8/24 (0.333) / mdfind 0/24 / rga 0/24** (rga は pandoc 導入 + 断片採点の
  上振れ運用でも 0 — Q_hard の設計どおり字句エンジンは全滅)。**差 >= 0.3 は両者に対し成立、
  KCS >= 0.8 の腕が未達 = ゲート OPEN**。クラス別 KCS: hard1 3/8・hard2 5/8・hard3 0/8。
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
  2,321 chunk を新 profile (`09ff0784`) で再埋め込み ($0.0096)。**凍結 24 問を再測定 = KCS
  9/24 (hard1 4・hard2 1・hard3 4)** — 8→9 の微増、かつ hard2 が 5→1 に**後退**。差 >= 0.3 は
  両 baseline に対し成立継続、`KCS >= 0.8` は依然 OPEN。
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
- 残るユーザー側 Done: baseline ゲートの充足 (cross-scope マージ score 化ラウンド後の再測定) と dogfood。

## 1. 残余契約 84 件 (QA 65 + QB 19 = P0 45 / P1 32 / P2 7) の選別

棚卸し方法: 契約書の全 ID − crates/ 内の実装参照 (2026-07-22 grep)。ID 一覧は
`tasks/step4b-contract-tests-p3a.md` / `-p3b.md` の該当節。

### 1-A. オンライン Adapter/課金/承認機構 (QA 系の大半) — v1.0 スコープ判断待ち
eval (offline) と北極星 3 シナリオはこれら無しで Done に到達済み。**online 課金運用を
始める前には必須**の層。優先席:
- ~~**安全性直結 P0 (先行推奨)**: QA21/22/25-27/29-31/16-19~~ → **2026-07-22 実装完了
  (`5dba4e5`)**: 送信 gate AND 化 (未設定 = 不成立)・approvals[] の scope.json 移設
  (QA23/24 field 同梱、consents.jsonl は移行せず再承認方針)・`kcs adapter revoke` +
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
  user_version + companion file の復元検知 → KCS-E-BATCH-RESTORE-RECONCILE-001 ゲート
  (Reused 行は通す)・`kcs ledger reconcile` 新設 (sync 回復 + batch 回復 walk 初配線 +
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
   1 文字も読めない。実装 = `kcs-adapter/src/pdf_decode.rs` の有界 graph decoder
   (object index + ObjStm 展開 + Page→Font→ToUnicode 解決 + bfchar/bfrange + content-op
   復号、fail-empty で legacy 経路とバイト同一共存、inflate 16 MiB 上限のみ hard error)。
   deterministic profile は 1.0.0→1.1.0 bump (意味論変更 = 新 tool_profile_hash、07 §2.1
   追記 = FB 枠)。実機実証: eval-gen の lualatex PDF (luatexja) が offline 索引され
   `read`/`境界`/`3600` 全ヒット、実 soffice 変換 PDF の抽出アサーション追加。
   テスト 1,237/0・eval 回帰ゼロ
2. QB41 の online 再結線 — enqueue dedup が (input_path, input_hash) キーで新 gen の
   online 再 enrichment を塞ぐ (offline gen+1 は生成済み。online lane の gen 認識は独立変更)
3. PPTX online 往復の専用テスト (offline は office_02、DOCX online は office_03 で被覆済み)
4. 頁数が変わる renderer 更新のドリフトは非検知 (`kcs reindex --force` の領分 — ガード (b) の
   意図的帰結)。office incremental は mode=Full 固定 (identity 対応関係が未定義のため)
5. XLSX (sheet 描画意味論 + QB27) / 音声 — 変換機構未定義のまま繰延 (07 §5.1 追記に明記)

### 1-A3. Mistral Batch 送信レーン (2026-07-23 実装完了 `18b9a7f` — 「OCR はバッチのみ許可」裁定の前提実装)
§5.8 台帳状態機械は QA13-15 時点で完全実装済みだったが相 2a/2b の本番 caller はゼロ =
送信レーンだけが未実装だった。**実装済み**: 07 §5.7 の client 契約 8 操作 (実 REST +
hermetic mock seam `KCS_TEST_MISTRAL_BATCH`、実 API 形状は experiments/ocr-verification の
2026-07-03 実測が正)・§5.8 書込順序どおりの submit (1 job = 1 task、metadata 5 key、
custom_id = input_hash、filename = kcs-<token>.jsonl)・poll/collect を batch resume + 書込系
preamble 4 箇所に配線 (回収は sync と同一 materialize 経路を共有)・cleanup-first (upload 削除
完了まで intent_token 保持)・bbox 有効 task も batch (bbox 既定 ON のため例外化は裁定の空文化)・
TIMEOUT_EXCEEDED = expired で予約額 estimated 記帳 / FAILED・CANCELLED = 0 記帳。
07 §5.7 に FB 追記。契約テスト 5 本 (submit 順序 / collect+検索 / crash 窓→reconcile found→
回収 / failed 終端 / in-flight exit 3)。テスト 1,260/0・eval 回帰ゼロ。
**残余 (順に優先度高)**:
1. **実 API 契約試験** (provider_scope_id / list_uploads / pagination — 07 §5.2 既記載の
   Step 3 実測分。初回オンライン実行 = eval corpus の batch OCR pass で消化するのが最短。
   v1 の provider_scope_id は `KCS_MISTRAL_WORKSPACE_ID` 上書き + 既定 "mistral:default")
2. incremental Markdownize の batch 化 (v1 は Full 送信へ縮退 — 小差分編集の再 enrichment が
   全頁課金になる。sync 時代の頁 prorate を回復するには collect 側 acceptance の非同期化が必要)
3. batch 出力に埋め込まれた画像の CAS 保存 (sync レーンとの成果物差 — bbox annotation は
   レーン非依存で機能するが、埋め込み画像の evidence 開封が batch 経由分だけ欠ける)
4. tasks.jsonl 喪失時の台帳のみからの persist 回復 (§5.8 の gen 規則再導出) — poll は task
   記述子なし行を skip (reconcile/abandon の領分)
5. 相 2a 着手済み・upload_id 未記録行の list_uploads 照合掃除 (現状 reconcile は報告のみ、
   abandon が脱出路)

### 1-B. QB 残 18 (26/27/34-40/42-48/63-65 — 41 は 1-A2 で消化)
import/export (fork/kcsz)・observability 深部・J 領域残。MVP 機能面への影響なし。

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
1. `kcs log --at/--since` の意味論明文化 (p3b Z5 — QB50-58 は確立フラグ意味論からの類推で
   実装済み。06-cli-spec §1 での規範化を推奨)
2. purged 終端 × contract_violation_count の 1 句 (Phase 3 メモ)
3. `kcs batch abandon --yes` (非対話運用)
4. ALTER TABLE 系 lint (10 §7.5.3 隣接)
5. 10 §12.1 の BATCH 表へ `KCS-E-BATCH-RESTORE-RECONCILE-001` を追記 (QA14 ゲート —
   CLEANUP-PENDING と同型、exit 1)
6. 06-cli-spec §1 へ `kcs ledger reconcile` を追記 (JSON 形状・冪等・network opt-in 不要)
7. 10 §7.5.2 へ復元検知の具体機構 1 句 (PRAGMA user_version 書込カウンタ + `.write-seq`
   companion 照合 — 挙動規範は既存のまま、検知手段の明文化)

適用済み: #1 決定的 query 正規化 (`1c6a55d`) / #2 スクリプト境界細分 + 短語 drop (`d6e8e85`) +
・U+30FB 補正 (`58cea60`) / #3 FTS 有界エスカレーション (`58cea60`)。

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
