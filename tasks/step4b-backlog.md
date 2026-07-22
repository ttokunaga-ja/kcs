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
- その他: idempotency key (QA13)、ledger バックアップ/復元 (QA14/15)、orphan 帰属 (QA15)、
  render_params identity (QA34) ほか

### 1-B. QB 残 19 (26/27/34-48/63-65)
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
