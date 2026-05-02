# 05 Runtime

統合元: `hybrid.md` (検索モード) + `commit_snapshot.md` (commit_type, GC, purge) + 一部 `read_only.md` (検索結果での書き込み境界) + 一部 `productization_notes.md` (運用)。

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
embedding profile_hash 不一致 → text fallback (KCS-E-SEARCH-VEC-INCOMPAT)
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

```
RRF_score(c) = 1 / (k + rank_text(c)) + 1 / (k + rank_vector(c))
default k = 60
```

`.kcs/config.toml [search.rrf]` で `k` と weight を上書き可。

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

## 1.5 ページング / カーソル

```bash
kcs search "..." --limit 20
kcs search "..." --limit 20 --offset 20         # 同一 snapshot 内
kcs search "..." --limit 20 --cursor <token>    # snapshot 越し安全
```

`cursor` は `(snapshot_id, last_score, last_chunk_id)` の opaque エンコード。index 更新中でも結果順序が安定。レスポンスに `next_cursor` を含める。

## 1.6 Snapshot 越し検索 (`--at`)

```
--at <commit>           指定 commit 時点で indexed だった chunks のみ対象
--at <commit> --vector  指定時点の embedding profile が現在と互換ならOK、
                        非互換なら KCS-E-SEARCH-VEC-INCOMPAT
                        (fail_behavior=fallback で text に落ちる)
--all-history           全 commit を横断 (削除済み・移動済み含む)
--include-deleted       現在 working tree に存在しないファイルも対象
--since <duration>      `--since 7d` のように期間指定
```

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
  "paging": { "limit": 20, "offset": 0, "next_cursor": "eyJzbmFwIjoi..." },
  "snapshot_at": "kcs_01H...",
  "results": [
    {
      "chunk_hash": "sha256:...",
      "evidence_pointer": {
        "commit": "kcs_01H...",
        "tree": "tree_abc",
        "raw_hash": "sha256:...",
        "tool_profile_hash": "sha256:...",
        "chunk_hash": "sha256:...",
        "path_at_commit": "docs/report.pdf",
        "heading_path": ["認証仕様", "API Token"],
        "char_start": 1200,
        "char_end": 1500
      },
      "score": 0.87,
      "scope_path": ".kcs at /Users/foo/Research/.kcs"
    }
  ]
}
```

`scope_path` で正本の `.kcs` を必ず明示する (truth vs cache の不変条件)。

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
| auto | 自動 snapshot (定期 / 取り込み完了時) | false | full (個数 / 時間で減衰) |
| imported | 外部 KCS から取り込んだ commit | true | none |
| migrated | format 変換時の中間 commit | false | shallow |
| repaired | repair 操作の中間 commit | false | shallow |
| merged | 共有版マージ (Phase 5+) | true | none |
| purged | 法務・秘匿削除後の commit | true | none |

`semver MAJOR でも値域 bump しない` 契約は他フィールドより強い保証。

## 2.2 GC

```
gc_policy(commit_type):
  auto      → full      (commit object 削除可)
  migrated  → shallow   (tree のみ破棄、commit object は残す)
  repaired  → shallow
  manual    → none
  imported  → none
  merged    → none
  purged    → none
```

`shallow` は履歴 DAG の連続性を保つため commit を残し tree のみ破棄する。

`shallow` 後の commit を `kcs view <commit>` した場合:

```
- メタ情報 (id, parents, message, timestamp, commit_type) は表示
- tree は "shallow: tree discarded" と表示
- kcs restore <shallow-commit> は KCS-E-COMMIT-SHALLOW-001 で拒否
- kcs diff <a> <b> で片方が shallow なら全ファイル差分は不能と明示
```

## 2.3 GC スケジューリング

GC は **on-demand を基本** とし、自動実行は idle 検出時のみ。常時バックグラウンドで動かさない (`kcs index` 中の I/O / lock 競合回避)。

```toml
[gc]
mode = "on_idle"               # "on_idle" | "manual_only" | "after_index"
idle_threshold_seconds = 300
max_runtime_seconds = 60
```

## 2.4 Tiered Retention

`commit_type=auto` のみ tiered retention を適用 (`manual/imported/merged/purged` は常に残す):

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

## 3.3 Dead Evidence Pointer のセマンティクス (確定待ち)

「Evidence Pointer の不変性」と「法務 purge」の緊張領域。仕様は [08-evidence-pointer-spec.md §4](08-evidence-pointer-spec.md)、未確定論点は [09-mvp-scope.md §5.3](09-mvp-scope.md)。

採用案 (確定後に 05-runtime.md へ昇格):

```
purge 後の pointer 解決:
1. raw_hash が tombstone を持つ → tombstone レスポンス
   {
     "status": "purged",
     "purged_at": "2026-04-25T12:00:00Z",
     "purged_reason": "legal" | "privacy" | "misingest",
     "commit": "kcs_01H...",
     "raw_hash": "sha256:..."
   }
2. raw_hash が完全削除 (履歴書き換え) → not_found
   error_code: KCS-E-PURGE-NOT-FOUND-001

検出 API:
kcs evidence verify <pointer> [--strict]
  → status=alive | tombstoned | not_found
```

## 3.4 purge スコープは `.kcs` 単位

横断 GC を持たないので、purge も **その `.kcs` 内に閉じる**。別 `.kcs` (= ユーザーが意図的に複数フォルダへ配置) に同一 raw_hash がある場合、それは別 purge 操作で消す必要がある。これは将来コスト低下/ローカル LLM 進展前提で容認 ([01-positioning.md](01-positioning.md))。

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

# 5. 並行性 / Locking

```
.kcs/.lock                     プロセスレベル排他 (kcs index, kcs gc, kcs purge)
.kcs/index/sqlite.db (WAL)     reader と writer の整合性
```

`kcs index` と `kcs search` の同時実行は許容 (SQLite WAL でリーダーは旧スナップショット)。`kcs index` の二重起動は `.kcs/.lock` で防止。

# 6. 観測 (Observability)

```
~/.local/share/kcs/logs/
  events.jsonl       重要イベント (commit, gc, purge, schema migration)
  metrics.jsonl      数値メトリクス (デフォルト 1h 間隔)
  errors.jsonl       error_code 付きの全エラー
.kcs/logs/
  access.jsonl       検索アクセスログ (redact_logs=true で機微マスク)
```

各行 JSON 必須フィールド: `ts, level, code, component, message, context`。詳細は [productization_notes.md §12.6](productization_notes.md)。

# 7. Auto Commit (Phase 3 範囲)

```
- ユーザー操作なし時に一定間隔で auto snapshot を作る (commit_type=auto)
- snapshot 対象は indexed scope の現在 working tree
- auto commit は tiered retention で減衰する (§2.4)
- manual commit は auto を吸収しない (auto は GC で消えるが履歴 DAG の中間点として残る)
```

`.kcs/config.toml`:

```toml
[snapshot.auto]
enabled = true
interval_seconds = 1800     # 30 分ごと
on_change_threshold = 50    # 50 ファイル以上の変更で即時 snapshot
```
