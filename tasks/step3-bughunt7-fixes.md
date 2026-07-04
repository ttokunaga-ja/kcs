# 探索型 4+ エンジン監査 (第 7 ラウンド) の裁定 (2026-07-04、main = 2c42d8d)

防御的セキュリティ監査。貼り付けランブックは R5 時点だったが、現在の main には R6 修正
(`tasks/step3-bughunt6-fixes.md`, `2715246`) が入っていたため、R6 も既知扱いにして探索した。
Claude 系 subagent は本セッションで使用できなかったため、利用可能な GPT 系 6 ワーカー相当に置換。
初期状態は `cargo test --workspace` 全 green (307 tests)。新規 **5 件** (1 critical + 4 major) を採択。
すべてオーケストレータが実機再現または file:line で検証済み。

却下 / 保留:
- `--online` が `index --revoke-network` の `allow_network=false` を上書きしない件は fail-closed で、
  実装コメントも「revocation gates every adapter off」としているため今回の修正対象外。docs の優先順位表との
  緊張は別途仕様整理。
- `parse_utc_seconds` が `2026-02-31T00:00:00Z` を正規化する件は、現行の本番経路では生成済み時刻の
  backoff 計算にしか使われず、外部入力 `next_retry_at` は文字列比較なので minor 堅牢性として保留。
- `normalized_view_path` の短 hash slice panic は public helper の defense-in-depth だが、主要 caller は
  検証済み raw_hash から来るため保留。

---

## 必須修正 R7-1-R7-5

### R7-1 [critical] Tier B `--send-secrets` 承認が `secrets-approved.jsonl` の存在だけで成立し、空ファイル/別 scope コピーで candidate secret が online 送信される
発見: GPT-5.4-B / 自己検証

- **根本**: `secrets_send_approved` (`crates/kcs-cli/src/main.rs`) が
  `.kcs/secrets-approved.jsonl.is_file()` だけを見ている。`write_secrets_approval` は `scope_id` を
  JSONL に書くが、読み取り側が scope 束縛を検証していない。
- **再現**:
  1. `api_secret.md` を含む scope で `kcs init`。
  2. 空の `.kcs/secrets-approved.jsonl` を作る。
  3. `KCS_TEST_GEMINI_EMBED=mock kcs index --approve --online --json`。
  4. `.kcs/quarantine.jsonl` が `approval_method:"send_approved"` になり、Tier B ファイルの
     embedding task が `status:"done"` になる。
- **期待 vs 実際**: 期待 = 当該 scope で明示 `--send-secrets` した JSONL 行だけが hold を解除する。
  実際 = 空ファイルや別 scope のコピーで candidate secret text が embedding adapter へ送信されうる。
- **修正**: `secrets_send_approved` は JSONL を読み、現在の `scope_id` + `approval_method:"send_secrets"`
  の一致行を必須にする。

### R7-2 [major] multi-scope search の query embedding opt-in が呼び出し元 scope だけで判定され、target scope の永続 opt-in を見ない
発見: 自己検証

- **根本**: `run_search` の `embedding_opt_in` は `persistent_network_allowed_for(&repo, adapter_id)` だけで、
  default/global search が列挙した `exec_scopes` それぞれの embedding opt-in を確認しない。
- **再現**:
  1. scope A は `KCS_TEST_GEMINI_EMBED=mock kcs index --approve --online` で永続 opt-in。
  2. scope B は `KCS_TEST_GEMINI_EMBED=mock kcs index --yes --online` で一回だけ embedding 生成
     (`network_opt_in:false`)。
  3. A から `KCS_TEST_QUERY_EMBED_TRACE=$trace KCS_TEST_GEMINI_EMBED=mock kcs search sharedterm --json`。
  4. trace に query が記録され、JSON は `resolved_mode:"hybrid"` かつ `searched_scopes` に B を含む。
- **期待 vs 実際**: 期待 = vector/hybrid で query を online embedding に送るなら、検索対象 scope すべてが
  当該 embedding adapter へ永続 opt-in 済みであること。実際 = 呼び出し元 A の opt-in だけで B も
  vector/hybrid 対象になる。
- **修正**: vector availability 判定で `exec_scopes` 全体の per-scope embedding opt-in を確認し、
  未承認 scope が混ざる場合は text fallback (`embedding_opt_in_required`) にする。

### R7-3 [major] embedding 失敗が retry policy を永続化せず、rate_limit/network/quota が即時 retry ループになる
発見: GPT-5.4-E / 自己検証

- **根本**: `fail_embedding_tasks` は `status` と `fallback_reason` だけを書き、`attempts` と
  `next_retry_at` を更新しない。`embeddable_task_state` / `batch retry` は `next_retry_at` と
  attempts を見るため、rate limit でも毎回即時 retry 可能になる。
- **再現**:
  `KCS_TEST_GEMINI_EMBED=rate_limit kcs index --approve --json` 後の embedding task は
  `status:"failed", attempts:0, next_retry_at:null, fallback_reason:"rate_limit"`。
  `batch retry` 後も同じで `tasks_updated:1` が繰り返される。
- **期待 vs 実際**: 期待 = markdownize と同じ retry policy に従い attempts 増加と backoff が残る。
  実際 = retry state が失われ、retry budget/backoff が機能しない。
- **修正**: embedding failure 更新時に `RetryErrorKind` を渡し、retryable/max_attempts に応じて
  `attempts += 1` と `next_retry_at` を保存する。

### R7-4 [major] `repair --rebuild-db` が unknown flag / 余剰引数を黙殺し、成功 JSON を返す
発見: GPT-5.3-Codex-Spark-F / 自己検証

- **根本**: `run_repair` は `args.iter().any(|arg| arg == "--rebuild-db")` だけを見ており、
  残り引数を検証しない。
- **再現**: `kcs repair --rebuild-db --definitely-invalid EXTRA --json` が exit 0 で
  `{"status":"rebuilt"}` を返す。
- **期待 vs 実際**: 期待 = unknown flag / extra operand は exit 2。将来の `--verify-objects` 等も
  未実装なら明示エラー。実際 = Agent が未実行の検査を成功と誤認する。
- **修正**: strict parser を導入し、`--rebuild-db` と既存互換の no-op `--yes` だけを許可。Step4 系 flag は
  `KCS-E-CONFIG-NOT-IMPLEMENTED-001`、未知/余剰は invalid usage。

### R7-5 [major] embedding profile 変化後、profile-blind な `chunk_vec`/task 判定で互換性不整合が自己修復しない
発見: GPT-5.4-E / 自己検証

- **根本**: embedding identity hash は `profile_hash` を含む一方、未 enrichment 判定は
  `chunk_vec.chunk_id IS NULL`、task key は `embedding:<chunk_id>` だけ。旧 profile の `chunk_vec`
  があると、現 profile で再 enqueue / re-embed されない。
- **再現**:
  1. `KCS_TEST_GEMINI_EMBED=incompatible_profile kcs index --approve --json`
  2. `KCS_TEST_GEMINI_EMBED=mock kcs index --approve --json`
  3. `KCS_TEST_GEMINI_EMBED=mock kcs search alpha --json`
  4. `resolved_mode:"text"`, `fallback_reason:"embedding_profile_incompatible"` のまま。
     SQLite `embeddings.profile_hash` も旧 `...incompat` のみ。
- **期待 vs 実際**: 期待 = 現 profile に戻した index で同一 chunk が再 embedding され、vector/hybrid が復帰する。
  実際 = 旧 profile の derived vector が存在するだけで再生成が止まる。
- **修正**: live chunk の embedding 欠落判定を現 profile に束縛し、`chunk_vec` が旧 profile 由来の場合は
  再 enqueue / re-embed する。

---

## 探索したが問題なしと確認した領域
- R6-1 の `approvals.jsonl` scope/tool_id 束縛は有効。
- `view/open/reindex/search` は R6-4 修正後、unknown flag / 余剰引数を拒否。
- `--text` 検索では query embedding trace が発火しない。
- R5 Q1 の chunks.jsonl torn tail 自己修復、R6-2/R6-8 の normalized/tool-lock atomicity は今回の範囲で新規破綻なし。
