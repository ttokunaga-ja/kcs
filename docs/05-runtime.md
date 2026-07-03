# 05 Runtime

統合元: `research/hybrid.md` (検索モード) + `research/commit_snapshot.md` (commit_type, GC, purge) + 一部 `research/read_only.md` (検索結果での書き込み境界) + 一部 `research/productization_notes.md` (運用)。いずれも正本ではない (経緯参照用)。

---

# 1. 検索

## 1.1 モード

```
text   FTS5 (BM25)         常に利用可能
vector sqlite-vec          embedding 互換性あり時に利用可能
hybrid RRF(text, vector)   両方利用可能時のみ。auto モードがデフォルト
```

`.kcs/config.toml`:

```toml
[search]
default_mode = "auto"            # "auto" | "text" | "vector" | "hybrid"
fail_behavior = "fallback"       # "fallback" | "error" | "warn"
```

`auto` の解決順:

```
両方利用可能 → hybrid
vector のみ NG → text
embedding profile_hash 不一致 → text fallback (KCS-E-SEARCH-VEC-INCOMPAT-001)
両方不可 → error (KCS-E-SEARCH-VEC-UNAVAIL-001)
```

## 1.2 CLI

```bash
kcs search "..."             # auto
kcs search "..." --text      # text only
kcs search "..." --vector    # vector only。失敗時は error
kcs search "..." --hybrid    # hybrid 強制。vector 失敗時は fail_behavior に従う
kcs search "..." --no-vector # 明示無効
```

## 1.3 RRF (Reciprocal Rank Fusion)

候補取得: text / vector 各バックエンドから検索対象集合 (§1.6) 内の上位 `candidate_depth` 件 (デフォルト 200) を取得し、和集合を候補プールとする。1 クエリで返しうる結果の上限は候補プール件数 (ページングしても超えない)。

```text
RRF_score(c) = w_text / (k + rank_text(c)) + w_vector / (k + rank_vector(c))
default: k = 60, w_text = 1.0, w_vector = 1.0
```

- `rank_*` は各バックエンド内の 1 始まり順位。バックエンド内の同点は chunk_id 昇順で順位を確定する
- 片方のバックエンドにしか現れない候補は、現れない側の項を 0 とする
- `RRF_score` の同点は chunk_id 昇順
- text-only / vector-only モードでは fusion せず当該バックエンドの順位をそのまま使う

```toml
[search.rrf]
k = 60
w_text = 1.0
w_vector = 1.0
candidate_depth = 200
```

## 1.4 多様化 (MMR / Dedup)

素の RRF だけでは同一原文の隣接 chunk が上位を独占しやすいので、後処理で多様化する。

```toml
[search.diversify]
enabled = true
strategy = "mmr"            # "mmr" | "group_by_raw_hash" | "off"
mmr_lambda = 0.7            # 1.0=relevance only, 0.0=diversity only
max_per_raw_hash = 3
```

MMR 選択則:

```
score(c) = λ * relevance(c) - (1-λ) * max_{c' ∈ selected} similarity(c, c')
similarity = vector cosine, または heading_path / section_id の Jaccard
```

適用範囲と決定性:

- MMR は候補プールの RRF 上位 `mmr_depth` 件 (デフォルト 100、`candidate_depth` 以下) に対して **1 回だけ** 適用し、並べ替え済みの**確定順序**を得る。`mmr_depth` 以降の候補は RRF 順のまま末尾に接続する
- `relevance(c)` = RRF スコアを **MMR 候補プール内で min-max 正規化した値** ([0,1]。全候補が同スコアなら一律 1.0。2026-07-03 確定、step3a §C の決定性論点解消 — 生の RRF スコア (最大 ~1/k) をそのまま使うと mmr_lambda の意味が損なわれるため)。`similarity` は embedding の cosine。embedding が無い場合 (text-only 検索) は MMR を適用せず RRF 順のままとする (ただし `max_per_raw_hash` の dedup は embedding 非依存であり text-only でも適用する)。MMR score の同点は RRF 順、さらに同点は chunk_id 昇順
- `max_per_raw_hash` は確定順序の構築時に結果ストリーム全体へ適用する (ページを跨いで raw_hash あたり最大 N 件)
- 入力 (chunk 集合・query・設定) が同じなら確定順序は常に同一 (決定論)。これがページング (§1.5) の前提

```toml
[search.diversify]
# (既存キーに追加)
mmr_depth = 100
```

## 1.5 ページング / カーソル

```bash
kcs search "..." --limit 20
kcs search "..." --limit 20 --offset 20         # 同一 snapshot 内
kcs search "..." --limit 20 --cursor <token>    # snapshot 越し安全
```

ページングは「確定順序 (§1.4) の決定論的再計算」で実現する。cursor に MMR の selected 集合や score は持たない。レスポンスに `next_cursor` を含める。本節の定義は単一 scope 内の sub-cursor であり、複数 scope 横断時の cursor 全体構造 (opaque token、`scope_mode` / `query_hash`) は §1.8 で定義する。

scope ごとの sub-cursor は `{scope_id, snapshot_commit, max_rowid, consumed}`:

- `snapshot_commit`: 当該 scope の検索対象 commit (§1.7 snapshot_at)。2 ページ目以降も同じ commit の tree_entries ([04-pipeline.md §4.5](04-pipeline.md)) で絞る
- `max_rowid`: cursor 発行時点の chunks 最大 rowid。`--all-history` / `--include-deleted` では `rowid <= max_rowid` で chunk 集合を固定する (chunks 行は append-only ([04-pipeline.md §4.1](04-pipeline.md)) なので単調増加)
- `consumed`: 当該 scope から既に返した件数
- `query_hash` (token 全体に 1 つ、§1.8) が不一致の cursor は `KCS-E-SEARCH-CURSOR-001` で拒否する

2 ページ目以降は同一の候補取得 → RRF (§1.3) → MMR (§1.4) を再計算し、consumed 件を skip して続きを返す。順序安定性の根拠は SQLite WAL のスナップショット分離**ではなく**、「commit 単位で固定された chunk 集合 + 決定論的な順位計算」である。CLI 呼び出しを跨いでも成立する。

`--offset` は cursor の糖衣であり、同じ再現規則で確定順序の `offset` 位置から `limit` 件を返す。確定順序 (= 候補プール) の末尾を超えたら `next_cursor: null` で終端。

## 1.6 Snapshot 越し検索 (`--at`)

```
--at <commit>           指定 commit 時点で indexed だった chunks のみ対象
--at <commit> --vector  指定時点の embedding profile が現在と互換ならOK、
                        非互換なら KCS-E-SEARCH-VEC-INCOMPAT-001
                        (fail_behavior=fallback で text に落ちる)
--all-history           全 commit を横断 (削除済み・移動済み含む)
--include-deleted       現在 working tree に存在しないファイルも対象
--since <duration>      `--since 7d` のように期間指定
```

各モードの検索対象 chunk 集合 (実装規範。schema は [04-pipeline.md §4](04-pipeline.md)):

```text
デフォルト          chunks ⨝ tree_entries(HEAD)     on (raw_hash, tool_profile_hash, gen)
--at <commit>       chunks ⨝ tree_entries(<commit>) on (raw_hash, tool_profile_hash, gen)
--include-deleted   デフォルト集合 ∪ (chunks ⨝ files[status='deleted'] on raw_hash。
                    tool_profile_hash / gen は当該 raw_hash の最新 normalized instance)
--all-history       全 chunk 行 (絞らない)
--since <duration>  --all-history 集合を chunks.created_at >= now - <duration> で絞る
```

共通フィルタ: `chunking_config_hash` が現行値の chunk のみ ([04-pipeline.md §4.6](04-pipeline.md))。purge 済み raw_hash の chunk 行は物理削除済みのため自然に除外される。

- `--include-deleted` が加えるのは「現在 working tree に存在しないファイルの**最終版**」のみ (files 行が保持する最後の raw_hash、[03-data-model.md §8](03-data-model.md))。途中版まで遡るのは `--all-history` の役割
- chunk 行が検索対象になるのは `kcs index` 成功完了時の auto snapshot (§8.1) 作成後。indexing 途中の chunk はどのモードでも返さない。auto snapshot 作成時に新規 chunk 行へ `first_seen_commit` を刻む ([04-pipeline.md §4.1](04-pipeline.md))
- shallow 化済み commit への `--at` の失敗規則は §2.2

過去 snapshot の embedding 再生成は別操作 (`kcs reindex --at`)。

## 1.7 AI Agent レスポンス契約

```json
{
  "query": "認証仕様",
  "requested_mode": "auto",
  "resolved_mode": "text",
  "fallback": true,
  "fallback_reason": "embedding_endpoint_not_configured",
  "error_code": "KCS-E-SEARCH-VEC-UNAVAIL-001",
  "diversify": { "strategy": "mmr", "mmr_lambda": 0.7 },
  "paging": { "limit": 20, "next_cursor": "eyJ2IjoxLCJzY29wZXMiOl..." },
  "searched_scopes": [
    { "scope_id": "scope_01J8ZQ...", "scope_path": "/Users/foo/Research/.kcs", "snapshot_at": "sha256:9f2c..." }
  ],
  "excluded_scopes": [],
  "index_status": {
    "enriched_ratio": 0.42,
    "pending_enrichment_tasks": 3120,
    "budget_paused": true
  },
  "results": [
    {
      "chunk_hash": "sha256:...",
      "evidence_pointer": {
        "schema_version": 1,
        "commit": "sha256:9f2c...",
        "tree": "sha256:3f9a...",
        "raw_hash": "sha256:...",
        "tool_profile_hash": "sha256:...",
        "chunk_hash": "sha256:...",
        "path_at_commit": "report.pdf",
        "heading_path": ["認証仕様", "API Token"],
        "char_start": 1200,
        "char_end": 1500,
        "scope_id": "scope_01J8ZQ..."
      },
      "evidence_uri": "kcs://scope_01J8ZQ.../sha256:9f2c.../sha256:.../sha256:.../sha256:...",
      "score": 0.87,
      "scope_path": "/Users/foo/Research/.kcs"
    }
  ]
}
```

`evidence_pointer` は [08-evidence-pointer-spec.md §2](08-evidence-pointer-spec.md) の schema を **そのまま** 埋め込む。root (`.kcs`) の信頼は `evidence_pointer.scope_id` を正とし、`results[].scope_path` は解決を高速化する表示・ヒント用の絶対パスである (truth vs cache の不変条件。解決手順は [08-evidence-pointer-spec.md §3.1](08-evidence-pointer-spec.md))。

`evidence_uri` は Evidence Pointer の正規テキスト形 ([08-evidence-pointer-spec.md §2.3](08-evidence-pointer-spec.md)) であり、そのまま `kcs open` / `kcs view` / `kcs evidence verify` の引数に渡せる。

`index_status` は AI 強化 (Markdownize / Embedding) が全対象に行き渡っていないときのみ必須 (`enriched_ratio < 1.0`)。人間向け表示では「AI 強化 42% (budget により一時停止中)」のような 1 行警告に翻訳する。

`snapshot_at` と `evidence_pointer.commit` の決定規則:

- `searched_scopes[].snapshot_at` = 当該 scope の検索対象 commit。デフォルト / `--all-history` / `--include-deleted` では検索時の HEAD commit、`--at` では指定 commit
- `evidence_pointer.commit`: chunk が当該 scope の `snapshot_at` の tree に live ならその commit。live でない chunk (`--all-history` の旧版、`--include-deleted` の削除済み分) は当該 chunk の `first_seen_commit` ([04-pipeline.md §4.1](04-pipeline.md))
- `path_at_commit` = `evidence_pointer.commit` の tree における path

これにより M3-2 の「path_at_commit と現在 path を併記」([09-mvp-scope.md §4](09-mvp-scope.md)) は、pointer.commit の tree と HEAD の tree_entries の 2 join で実装できる。

## 1.8 複数 scope 横断検索 (multi-scope search)

デフォルトの `kcs search` は scope_registry に登録された全 indexed scope を対象とする ([06-cli-spec.md §3](06-cli-spec.md))。各 `.kcs` は独立した index (sqlite.db) を持つため、横断検索は次の実行モデルで行う。

### 対象 scope の列挙

1. scope_registry から `participates_in_global_search = true` の scope を列挙する
2. `--scope <path>` / `--descendants` 指定時は root_path の前方一致で絞り込む
3. 到達不能 / stale な scope (外部ドライブ切断等) は skip し、`excluded_scopes` に理由付きで記録する (検索全体はエラーにしない)

### 実行とマージ

1. scope ごとに独立にクエリを実行する。並列度は min(4, scope 数)、per-scope timeout は 2 秒 (いずれも config で上書き可)
2. scope 内では §1.1〜§1.4 の単一 scope 検索をそのまま実行し、RRF 済み上位 candidate_depth 件 (§1.3) を候補として返す
3. scope 間の統合は **rank ベース** で行う。各 scope の RRF スコア (rank のみから決まる) をそのまま比較して降順マージする。**BM25 / vector の raw スコアを scope 間で比較・正規化してはならない** (コーパス統計が index ごとに異なり比較不能)。同点は (scope_path, chunk_hash) の辞書順で安定化する
4. diversify (MMR / group_by_raw_hash, §1.4) は統合後の候補列に対して適用する
5. vector / hybrid の横断条件は [03-data-model.md §7](03-data-model.md) に従う。embedding profile が全 scope で一致しない場合、横断部分は text (BM25 rank) のみで統合し、`fallback_reason` に記録する

既知の限界: rank ベース統合は、関連文書の乏しい scope の 1 位と強い scope の 1 位を同格に扱う。MVP ではこれを容認する (結果に scope_path が必ず含まれるため判別可能)。scope 間の再ランクは v2 以降の検討事項。

### 設定

```toml
[search.multi_scope]
parallelism = 4                 # 同時にクエリする scope 数の上限
per_scope_timeout_seconds = 2   # 超過 scope は excluded_scopes (reason=timeout)
```

### 部分失敗と exit code

| 状況 | 挙動 | exit code |
| --- | --- | --- |
| 全 scope 成功 | 通常結果 | 0 |
| 一部 scope 失敗 / stale / timeout | 結果を返し `excluded_scopes` に記録 | 3 |
| 全 scope 失敗 | エラー (`KCS-E-SEARCH-SCOPE-ALL-FAILED-001`) | 4 |

### レスポンス契約の拡張

単一値の `snapshot_at` は採用せず、次の 2 フィールドを返す (§1.7 の例):

```json
{
  "searched_scopes": [
    { "scope_id": "scope_01J8ZQ...", "scope_path": "/Users/foo/Research/.kcs", "snapshot_at": "sha256:9f2c..." }
  ],
  "excluded_scopes": [
    { "scope_id": "scope_01K3AB...", "scope_path": "/Volumes/ext/Research/.kcs", "reason": "stale" }
  ]
}
```

`snapshot_at` は scope ごとの検索時点 snapshot (commit_hash, [03-data-model.md §8.1](03-data-model.md))。単一 scope 検索 (`--scope .`) でも同形式 (要素 1 個の配列) を返す。これは [06-cli-spec.md §9](06-cli-spec.md) の Agent API 保証 (searched_scopes / excluded_scopes / fallback_reason) と同一の契約である。

### cursor の multi-scope 拡張

§1.5 の cursor を per-scope sub-cursor の合成に拡張する:

```json
{
  "v": 1,
  "scope_mode": "all",
  "query_hash": "sha256:...",
  "scopes": [
    { "scope_id": "...", "snapshot_commit": "sha256:9f2c...", "max_rowid": 18234, "consumed": 40 }
  ]
}
```

cursor はこの JSON の JCS を base64url した opaque token として返す。

- `scope_mode` は検索対象 scope の指定方法 (all / `--scope` / `--descendants`)、`query_hash` は次の正準構成 (2026-07-03 確定、step3a §C-2): `"sha256:" + base16(sha256(JCS({ query: <NFC 正規化後のクエリ文字列>, mode: <解決後の実効 mode (text|vector|hybrid)>, scope_mode, scopes: <対象 scope_id の昇順配列>, rrf: <[search.rrf] の実効値 (k / candidate_depth / w_text / w_vector — 変更は確定順序を変えるため cursor 誤用検出の対象)>, diversify: <[search.diversify] の実効値>, time_travel: <--at/--all-history/--include-deleted/--since の実効値 (未指定キーは省略)> })))`。`limit` / `--offset` / `--cursor` / `--json` は**含めない** (ページング操作で hash が変わってはならない)。いずれも token 全体に 1 つで、別クエリ・別条件での cursor 誤用検出に使う (不一致は `KCS-E-SEARCH-CURSOR-001` で拒否、§1.5)
- `snapshot_commit` は当該 scope の検索時点 snapshot (commit_hash)、`max_rowid` は snapshot 時点で index に取り込まれていた chunk 行の上限 (snapshot 固定の再クエリに使う)、`consumed` は当該 scope から既に返した件数
- 次ページは各 scope を `snapshot_commit` に固定して再クエリし、consumed 件を skip してマージを継続する。マージは決定的 (RRF スコア降順 + 辞書順 tie-break) なのでページを跨いで再現可能
- cursor 中の `snapshot_commit` が shallow 化済み (tree 破棄) の場合、cursor の再計算は `KCS-E-COMMIT-SHALLOW-001` で失敗する (§2.2)。この場合は cursor なしの再検索を案内する

### 性能目標の前提

M3-1 の p95 < 5 秒 ([09-mvp-scope.md §4.1](09-mvp-scope.md)) は **20 scopes / 合計 10 万 chunk** を前提とする。scope 数が数百を超える構成は MVP の性能保証外とし、`--scope` での絞り込み、または利用頻度の低い scope の `participates_in_global_search = false` 設定を案内する。

# 2. Commit / Snapshot

## 2.1 commit_type 永続 enum

`commit_type` は **永久に変更しない契約**。SQLite CHECK 制約で固定:

```sql
commit_type TEXT NOT NULL CHECK (commit_type IN (
  'manual', 'auto', 'imported', 'migrated',
  'repaired', 'merged', 'purged'
))
```

| type | 用途 | protected | GC policy |
| --- | --- | --- | --- |
| manual | 明示 commit | true | none |
| auto | 自動 snapshot (取り込み完了時 = MVP / 定期 = Phase 4、§8) | false | shallow (個数 / 時間で tree を減衰) |
| imported | 外部 KCS から取り込んだ commit | true | none |
| migrated | format 変換時の中間 commit | false | shallow |
| repaired | repair 操作の中間 commit | false | shallow |
| merged | 共有版マージ (Phase 5+) | true | none |
| purged | 法務・秘匿削除後の commit | true | none |

`semver MAJOR でも値域 bump しない` 契約は他フィールドより強い保証。

## 2.2 GC

> GC (§2.2-2.6) の**実装は Phase 4+** ([09-mvp-scope.md §3.1](09-mvp-scope.md))。MVP (Step 1-4) では GC を実行せず (auto snapshot がまだ無く回収対象がほぼ発生しないため)、`gc_policy` × `commit_type` の対応 schema のみ Step 1 の設計時から契約として遵守する (§2.6)。

```text
gc_policy(commit_type):
  auto      → shallow   (tiered retention 満了で tree のみ破棄、commit object は残す)
  migrated  → shallow
  repaired  → shallow
  manual    → none
  imported  → none
  merged    → none
  purged    → none
```

**full (commit object の削除) はどの commit_type にも適用しない。** commit object は append-only であり、これを消す操作は KCS に存在しない (purge も commit / tree を書き換えない、§3.5)。

なお `kcs repair --verify-objects` ([10-operations.md §7.5](10-operations.md)) が生成する `repaired` commit は破損 object の再取り込みによる復旧点であり、その復元した raw object は GC 対象外 (§2.6)。したがって commit の tree が shallow 化されても復旧した raw 内容は保持され、object としては実効的に none 相当である。

`shallow` は履歴 DAG の連続性を保つため commit を残し tree のみ破棄する。

`shallow` 後の commit を `kcs view <commit>` した場合:

```text
- メタ情報 (commit_hash, parents, message, timestamp, commit_type) は表示
- tree は "shallow: tree discarded" と表示
- kcs restore <shallow-commit> は KCS-E-COMMIT-SHALLOW-001 で拒否
- kcs diff <a> <b> で片方が shallow なら全ファイル差分は不能と明示
- kcs search --at <shallow-commit> と、shallow 化 commit を snapshot とする
  cursor の再計算も KCS-E-COMMIT-SHALLOW-001 で失敗する (tree 全体を要するため)
- shallow commit を指す Evidence Pointer の解決は失敗しない
  (raw_hash / chunk_hash による直接解決、08-evidence-pointer-spec.md §3.1)
```

## 2.3 GC スケジューリング

GC は独立した常駐プロセスを持たない (§5 プロセスモデル)。実行契機は次の 3 つ:

1. `manual_only` (MVP デフォルト): `kcs gc` の明示実行のみ
2. `after_index` (Phase 4+ の GC 実行系実装後のデフォルト): `kcs index` / `kcs snapshot` の成功終了後、同一プロセス内で `max_runtime_seconds` を上限に実行する。上限到達で中断し、残りは次回に持ち越す (`kcs index` 実行中とは重ならないため I/O / lock 競合が起きない)
3. `on_idle` (Phase 4+): OS スケジューラ委譲の定期 auto snapshot 実行時 (§8)、直近の KCS 書き込み操作から `idle_threshold_seconds` 以上経過していれば便乗実行する

GC 実行系の実装自体は Phase 4+ (§2.6)。config schema は Step 1 の設計時から遵守する。

```toml
[gc]
mode = "manual_only"           # MVP デフォルト。"after_index" (Phase 4+ 実装後のデフォルト) | "on_idle" (Phase 4+)
idle_threshold_seconds = 300   # on_idle 用 (Phase 4+)
max_runtime_seconds = 60
```

## 2.4 Tiered Retention

`commit_type=auto` のみ tiered retention を適用する。retention 満了は **shallow 化 (tree 破棄)** であり commit object の削除ではない (`manual/imported/merged/purged` は tree も常に残す):

```toml
[gc.auto_retention]
keep_last_hours    = 24
keep_hourly_days   = 7
keep_daily_weeks   = 4
keep_weekly_months = 6
[gc.derived_retention]
keep_migrated_per_branch = 5
keep_repaired_per_branch = 5
```

## 2.5 並行性 / power-loss 安全性

```
- GC 中の新規 commit 受付は block しない (CoW 風 readonly snapshot 上で走る)
- object 物理削除は exclusive lock の短い critical section に限定
- power-loss 中断時は次回起動時に sweep 再開 (.kcs/gc/in_progress マーカーで検出)
```

## 2.6 GC の削除対象 (規範)

GC (tiered retention / `kcs gc --prune-unreachable` を含む) が削除してよいもの:

```text
- tree object (shallow 化対象 commit のもの)
- SQLite index / FTS など objects/ から再構築可能な cache
- どの commit からも参照されない中間 object (中断した index が残した prepared 等)
```

GC が削除してはならないもの:

```text
- commit object (append-only。§2.2)
- raw object / chunk object — これらを削除する唯一の経路は purge (§3)
```

raw / chunk を GC 対象外とするのは、Evidence Pointer の永続性契約 ([08-evidence-pointer-spec.md §6](08-evidence-pointer-spec.md)) を「purge されない限り」で成立させるため。ストレージ増は「原則として忘れない」設計の受容済みコスト。

なお GC の実行系 (tiered retention / on_idle / prune) の実装は Phase 4+ ([09-mvp-scope.md](09-mvp-scope.md))。本節の削除対象規範と §2.2 の gc_policy schema は Step 1 の DB / object 設計時から遵守する。tiered retention 導入までの auto commit の蓄積はディスク消費として容認する。

# 3. Purge (法務・秘匿・誤取り込み)

## 3.1 purge と archive の区別

```
archive: 履歴上は残し「現在は使っていない」状態。デフォルト操作。
purge:   履歴から物理的に消す。例外操作。commit_type=purged が記録される。
```

正当事由:

```
- 法令上の削除義務 (個人情報・GDPR の forget 権)
- 機密漏洩への対応 (誤って取り込んだ秘匿文書)
- 著作権・契約上の保持禁止
```

CLI:

```bash
kcs purge <path|raw_hash> --reason <legal|privacy|misingest|copyright|...>
# --reason は必須。--yes なしなら確認プロンプト
```

## 3.2 「忘れない」と purge の両立

KCS は「原則として忘れない」が、**purge は「忘れる」のではなく「消した事実を記録して忘れる」操作**。purge 後も:

```
- commit_type = "purged" の新 commit が記録される
- 誰が、いつ、どの正当事由で実行したかを保存
- 監査可能性は維持される (= 透明な忘却)
```

## 3.3 Dead Evidence Pointer のセマンティクス

「Evidence Pointer の不変性」と「法務 purge」の緊張領域。正本は [08-evidence-pointer-spec.md §4](08-evidence-pointer-spec.md)。残未決 (bulk verify スループット / 二重 purge) は [09-mvp-scope.md §5.3](09-mvp-scope.md)。以下は採用済みセマンティクスの要約。

```text
purge 後の pointer 解決:
1. raw_hash が tombstone を持つ → tombstone レスポンス
   {
     "status": "purged",
     "purged_at": "2026-04-25T12:00:00Z",
     "purged_reason": "legal" | "privacy" | "misingest",
     "purged_in_commit": "sha256:9f2c...",
     "raw_hash": "sha256:..."
   }
2. raw_hash が完全削除 (--erase-tombstone: tombstone 記録も残さない) → not_found
   error_code: KCS-E-PURGE-NOT-FOUND-001

検出 API:
kcs evidence verify <pointer> [--strict]
  → status=alive | tombstoned | not_found
```

## 3.4 purge スコープは `.kcs` 単位

横断 GC を持たないので、purge も **その `.kcs` 内に閉じる**。別 `.kcs` (= ユーザーが意図的に複数フォルダへ配置) に同一 raw_hash がある場合、それは別 purge 操作で消す必要がある。これは将来コスト低下/ローカル LLM 進展前提で容認 ([01-positioning.md](01-positioning.md))。

## 3.5 purge の機構 (何を消し、何を残すか)

purge は **object の物理削除 + tombstone 記録** であり、**履歴 DAG の書き換えではない**。

消すもの (対象 raw_hash について、全履歴にわたり):

```text
- raw object 本体 (objects/raw/ab/cd/<raw_hash>)
- 派生 artifact: prepared / normalized / chunk / embedding
  (normalized は同一 (raw_hash, tool_profile_hash) 配下の全 gen instance を対象とする)
- SQLite の chunks / embeddings 行と FTS エントリ
```

残すもの (不変):

```text
- すべての commit / tree object。commit / tree は書き換えない。
  DAG の再結線・tree entry の削除・連鎖再 hash は行わない。
- tree entry のメタデータ (path, raw_hash)。raw_hash から原文は復元できない。
- tombstone (.kcs/tombstones/ab/cd/<raw_hash>)。--erase-tombstone 指定時を除く。
```

追加されるもの:

```text
- commit_type=purged の新 commit (purge 実行後の working tree を指す)
```

tombstone は raw_hash をキーとする JSON レコードで、CAS object ではないため `objects/` の外に置く:

```json
{
  "raw_hash": "sha256:abc...",
  "purged_at": "2026-04-25T12:00:00Z",
  "purged_reason": "legal",
  "purged_in_commit": "sha256:9f2c..."
}
```

**制約 (明記)**: tree entry の `path` 文字列と `raw_hash` は履歴に残る。ファイル名そのものが秘匿対象であるケース (履歴書き換えが必要) は MVP 非対応。commit / tree の書き換えは content hash の連鎖再計算と無関係ファイルの Evidence Pointer 無効化を伴うため、対応する場合も v2+ の再設計事項とする。

# 4. Restore / Time-travel

## 4.1 Restore

```bash
kcs restore <evidence|path|commit> --to <dir>
```

**安全要件**:

```
- working tree への直接書き戻しは禁止 (--to <dir> 必須)
- 既存ファイル上書きは --force 必須 + 確認プロンプト
- restore は raw object をそのまま展開 (再 Markdownize しない)
- shallow commit からの restore は KCS-E-COMMIT-SHALLOW-001
- purged 対象は KCS-E-PURGE-NOT-FOUND-001 / tombstone
```

## 4.2 kcs view (過去版閲覧)

```bash
kcs view <evidence-at-commit-X>
kcs view <path> --at <commit>
```

過去 commit 時点の Markdown を再生成せず、当該 commit の object をそのまま返す (re-Markdownize しない)。

# 5. プロセスモデル (常駐なし)

KCS は **常駐 daemon を持たない**。すべての処理は CLI コマンドのプロセス内で完結する。

- interval 発火 (定期 auto snapshot, Phase 4) は OS スケジューラ (launchd / systemd user timer / Task Scheduler) から CLI を起動する委譲方式とする (§8.2)
- idle 検出 (GC on_idle, Phase 4+) も同様に委譲実行時に判定し、KCS 自身は常駐しない (§2.3)
- 同一 `.kcs` に対する多重起動は `.kcs/.lock` で防止する (§6)

# 6. 並行性 / Locking

```text
.kcs/.lock                     プロセスレベル排他 (書き込み系コマンド全般、下記)
.kcs/index/sqlite.db (WAL)     reader と writer の整合性
```

`.kcs/.lock` を取得するコマンド (書き込み系):

```text
kcs index / kcs snapshot (= kcs commit) / kcs tag (refs/tags 更新) / kcs gc / kcs purge /
kcs repair --rebuild-db / kcs move --accept
```

規約:

- 読み取り系 (search / log / view / inspect / evidence verify / restore / status / diff) は `.kcs/.lock` を取得しない。`kcs index` と `kcs search` の同時実行は許容 (SQLite WAL でリーダーは旧スナップショット)
- `.kcs/.lock` を取得できない場合、書き込み系コマンドは**待機せず即座に失敗する**: error code `KCS-E-STORE-LOCKED-001`、exit code 3 (retryable、[06-cli-spec.md §7](06-cli-spec.md))。lock ファイルには保持プロセスの pid と取得時刻を記録し、保持プロセスが存在しない stale lock は次の取得試行時に回収してよい。待機オプション (`--wait <seconds>`) は Phase 4+ 予約
- refs (refs/heads/main, refs/tags/*) の更新は `.kcs/.lock` 保持下で、temp file 書き込み + atomic rename により行う (部分書き込みを外部に見せない)
- `kcs repair --rebuild-db` 実行中の `kcs search` は、再構築完了までの間旧 sqlite.db (存在すれば) を読むか、`KCS-E-INDEX-REBUILDING-001` を返す。再構築の完了も atomic rename (sqlite.db.tmp → sqlite.db) で切り替える
- scope-registry.sqlite (~/.local/share/kcs/) は WAL モード + busy_timeout (デフォルト 5000ms) で複数プロセスの同時書き込みを直列化する。registry は cache であり ([03-data-model.md §4](03-data-model.md))、破損時は各 `.kcs` の rescan で再構築する

# 7. 観測 (Observability)

```
~/.local/share/kcs/logs/
  events.jsonl       重要イベント (commit, gc, purge, schema migration)
  metrics.jsonl      数値メトリクス (デフォルト 1h 間隔の集計に加え、下記の per-search 記録)
  errors.jsonl       error_code 付きの全エラー
.kcs/logs/
  access.jsonl       検索アクセスログ (redact_logs はデフォルト true、10-operations.md §12.6)
```

**検索 latency の per-search 記録** (2026-07-03 追記、step3a §C の解消。北極星 §4.1 の p50/p95/p99 計測の一次データ): `kcs search` は 1 回の実行ごとに metrics.jsonl へ 1 行を追記する。行はログ共通 envelope (必須 `ts, level, code, component, message, context`) に従い、metric 固有フィールドを加える — `{ "ts": <UTC>, "level": "info", "code": "KCS-M-SEARCH-001", "component": "search", "message": "search completed", "metric": "search.latency_ms", "value": <実測 ms>, "context": { "mode": <実効 mode>, "scope_count": <検索した scope 数>, "result_count": <返却件数> } }`。redact_logs 既定 (クエリ本文・path は記録しない) に従う。1h 間隔の集計メトリクスはこの一次データから導出してよい。

各行 JSON 必須フィールド: `ts, level, code, component, message, context`。詳細は [10-operations.md §12.6](10-operations.md)。

# 8. Auto Commit

## 8.1 MVP (Phase 1-3) の snapshot 契機

MVP での snapshot 生成契機は次の 2 つのみ (常駐プロセスは持たない、§5):

1. 明示的 `kcs snapshot` / `kcs commit` (commit_type=manual)
2. `kcs index` の成功完了時に同一プロセス内で auto snapshot を作る (commit_type=auto)。ただし tree_hash が現在の HEAD の tree と一致する場合は commit を作らない (no-op、[03-data-model.md §8.2](03-data-model.md))

## 8.2 定期 Auto Snapshot (Phase 4 範囲)

```text
- ユーザー操作なし時に一定間隔で auto snapshot を作る (commit_type=auto)
- 実行主体は常駐 daemon ではなく、OS スケジューラ (launchd / systemd user timer /
  Task Scheduler) から起動される CLI とする (§5)。多重起動・kcs index との競合は
  .kcs/.lock で排他する (§6)
- snapshot 対象は indexed scope の現在 working tree
- auto commit は tiered retention で減衰する (§2.4)
- manual commit は auto を吸収しない (auto は tiered retention 満了で shallow 化され tree を失うが、commit object は履歴 DAG の中間点として残る。§2.2)
- tree_hash 不変なら no-op (§8.1 と同じ)
```

`.kcs/config.toml`:

```toml
[snapshot.auto]                 # Phase 4 (定期 auto snapshot)
enabled = true
interval_seconds = 1800     # 30 分ごと
on_change_threshold = 50    # 50 ファイル以上の変更で即時 snapshot
```
