# 修正計画 — G1 / G2 / H2 (2026-07-25)

R24/R24b の裁定後に、**Phase 2 の課金経路上で新たに 2 件** (G1/G2) を実機再現で確定した。
本計画はその 2 件と、裁定済み未修正の repair クラスタ (H2) の修正順・内容・検証を定める。

| | 内容 | Phase 2 経路 | 規模 | 前提 |
|---|---|---|---|---|
| **G1** | Gemini batch client を §5.8 回復走査へ配線 | **上** | 小 (~80 LOC + 3 test) | なし |
| **G2** | batch レーンの provider エラーを分類し保持する | **上** | 小 (~60 LOC + 3 test) | **G1** |
| **H2** | `repair` の preview が本実行を拘束する | 外 | 中 (~150 LOC + 5 test) | なし |

**順序: G1 → G2 → Phase 2 → H2。** G2 は「失敗した行は回復に委ねる」形にするので、
**回収路 (G1) が先に無いと宙吊りを増やすだけ**になる。H2 は課金経路の外なので Phase 2 の後でよいが、
**`repair` を実際に使う前**には入れる (Phase 2 が残骸を残したとき最初に手を伸ばすのがこのコマンド)。

---

## G1. Gemini batch client を回復走査へ配線する

### 現状 (実機再現済み)

`kio_adapter::batch_inventory::configured_inventories()` は **Mistral クライアントしか歩かない**。
`GeminiBatchClient::list_jobs` は実装済みだが**呼び出し元がゼロ** (dead code)。

```
index --online (create_embedding_job 失敗)
  → row: state=0 / intent_token=set / batch_job_id=NULL / 予約 $1.85e-06 保持
kio ledger reconcile
  → unlistable: 1        ← 回収できない。予約は永久に device cap を食う
```

相 2b 開始済み・job 作成前の窓に落ちた行が**恒久的に宙吊り**になる。
脱出は `kio batch abandon <selector>` の手動実行のみ。

### 変更内容

**1. `crates/kio-adapter/src/batch_inventory.rs`**

`configured_inventories()` が Mistral に加えて Gemini の inventory も返すようにする
(どちらも未構成なら空 `Vec`、片方だけ構成済みなら 1 要素)。

```rust
let mut inventories = Vec::new();
if let Some(client) = crate::batch_client::configured_mistral_batch_client()? {
    inventories.push(inventory_from_client(client.as_ref())?);
}
if let Some(client) = crate::gemini_batch_client::resolve_gemini_batch_client()? {
    inventories.push(gemini_inventory_from_client(client.as_ref())?);
}
Ok(inventories)
```

**2. Gemini 用のマッピング関数を足す**

| `ProviderJobRecord` | Gemini での出所 |
|---|---|
| `job_id` | `GeminiBatchJobRecord.name` (`batches/...`) |
| `intent_token` | **`display_name` から `kio-` を剥がす** — `batch_display_name()` の逆関数を新設 |
| `task_key` | **`None`** — Gemini の job は metadata を持たず displayName しか運べない |
| `uploads` | **常に空** — inline 入力なので upload は原理的に存在しない (07 §5.3 訂正ブロックが明記) |

> `task_key = None` で問題ない理由: `job_is_accounted_for` は task_key が無ければ
> **`intent_token` にフォールバックする** ([main.rs:10915](../crates/kio-cli/src/main.rs#L10915))。
> `run_batch_recovery_walk` も `intent_token` 一致で照合する ([main.rs:10723](../crates/kio-cli/src/main.rs#L10723))
> ので、**回収方向は成立する**。逆方向 (orphan 走査) で未帰属だった Gemini job は
> `unknown` に「task_key を持たない」理由で載る = upload と同じ report-only 姿勢
> (10 §7.5.2「filename の token しか持たない upload は帰属不能 (unknown) として報告のみ」) と一致する。

**3. `intent_token_from_display_name()` を `gemini_batch_client.rs` に新設**

`batch_display_name(token) -> format!("kio-{token}")` と**対で**置き、
往復のプロパティテスト (`from(display_name(t)) == Some(t)`) を付ける。
`kio-` で始まらない displayName は `None` (他人の job)。

### テスト

| # | 内容 | 期待 |
|---|---|---|
| G1-1 | `create_job` 失敗で宙吊り → provider には job が存在 → `ledger reconcile` | `batch_found: 1`・行に `batch_job_id` が入る (現状 `unlistable: 1`) |
| G1-2 | 同上だが provider に job が無い | `settled_unknown: 1` — 予約が解放される |
| G1-3 | `kio-` 以外の displayName の job | `unknown` に載り、ローカル行を書き換えない |
| G1-4 | 往復プロパティ | `intent_token_from_display_name(batch_display_name(t)) == Some(t)` |

既存の `TEST_BATCH_INVENTORY_ENV` seam は inventory 全体を fixture 置換するので、
G1-1〜G1-3 は fixture で書ける。実クライアント経路は G1-4 + 単体で担保する。

---

## G2. batch レーンの provider エラーを分類して保持する

### 現状

embedding batch レーンは provider エラーを **4 箇所すべてで `.map_err(adapter_to_kio)?`**
= パス全体を中断する。OCR レーンは §5.8 どおり保持する。

```rust
// OCR (poll_one_batch_markdownize_row, main.rs:19255)
let job = match client.get_job(&job_id) {
    Ok(job) => job,
    Err(_) => {
        // §5.8 unknown: 何も変更せず保持し、次回再試行する。
        return Ok(BatchPollDisposition::InFlight);
    }
};
```

| 行 | 呼び出し | 現状 | 影響 |
|---|---|---|---|
| 14919 | `provider_scope_id()` (submit) | `?` で中断 | 一時エラーで `index` 全体が exit 2 |
| 14942 | `create_embedding_job()` (submit) | `?` で中断 | 同上 + **G1 の宙吊り行を作る** |
| 15004 | `get_job()` (poll) | `?` で中断 | **1 行の失敗が同 scope の残り全部の回収を止める** |
| 15039 | `fetch_inlined_results()` (poll) | `?` で中断 | 同上 |

加えて `adapter_to_kio` は `NotImplemented` 以外を全部 `KioError::schema` に潰すため、
**ネットワークエラーが `KIO-E-CONFIG-SCHEMA-001` (恒久的な設定エラー) として報告される**。

### 変更内容

**既存の分類器をそのまま使う。** [main.rs:13339](../crates/kio-cli/src/main.rs#L13339) の
`task_failure_from_adapter(error) -> TaskExecutionFailure { retry_kind, retry_after_ms }` が
`Auth`/`RateLimit`/`QuotaExceeded`/`Network`/`Io`/`ContractViolation`/`NotImplemented` を
すべて分類済み。新しい分類は書かない。

**submit 側 (`submit_embedding_batch_jobs`)** — その job だけ諦め、**他の job は続行**する。

- `provider_scope_id()` / `create_embedding_job()` の失敗は `?` をやめ、
  `task_failure_from_adapter` で分類 → メンバに遷移を記録 → `continue`。
- `AuthError` は `embedding_pause_transition()` 相当の Paused(auth) へ倒す
  (sync レーンと同じ扱い。認証不備は再試行で直らない)。
- それ以外は Failed(retryable) にして**予約は保持**する。F8 posture (reserve-before-send) を維持し、
  **回収は G1 の `ledger reconcile` に委ねる**。

**poll 側 (`poll_batch_embedding_jobs`)** — OCR と同一の作法にする。

- `get_job()` / `fetch_inlined_results()` の失敗は `outcome.inflight += 1` して `continue`。
  行は一切変更しない (§5.8 unknown = 保持して次回再試行)。
- **`?` を使わない**ので、1 行の失敗が残りの行の回収を止めない。

### テスト

| # | 内容 | 期待 |
|---|---|---|
| G2-1 | 2 job のうち 1 つ目の `create_job` が RateLimit | 2 つ目の job は作られる。index は exit 0 で完走 |
| G2-2 | `create_job` が Auth エラー | メンバが Paused(auth)。予約は保持 |
| G2-3 | 2 行のうち 1 つ目の `get_job` が Network エラー | **2 行目は回収される**。1 行目は state 1 のまま無変更 |
| G2-4 | `fetch_inlined_results` が失敗 | 行は state 1 保持・課金確定しない・次パスで再回収できる |

G2-3 が本丸 (head-of-line blocking の非回帰)。

---

## H2. `repair` の preview が本実行を拘束する

R24b で **3/3 系統一致・うち 2 件 fatal**。H2-4 (拘束) / H2-3 (列挙) / H2-6 (registry) は**同根**で、
「preview が返した対象リストそのものを本実行へ渡す」形にすれば同時に解ける。

### 現状

```rust
let preview = verify_objects::prune_orphans(&repo, true)?;   // 数える
confirm_repair_prune(..., 件数, skip_prompt)?;               // 件数だけ見せて問う
let prune = verify_objects::prune_orphans(&repo, false)?;    // もう一度スキャンして消す
```

2 回のスキャンの間に対象が増えれば**承諾していない対象まで消える**。
`prune_orphans` は探索と削除が同じループに同居し `dry_run` で分岐している
([verify_objects.rs:2168-2240](../crates/kio-cli/src/verify_objects.rs#L2168)) ため、
現状の形のままでは拘束できない。

### 変更内容

**1. plan / apply に分割する** (`verify_objects.rs`)

```rust
pub struct PruneOrphansPlan {
    pub status: String,                 // "pruned" | "blocked"
    pub blocked_by: Option<String>,
    pub prepared: Vec<String>,          // 削除対象の hash
    pub images: Vec<String>,
    pub cache_dirs: Vec<PathBuf>,
}
pub fn prune_orphans_plan(repo: &Repository) -> Result<PruneOrphansPlan>;
pub fn prune_orphans_apply(repo: &Repository, plan: &PruneOrphansPlan) -> Result<PruneOrphansReport>;
```

`dry_run` 引数は消える。**apply は plan に入っている対象しか触らない** (再スキャンしない)。
`PruneOrphansReport` の件数フィールドは実際に消せた数を返す (対象が既に消えていれば減る)。

**2. `registry_prune` も同型に** — `RegistryPrunePlan { rows: Vec<...> }` を返し、
apply はその行だけを DELETE する。

**3. 確認プロンプトが列挙する** (`main.rs`)

`confirm_repair_prune(what, count, yes)` を `confirm_repair_prune(what, &targets, yes)` へ。
06 §1 の「削除対象を先に列挙して見せてから問う」を満たす。
長大化を避けるため **先頭 20 件を列挙し残りは件数**で示す (`purge` の preview と同じ作法)。

```
repair verify-objects --prune-orphans will permanently remove 23 item(s):
  prepared  sha256:1a2b…  (12)
  image     sha256:9f8e…  (8)
  cache     ~/.cache/kio/open/…  (3)
  … and 3 more
Proceed?
```

**4. blocked の JSON に `error_code` を載せる** (H2-5、3/3 一致)。
`__exit_code: 3` だけで `error_code` が無い非対称を解消する。

### テスト

| # | 内容 | 期待 |
|---|---|---|
| H2-a | preview 取得 → **新しい orphan を作る** → apply | **新しい orphan は消えない** (拘束の本体) |
| H2-b | 非対話 `--yes` 無しで拒否 | 何も消えない (既存テストの維持) |
| H2-c | プロンプト文に対象が列挙される | 件数だけでない |
| H2-d | `registry-prune` の拒否 | 行が残る (R24b-son-4 が「テストが無い」と指摘) |
| H2-e | blocked 時の JSON | `error_code` と `__exit_code` が整合 |

---

## 検証と完了条件

各段階で以下を通す。

```bash
cargo test --workspace && cargo clippy --workspace --all-targets --all-features -- -D warnings && cargo fmt --all --check
```

- **G1 完了条件**: G1-1 の再現が `unlistable: 1` → `batch_found: 1` に変わること。
  実機 (mock seam) で `index --online` (create_job 失敗) → `ledger reconcile` → 行に job id が入る、を通す。
- **G2 完了条件**: G2-3 で「2 行目が回収される」こと。`?` による中断が 4 箇所から消えていること
  (`grep -c 'adapter_to_kio' ` が submit/poll 区間で 0)。
- **H2 完了条件**: H2-a が落ちないこと。既存の PB12/PB13/PB15/PB25 が全部 green のまま。

## 本計画で扱わないもの

R24 裁定の F5 (レーン分裂) / F7 (profile 不一致) / F8 (未知 state) / F9 (list_jobs 5000 件) /
H2-7 (reachability 読取り失敗) は [step4b-backlog.md §6](step4b-backlog.md) に残す。
F6 (inline 上限) は実測で棄却済み — 実コーパスは **scope あたり最大 14 chunk / 最大 3,405 字**で、
512 メンバ・16MB の上限に遠く及ばず、かつクライアント側が両上限をテスト付きで強制している。

---

## 実施結果 (2026-07-25)

**3 件すべて実装・検証完了。** テスト **1,318 passed / 0 failed** (着手時 1,312 → 新規 6)、
clippy `-D warnings --all-features` 警告 0、fmt クリーン。

| | 状態 | 新規テスト |
|---|---|---|
| G1 | 完了 | `reconcile_recovers_a_row_stranded_in_the_job_creation_window` / `reconcile_does_not_claim_a_foreign_provider_job` |
| G2 | 完了 | `a_submit_failure_does_not_abort_the_invocation` / `an_unreachable_row_does_not_block_collection_of_the_others` |
| H2 | 完了 | `apply_removes_only_what_the_plan_listed` / `a_blocked_plan_applies_nothing` |

### 計画からの差分

- **G1 の逆関数は新設不要だった** — `display_name_intent_token` が既に存在し、
  往復テストも既にあった。配線のみで完了。
- **G2 は新しい分類器を書かず**、既存の `task_failure_from_adapter` を再利用。
  同期レーン側の 3 分岐も共通ヘルパ `embedding_failure_transition` に寄せ、
  2 つのレーンが分岐で乖離できないようにした。
- **mock に `fail_job_names` を追加した** (計画外)。既存の `fail_phase` は
  all-or-nothing で「複数行のうち 1 行だけ不達」を表現できず、G2 の本丸
  (head-of-line blocking の非回帰) を固定できなかったため。
- **H2-5 (blocked の error_code) も同時に実施** — 同じ関数を触るため分離する理由が無かった。
  `KIO-E-PRUNE-ORPHANS-BLOCKED-001` を新設。

### 実機確認

```
G1: index --online (create_job 失敗) → ledger reconcile
    unlistable: 1  →  batch_found: 1   行に batch_job_id が入る
G2: 2 行のうち batches/blocked が不達
    batches/ok は state 2 で回収済み / batches/blocked は state 1 で保持 (無変更)
H2: repair verify-objects --yes      → KIO-E-CONFIG-USAGE-001 (旧: 受理して無効)
    blocked な prune の JSON          → KIO-E-PRUNE-ORPHANS-BLOCKED-001 が載る
```

### 残件

[step4b-backlog.md §6.2](step4b-backlog.md) の F5/F7/F8/F9/F10/H2-7/H2-8。
いずれも Phase 2 の課金経路上には無い。
