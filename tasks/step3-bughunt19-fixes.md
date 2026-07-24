# 探索型監査 第19ラウンド (R19) — 裁定と修正計画

7 エンジン (Claude-Opus / Sonnet-A / Sonnet-B / Sonnet-C / Sonnet-D / GPT-5.5 / GPT-5.3-Codex-Spark)。
HEAD `de5003f`、全 472 テスト green の状態から開始。

**結果: 0 critical + 4 major + 4 minor。却下 0 (自己取り下げ 0)。**

焦点の「R18 fix が開ける穴」(定番脈 9 例目候補) が **3 本の major** で本命的中 (R19-2/R19-3/R19-4)
— いずれも R17-3/R18-1/R18-2 が新設した embedding/markdownize の **reclaim + 終端化 (invalid_input)** 機構が、
`Failed` タスクを経路ごとに非一貫に扱う縫い目から噴出。加えて runbook が別候補に挙げた **「Tier B / approval 再掃」**
(R6/R7 以来正面未掃) が **major 1 本** (R19-1、秘匿漏出) で的中。R18-4 の「fix が追い越す」残穴 (R19-6) も出た。

Spark (範囲限定=R18 reclaim 新配線の網羅性) は **0 新規の健全確認着地** = R14/R17 型。
だが同ラウンドでフルスコープ 6 本が別脈・同脈別角度で major 4 + minor 4 = **R9-1 パターン 7 回目**。

---

## 所見一覧 (severity 降順)

### R19-1 [major] `!pattern` で解除した Tier A 秘匿ファイルが `--send-secrets` ゲート無し・監査記録無しで OCR + embedding の両オンライン経路へ送信される (リスク勾配の逆転)

**エンジン**: Claude-Opus (実機再現)。**脈**: Tier B/approval 再掃 (runbook R19 候補的中)。**型**: bughunt2 N1 の hold ゲート述語が Tier B マーカーのみを見る「fix が開ける穴」。

**根本原因 (file:line)**:
- `crates/kio-pipeline/src/scan.rs:136-140` — `quarantine_reason` の match は `Some(TierA) if ignored` のみに `secrets_tier_a_excluded` を付与し、**解除 (TierA かつ `ignored=false`) は `_ => None` に落ちる**。
- `crates/kio-cli/src/main.rs:8393-8394` — online markdownize の hold ゲートは `quarantine_reason == Some("secrets_tier_b_warning")` のみ。lifted Tier A は `None` なので `secrets_hold=false`。
- `crates/kio-cli/src/main.rs:7059-7062` — embedding の hold ゲートは `classify_secret(&chunk.raw_path) == Some(SecretTier::TierB)` のみ。lifted Tier A は `TierA` を返すため素通り。

**docs 契約**: docs/10 §1.1:120 は secrets 機構の目的を「取り込み・**オンライン送信事故**を防ぐため」と明記。§1.1:178-181 は Tier B (低リスク) を「ローカル取り込みは行うが online 送信 task は保留・要 `--send-secrets`」と規定。Tier A (最高機微) を解除すると両オンライン経路が無ゲート・無監査で送信されるのは目的違反かつ勾配逆転。

**期待 vs 実際 (control 付き実機再現)**:
| ファイル | markdownize(OCR) | embedding | quarantine.jsonl |
|---|---|---|---|
| Tier B `mysecret.png` (低リスク・未承認) | paused `secrets_tier_b_hold` | paused `secrets_tier_b_hold` | hold 記録 |
| lifted Tier A `secret.pem` (`!pattern`) | **done `online_adapter_done` (課金 2.6e-6)** | **done `embedding_adapter_done` (課金)** | **空** |
| 非解除 Tier A `.env` (control) | — (n_tasks=0) | — | `secrets_tier_a` 除外記録 |

解除は「ローカル管理対象にする」操作であって「クラウド送信の承認」ではない (docs §1.1 規約2)。`--send-secrets` を一度も渡していないのに最高機微ファイルが外部 API へ送信され、監査証跡もゼロ。

**修正案**: `scan.rs:136-140` の match に lifted Tier A を Tier B 同等の online hold へ落とす arm を追加 (`Some(TierA) => Some("secrets_tier_b_warning")` を `_ => None` の前へ。※非解除 Tier A は ingest 前に除外済みなので embedding へ到達する Tier A は解除分のみ)。併せて embedding ゲート (`main.rs:7061`) を `classify_secret(...).is_some()` に拡張。docs 変更不要 (§1.1:120 の既存目的に合致)。
**裁定注記**: severity は critical 隣接だが、発火に利用者の明示操作 (`!pattern`) を要する点で N2/R6-1/R7-1 の「秘匿特有の操作ゼロで送信」critical とは一段異なる → major。

---

### R19-2 [major] QuotaExceeded で max_attempts 枯渇した online markdownize タスクの F8 phantom 予約が、supersede/sweep/batch-retry の全 reclaim 経路から `task_retry_allowed` ゲートで排除され当月 reclaim 不能 (markdownize cap 枯渇 → 正規タスク誤 Paused)

**エンジン**: Claude-Sonnet-A (control 実機 + file:line 4 箇所)。**脈/型**: R18 fix が開ける穴 (R17-3/R18-2 の配線対象の絞り漏れ)。R15-2×R16-7 合流の R17-3 が rate_limit を塞いだ隣で quota が残った。

**根本原因 (file:line)**:
- `crates/kio-pipeline/src/task.rs:346-353` — `QuotaExceeded` は `retryable:true, max_attempts:Some(3)` (RateLimit は `max_attempts:None`)。
- `crates/kio-cli/src/main.rs:7890-7898` — `task_retry_allowed` は `retryable && attempts < max_attempts`。quota は 3 回失敗で恒久 `false`。
- `crates/kio-cli/src/main.rs:8333-8337` (R18-2 sweep) と `main.rs:9317-9322` (R17-3 supersede) は共に Failed の退役条件に `task_retry_allowed(task)` を含む → exhausted quota を除外。
- `crates/kio-cli/src/main.rs:5525-5550` (batch retry) も同ゲートで Failed→Pending を拒否。
- **対照 (非対称の傍証)**: embedding 側 `reconcile_committed_embedding_tasks` (`main.rs:7659-7667`) は reclaim 判定に `task_retry_allowed` を一切使わず `status ∈ {Pending,Running,Failed} && reserved_usd.is_some()` のみ。embedding はこの穴が無い。

**期待 vs 実際**: R17-3 契約「rate_limit/quota で失敗し非課金の F8 予約は対象が非 live 化したら reclaim」。実際 = quota は「retryable だが有限回で尽きる」中間状態に落ち、3 回失敗後は全退役経路から排除され `cost-ledger-reclaimed.jsonl` に行が生成されず per-adapter cap を当月食い潰す。Sonnet-A が control 実機 (rate_limit phantom は編集で reclaim される / quota-exhausted は reclaim されず新規タスク誤 Paused) で確定。

**修正案**: `main.rs:8336` と `main.rs:9321-9322` の Failed 退役条件から `task_retry_allowed(task)` の conjunct を外し、embedding 側 (7659-7667) と同じ「reclaim 可否は `retire_online_task_reclaiming` 内部の RateLimit/Quota 判定に委ねる」パターンに揃える。→ **R19-3 と協調して設計** (下記「修正の相互作用」参照)。

---

### R19-3 [major] R18-1 の非 live embedding reclaim が Failed(rate_limit/quota) を invalid_input へ恒久終端化するが、content-addressed identity (chunk_id) は revert/undo/backup で復活し得る — 復活後 enqueue idempotency が re-enqueue をブロックし chunk が vector 検索から恒久消失

**エンジン**: Claude-Sonnet-B (control 実機 RRF 1/61)。**脈/型**: R18 fix が開ける穴 (R18-1 が「非 live = 恒久」を前提したが content-addressing では可逆)。

**根本原因 (file:line)**:
- `crates/kio-cli/src/main.rs:7642-7690` — R18-1 の reclaim pass は非 live Failed(rate_limit/quota) を `retire_online_task_reclaiming` で `invalid_input` (非 retryable) に終端化。
- `crates/kio-cli/src/main.rs:7817-7833` — `enqueue_embedding_tasks` は **status を問わず** 全 embedding task の output_ref を集め (`7821`)、`existing.contains(&output_ref)` なら新規 Pending を作らず `continue` (`7831-7832`)。終端化 task が同一 chunk_id を永久ブロック。
- `crates/kio-cli/src/main.rs:7696-7698` — R15-7 の transitions loop は Pending/Running のみ処理。R18-1 以前は Failed(rate_limit) は `max_attempts:None` で retryable のまま残り、chunk 復活時に retry で埋め込まれた。R18-1 の invalid_input 化がこの回復を潰した。

**期待 vs 実際 (control 実機再現)**:
```
index --online rate_limit  → V1 chunk H1 Failed(rate_limit), reserved
edit to V2, index --online mock → R18-1 reclaim: H1→invalid_input, phantom reclaimed
revert to V1 EXACT bytes (byte-match YES), index --online mock → chunk 再埋め込みされず
search "ALPHA" → n_results=1 (字句検索可) だが score=0.01639=1/61 = 純字句寄与のみ (vector 寄与ゼロ)
```
以後 batch retry/resume/repair 全て no-op。exit 0・警告なしの完全沈黙。markdownize 側も同型 (ローカル抽出 baseline は生存するため字句検索は効くが AI 強化 markdown へ二度と到達不可)。

**修正案**: 非 live 起因の終端化に **再 enqueue 可能な専用 fallback_reason** (例 `"retired_non_live"`) を用意し、`enqueue_embedding_tasks` (`7831`) と markdownize 側 `enqueue_online_placeholder_task` の idempotency 判定がその reason をブロック対象外とし、live candidate 再出現で新規タスクを起こせるようにする (reclaim/phantom 処理は維持)。→ **R19-2 と協調** (下記参照)。

---

### R19-4 [major] 重複コンテンツ (共有ライセンスヘッダ/共通セクション等) の embedding chunk が rate_limit で Failed すると、`rebuild_chunk_vec` の content-hash JOIN が双子成功側の vector で chunk_vec を裏で完成させ、reconcile の live→Done ループが Failed を除外するため task が永久固着 + phantom reserved_usd 残留 + `pending_enrichment` 恒久 1

**エンジン**: Claude-Sonnet-C (独自 sqlite-vec 拡張ビルドで chunk_vec 直接検証 + control 実機)。**型**: 「データレベルの完成 (content-addressing) と タスクレベルの完成 (status 遷移) の乖離」を reconcile が部分的にしか吸収していない構造の縫い目。

**根本原因 (file:line)**:
- `crates/kio-index/src/embedding_store.rs:152-171` — `rebuild_chunk_vec` は `chunks c JOIN embeddings e ON e.target_id = c.text_hash` の **タスク非依存な content-hash 結合** で chunk_vec を無条件再構築。
- `crates/kio-cli/src/main.rs:647` — `run_index` が embedding enrichment (`652`) より **前** に毎回無条件で `rebuild_chunk_vec` を呼ぶ。→ 双子 (b.md) の成功送信で `embeddings` に乗った共有本文 vector を使い、a.md 側 Failed タスクの chunk_id が本人の再送/reuse 判定を経ずに chunk_vec へリンク。
- `live_chunks_without_embedding` (`main.rs:7606-7611`) は「chunk_vec に行がある = 仕事なし」で pending から除外。
- `reconcile_committed_embedding_tasks` の live→Done 補完ループ (`main.rs:7696-7698`) は `matches!(status, Pending|Running)` のみで **Failed を除外** → 固着タスクを拾えない。
- 唯一回復する batch retry (`5525-5550`) は `embedding_done_transition()` を素通しするだけで reclaim を経ず、非課金 rate_limit phantom が Done タスクへ永久残留 (R18-1 の reclaim は Failed のみ対象・Done は「常に real spend」前提だが本ケースはその前提を破る)。

**期待 vs 実際 (control 実機再現、backoff 経過で分離)**:
```
a.md (# AAAA + ## Shared Section 本文) を index --online rate_limit → 2 chunk Failed(rate_limit)
b.md (# BBBB + a.md と同一の ## Shared Section) を index --online mock → b.md 2 chunk Done
backoff 経過 + index --online mock ×2:
  title chunk (unique)   → done (正常 retry で回復)
  shared chunk (duplicate) → failed rate_limit reserved=5.2875e-6 のまま恒久固着
```
`kio index` を何度回しても shared chunk は不変、`pending_enrichment_tasks` 恒久 1。

**修正案**: `main.rs:7696` の状態ガードを `Pending | Running | Failed` に拡張し、chunk_vec に既にリンク済みの live chunk を status に関わらず Done へ収束させる。あわせて非課金 rate_limit/quota スタンプは Done 化前に `retire_online_task_reclaiming` 相当で reclaim (phantom を残さない)。

---

### R19-5 [minor] Partial markdownize retry の attempts が「送信結果」でなく「re-enqueue 時点」でも消費され二重計上、かつ Ok(Partial) 復帰時に next_retry_at 未設定で backoff なし即再投入

**エンジン**: GPT-5.5 (静的 file:line)。**脈**: R10-4/R11-6 の task 会計残余。

**根本原因 (file:line)**:
- `crates/kio-cli/src/main.rs:5636-5643` — `reenqueue_partial_markdownize_tasks` が Pending 復帰時に `attempts += 1` (`5643`) + `next_retry_at = None` (`5640`)。
- `crates/kio-cli/src/main.rs:6094` — 再 enqueue されたタスクが online executor へ流れ adapter 失敗すると `attempts += 1` を **再度** 実行 → 1 回の送信で二重消費。
- `crates/kio-cli/src/main.rs:6053-6075` — Ok(Partial) 復帰経路は status/output_ref のみ書き戻し attempts/next_retry_at 未更新。reenqueue には次_retry_at ゲートが無い (`5603-5647`) → 次の batch retry が backoff を見ず即再投入。

**期待 vs 実際**: 期待 = 実 adapter 送信 1 回につき attempts 1 回・retryable Partial 残存には next_retry_at 設定。実際 = no-send (budget pause/precondition) でも re-enqueue で消費、adapter 失敗で二重消費、Partial 再失敗は backoff 無し即 retry 可。影響は「retry が ~2x 早く枯渇 + partial 間 backoff なし」で有界・fail-safe 側 → minor。

**修正案**: `reenqueue_partial_markdownize_tasks` の pre-send `attempts += 1`/`next_retry_at = None` を廃し、executor の送信結果処理 (`Err` または `Ok(Partial)`) でのみ governing `RetryPolicy` から attempts/next_retry_at を 1 回更新する。

---

### R19-6 [minor] store 破損回復ガイダンス (`store_corruption_recovery_hint`) が `index_missing`/`index_corrupt` に未配線 — partial exclusion と異種混在全滅でガイダンスゼロ

**エンジン**: Claude-Sonnet-D (実機 3 パターン)。**型**: 「fix が追い越す」(R18-4 が store_corrupt/snapshot_shallow だけを構造化 recovery に格上げし、R17-4 コメントの参照元だった index 系を置き去り)。

**根本原因 (file:line)**:
- `crates/kio-cli/src/main.rs:2479-2491` — `store_corruption_recovery_hint()` の match は `store_corrupt`/`snapshot_shallow` の 2 reason のみ扱い `index_missing`/`index_corrupt` は `_ => None`。
- `crates/kio-cli/src/main.rs:1438-1451` (index_unusable 集約) — 同種全滅時に `message` へ repair 文言を埋めるが `context.recovery` は付かない。
- `crates/kio-cli/src/main.rs:1469-1497` (store_corruption 集約) — 異種混在 (index_corrupt + store_corrupt、健全 scope ゼロ) はどちらの同種集約にも該当せず素の "all searched scopes failed" (ガイダンス文言ゼロ) にフォールバック。

**期待 vs 実際 (実機 3 パターン)**: (1) 単一 index_corrupt = message あるが context.recovery なし、(2) partial exclusion = 健全 scope 生存下で index_corrupt entry が recovery なし・同一レスポンス内で store_corrupt entry だけ recovery 付きの非対称、(3) 異種混在全滅 = exit 4 でガイダンス文言ゼロ。

**修正案**: `store_corruption_recovery_hint()` に `"index_missing" | "index_corrupt" => Some("... kio repair --rebuild-db ...")` arm を追加 (既存 per-entry 配線と index_unusable 集約の両方がこの関数を経由するよう揃える)。新エラーコード導入は避ける (R17-4 の教訓)。

---

### R19-7 [minor] `--send-secrets` 承認後も quarantine.jsonl の disposition が `hold` 固定 — `kio status` が承認・送信済みファイルを未承認と誤報

**エンジン**: Claude-Opus (実機再現)。

**根本原因 (file:line)**:
- `crates/kio-cli/src/main.rs:9853` — `record_quarantine_candidates` は `if existing.contains(&candidate.input_path) { continue; }` で **path 既存なら一切スキップ** → `hold`→`send_approved` の遷移行が永久に追記されない。
- `main.rs:9838-9850` のコメントは disposition 更新 (`hold` until `--send-secrets`, then `send_approved`) を意図しているが path-only dedup がこれを阻止。

**期待 vs 実際 (実機)**: `--send-secrets` で embedding/markdownize task が `done` (送信済み) になっても quarantine record は `approval_method: "hold"` のまま → 07 §122 の「どの file/task を送信対象にしたか」の監査整合を崩す。

**修正案**: `existing` の dedup キーを path 単独でなく `(path, approval_method)` にし (reader は path ごと最新行を採用)、hold→send_approved の遷移を追記させる。

---

### R19-8 [minor・borderline-intended] `adapter.policy.max_input_bytes` は enqueue 時 (`kio index`) のみ検査され、送信時 (`batch resume`/`retry`) に再検査されない — cap を後から絞ってもキュー済みタスクは新 cap を無視して送信・課金

**エンジン**: Claude-Sonnet-A (control 実機)。**裁定**: minor (borderline)。R12-2 設計メモが「prepare/enqueue 前のサイズ検査」と記し docs/07 §7.1:352-355 も継続強制保証に `allowed_scope`/`allow_network` のみ列挙 (max_input_bytes は未規定) = enqueue-time 限定は意図の範囲内とも読める。ただし同 policy ブロックの姉妹キー `allow_network` は送信毎に再検査 (`main.rs:5817-5846`) される非対称があり、送信時再検査は無回帰の防御改善。

**根本原因 (file:line)**:
- `crates/kio-cli/src/main.rs:8372-8391` — `run_index_pipeline` が `effective_max_input_bytes` を候補ループ内で 1 回検査 (唯一の enforcement)。
- `crates/kio-cli/src/main.rs:6296-6318` — `online_markdownize_precondition_ok` (Pending 送信直前の唯一ゲート) は existence/hash/text-native/prepared_units のみ検査し size を見ない。

**期待 vs 実際 (control 実機)**: 245 バイトの pending task 作成後 config に `max_input_bytes=244` を追記 → `batch resume` で送信・課金 (`device_spent_usd:2.45e-05`)。cap を最初から 244 にすると `skipped_oversized_files:1` で正しく機能。

**修正案**: `online_markdownize_precondition_ok` に `fs::metadata().len() > effective_max_input_bytes(repo)` の再検査を追加し、超過時は既存 invalid_input 退役経路へ合流。無回帰 (cap 不変の通常フローは影響なし・cap 引き下げ時のみ利用者意図を尊重)。

---

## 修正の相互作用 (fix phase で必須の設計協調)

**R19-2 / R19-3 / R19-4 は embedding/markdownize の reclaim + reconcile + enqueue-idempotency の重なる領域を触るため、独立パッチにすると衝突する。一体で設計せよ:**

1. **R19-2** は「exhausted-quota Failed も終端化+reclaim せよ」= 終端化される Failed が **増える**。
2. **R19-3** は「invalid_input 終端化が再 enqueue を恒久ブロックする」= R19-2 の終端増加が R19-3 の穴を広げる。→ R19-3 の fix (再 enqueue 可能な `retired_non_live` reason) が **R19-2 を安全化する前提**。
3. **R19-4** は「live-but-embedded な Failed を reconcile が収束できない」= reconcile の Failed 扱いを統一する。

共通の根: `reconcile_committed_embedding_tasks` (7628-7726) と退役経路が **Failed タスクを live/非 live/duplicate で非一貫に扱う**。統一原則案:
- 非 live Failed(非課金) → reclaim + **再 enqueue 可能な**終端 reason (R19-2 の quota も含める / R19-3 の再出現を許す)
- live-but-embedded Failed (chunk_vec 完成済み) → reclaim + Done 収束 (R19-4)
- live-but-unembedded Failed(retryable) → backoff 後 retry (現状維持)

**推奨: この 3 件はオーケストレータ自身が実装** (R18 と同様、delicate な cost-ledger + task 状態機械で context 保持が delegate より有利)。各 fix ごとに回帰テスト (discriminator) + control 付き実機 repro クローズ。

---

## 探索したが問題なしと確認した領域 (健全確認 — 反証ではなく追加確認)

- **R18 reclaim 新配線 (Spark 焦点 + 全 Sonnet + Opus + GPT-5.5 が独立確認)**: `retire_online_task_reclaiming` の二重 reclaim 防止 (reserved_* の None 化)・Done 誤 reclaim なし (markdownize は placeholder 判定・embedding は status で Done 除外)・NetworkError 非 reclaim 不変条件・live_paths が Tier B hold/oversize/quarantine を誤除外しない・embedding per-chunk stamp の線形性 (estimate_embedding_cost 純線形)・apply_embedding_transitions 単一書き戻しの O(N²) 回避・reconcile reclaim と transitions loop の非競合。
- **R18-3 net_monthly_spent の netting 網羅**: budget_status_json/scope_budget_warning/budget_remaining_for_adapter の 3 面が単一ヘルパー経由、gross `monthly_total` 直接呼びは本番コードに残存なし (テストのみ)。`ScanPreview.estimated_cost` は未配線プレースホルダで漏れ経路にならない。
- **Tier B/approval 束縛**: approval は scope_id + tool_id に束縛、`secrets_send_approved` は現 scope_id と approval 行の scope_id 厳密一致 (再 init で自動失効)、送信直前再検証あり (markdownize/embedding とも)。※R19-1 は「解除 Tier A が Tier B hold 分類に載らない」別問題。
- **時刻/civil date 演算**: Hinnant アルゴリズム、閏年/月末境界、ログローテ/prune の日付比較健全。月跨ぎ charge/reclaim は同一 `month` stamp で対称 (R17/R18 据え置き継続)。
- **検索数理/Evidence**: RRF/MMR/cursor HMAC/FTS5 phrase quoting (injection なし)/object URI hash 検証/R17-1 偽 commit 拒否/N5 gen 束縛/CAS hash 検証。

## 却下 (0 件)

なし。全エンジンの所見が重複ゼロで採択 (R9・R16 に次ぐ 3 回目の却下 0)。Spark の 0 新規は「範囲限定の健全確認」として据え置き扱い (却下ではない)。

## 据え置き継続 (Step 4 gc 設計マター)

tasks.jsonl / cost-ledger / open cache の無限成長、month 月跨ぎの charge/reclaim 記帳 (R17/R18 と同じく reserved_month で対称のため会計上は正)。R19 でも新規理由なし。
