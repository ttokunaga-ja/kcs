# 残宿題の実行計画 (2026-07-25)

対象は 3 件。依存関係は **H2 は独立 / H1 が H3 の Phase 2 を塞いでいる**。

| | 宿題 | 規模 | 課金 | 塞いでいるもの |
|---|---|---|---|---|
| **H1** | embedding の Batch レーン CLI ドライバ | 大 | なし (実装は hermetic) | H3 Phase 2 |
| **H2** | `repair` の破壊的操作の確認プロンプト | 小 | なし | なし |
| **H3** | dogfood コーパスの索引化 | 中 | 約 $1.4–2.0 | H1・OOXML 修復・API キー |

---

## H1. embedding の Batch レーン CLI ドライバ

Adapter 層 (`kio_adapter::gemini_batch_client`) は実装済み・単体 16 本 green。
残るのは **CLI 側の駆動** — 「submit して返る」形への変更と、poll/collect の追加。

### H1-0. 先に決めるべき設計点 — job の粒度 (**着手前の裁定が必要**)

07 §5.7 は Batch レーンの v1 契約として **「1 job = 1 task」**を確定している
(`batch_job_id` 列がそのまま回復キーになるため)。ところが embedding の task 粒度は
**group** = 同一 `embedding_hash` を共有する chunk 群であり、fixture 実績で **2,321 task**。
これをそのまま 1 job = 1 task にすると **2,321 個の batch job** を投げることになる。

| 案 | 内容 | 評価 |
|---|---|---|
| **A. job 単位の task を新設 (推奨)** | N group を 1 job にまとめ、その job 自身を 1 つの task として台帳に載せる。`input_hash` = メンバの `embedding_hash` を整列して連結した digest | **1 job = 1 task が保たれる**。§5.8 の状態機械・回復・`batch abandon` が無改造で効く。group が変われば別 task キーになるが、既に埋め込み済みの chunk は content-addressed reuse で自然に脱落するので無駄がない |
| B. N task が 1 job を共有 | 既存の group task をそのまま使い、複数行が同じ `batch_job_id` を持つ | 07 §5.7 の v1 契約を破る。回復 walk が job→task の fan-out を扱う必要があり、`abandon` の意味も変わる |
| C. 1 group = 1 job | 契約は守れるが 2,321 job | provider のレート制限・運用ともに非現実的 |

**A を推奨**。1 job あたりのメンバ数は adapter 側の上限 (inline 20MB / `MAX_INLINE_REQUESTS = 2048`)
の下で選ぶ。fixture 規模なら **2〜3 job で全 2,321 chunk** を賄える。

> 影響: 07 §5.7 に「embedding の task 単位 = job (メンバ集合の digest)」を 1 段落追記する。
> 「1 job = 1 task」自体は破らない。

### H1-1. 実装 (段階と検証)

1. **submit 経路** — `run_embedding_enrichment` を分岐させる。
   `effective_invocation_lane()` が Batch なら: group を job 単位に束ね、相 1 (行作成 + 予約) →
   `create_embedding_job` → `batch_job_id` 記録で返る。task は pending のまま
   (`fallback_reason = "batch_submitted"` — markdownize レーンの既存定数を再利用)。
   realtime なら現行の同期経路をそのまま通す。
2. **poll/collect 経路** — `poll_batch_markdownize_jobs` と同じ 4 箇所の write-command entry
   (`index` / `repair rebuild-db` / `reindex` / `batch resume`) に embedding 版を追加。
   `get_job` → 終端なら `fetch_inlined_results` → `metadata.key` で chunk に対応づけ →
   `embeddings` / `chunk_vec` へ書き込み → 相 3 の確定記帳 + `intent_token` NULL 化。
3. **受入検査** — 07 §5.3 の (1)〜(5) を batch 経路にも通す (id 全単射・次元・有限非ゼロ・
   正規化後再検査・profile 一致)。sync 経路と**同じ関数**を通すこと (二重実装しない)。
4. **レーン切替** — `active_embedding_send_lane()` を `effective_invocation_lane()` へ差し替える。
   これが**この変更の最後の 1 行**であるべき。それまでは sync 単価で記帳され続け、記帳は正しいまま。
5. **単価** — Batch レーンの $0.10/1M が `embedding_usd_per_token` 経由で自動的に効く (実装済み)。

### H1-2. テスト

- hermetic mock (`KIO_TEST_GEMINI_BATCH`) で **submit → pending → poll → collect** の
  フルサイクル契約テスト。markdownize の `step4b_batch_lane_contract.rs` が雛形になる。
- crash window: submit 後 / job 作成後 / 結果取得後の各点で中断し、再実行が
  **二重課金せず**完遂すること (`fail_phase` seam で再現)。
- `--realtime` 指定時に sync 経路へ落ちること、飛行中の batch 行が乗り換えないこと。
- `batch abandon` が embedding 行にも効くこと。

### H1-3. 想定コスト

実装 700–900 LOC + テスト 500–700 LOC。**実 API 呼び出しなしで完結**する
(mock seam で全経路を覆えるため)。

### H1-4. 完了後の推奨 — 実装監査 1 ラウンド

この変更は **課金経路と crash 回復の両方**に触れる。R23 と同じ多エンジン実装監査を
1 ラウンド通すことを推奨する ([multi-model-cli-audit] の 5〜7 系統)。
過去の実績では、この層の穴は「fix が開けた穴」として次ラウンドで出ている。

---

## H2. `repair` の確認プロンプト (小・独立)

06 §1 は `repair verify-objects --prune-orphans` と `repair registry-prune` に
**確認プロンプト必須**と定めているが、**実装が存在しない**。
先の整理で死んでいた `--yes` を削除したので、プロンプトと `--yes` をセットで入れる。

- `confirm_batch_action` (main.rs) が既にあるので流用する。`purge` の
  `confirm(&preview, args.yes)` が「preview → 確認 → 実行」の雛形。
- 削除対象を**先に列挙して見せてから**問う (purge / registry-prune と同じ作法)。
- 非対話 (`isatty=false`) では `--yes` 無しは `KIO-E-CONFIRM-REJECTED-001` で拒否。
- `--yes` を両サブコマンドへ再追加する。

実装 80–120 LOC + テスト 4〜6 本。**H1 と独立**なので、H1 の待ち時間に入れられる。

---

## H3. dogfood 索引化 (計画は [dogfood-index-phase-plan.md](dogfood-index-phase-plan.md))

裁定済みの前提: **Phase 2 はドライバ完成を待つ**。

| Phase | 状態 | 依存 |
|---|---|---|
| Phase 0 — コーパス退避 | **完了** (`~/kio-dogfood/corpus-v1`) | — |
| Phase 0 — OOXML 修復 (30 ファイル) | **Codex に委任済み・報告待ち** | — |
| Phase 0 — `tools.toml` / `config.toml` 作成 | 未 | — |
| Phase 0 — API キー 2 本 | **ユーザー作業** | — |
| Phase 1 — offline baseline (428 scope・約 12 分) | 未・**無課金** | OOXML 修復 |
| Phase 2 — p01 canary → 全体 | 未・課金 $1.4–2.0 | **H1** + API キー |
| Phase 3 — 32 契約の実測検証 | 未 | Phase 2 |

**Phase 1 は H1 を待つ必要がない。** OOXML 修復が終わり次第、私の検証 →
offline baseline まで走らせられる。ここで配線・スコープ・エンコーディングの問題を
課金前に全部出し切っておくと、Phase 2 が一発で通る確率が上がる。

---

## 実行順の提案

```
[並行 1] H2 確認プロンプト        小・独立・無課金
[並行 2] Codex の OOXML 修復報告 → 私が検証 → H3 Phase 1 (offline baseline)
   ↓
H1-0 job 粒度の裁定 (A/B/C)      ← ユーザー判断が要る唯一の点
   ↓
H1-1〜H1-2 ドライバ実装 + テスト
   ↓
(推奨) H1-4 実装監査 1 ラウンド
   ↓
H3 Phase 2 canary → 全体 → Phase 3 検証
```

**ユーザーの判断・作業が要るのは 3 点だけ**:

1. **H1-0 の job 粒度** (推奨 = A)
2. **API キー 2 本** (`MISTRAL_API_KEY` / `GEMINI_API_KEY`)
3. **H1-4 の監査ラウンドを回すかどうか**

それ以外 (H2・Phase 1・H1 の実装とテスト) は指示があればそのまま着手できる。
