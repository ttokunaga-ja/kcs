//! `cost-ledger.sqlite` schema: DDL SQL-of-record (04-pipeline.md §5.4), device
//! path resolution, connection bootstrap (WAL + busy_timeout, same precedent as
//! `crates/kio-index/src/registry.rs`'s scope-registry.sqlite), and the shape
//! detection/self-heal machinery required by 10-operations.md §7.5.3 ("形状検出は
//! sqlite_master の CREATE 文 (列・CHECK 制約を含む) の canonical 比較で行う").

use std::collections::BTreeSet;
use std::path::{Path, PathBuf};
use std::time::Duration;

use rusqlite::{Connection, OptionalExtension};

use crate::{PipelineError, Result};

/// `04-pipeline.md §5.4` SQL-of-record, copied verbatim (comments included —
/// comments are inert for `CREATE TABLE`/`CREATE INDEX` and are stripped by
/// [`canonical_sql_tokens`] for shape comparison, so keeping them here is a
/// direct, driftable link back to the spec text rather than a paraphrase).
pub const CREATE_COST_LEDGER_SQL: &str = "CREATE TABLE cost_ledger (               -- 確定・推定課金の追記台帳 (行の UPDATE / DELETE 禁止)
    scope_id          TEXT NOT NULL,
    adapter_kind      TEXT NOT NULL,     -- 'markdownize' | 'embedding' | ...
    input_hash        TEXT NOT NULL,     -- §5.5 のタスク同一性キーと同じ組
    tool_profile_hash TEXT NOT NULL,
    submission_seq    INTEGER NOT NULL,  -- 投入の通算連番。**新しい外部投入の開始 (相 1) ごとに
                                         --  MAX+1 を採番** — 同一 attempt の回復中は不変 (§5.8)
    batch_job_id      TEXT NOT NULL,     -- 値規則: 実 job id。job id 不明の記帳 (期限超・abandon) は
                                         --  当該 intent_token (§5.8 の記帳済み判別の突合キー)。
                                         --  sync 呼出 (Batch 非対応 provider) は provider request id、
                                         --  無ければ当該 attempt の intent_token
    usd               REAL NOT NULL      -- estimated=1 の行は保守的な推定額 (NULL 禁止 — SUM が
        CHECK (usd >= 0 AND               --  負値も禁止 (cap の相殺・過少計上を防ぐ)
               usd < 1e999 AND            --  +Inf 拒否 (typeof は Inf を 'real' として通し SUM を汚染する)
               typeof(usd) IN ('integer', 'real')),
                                         --  NULL を無視すると budget 判定が過少 = 安全側の逆になる。
                                         --  typeof 検査: REAL affinity は TEXT 混入を通し SUM が 0.0
                                         --  扱いにする = cap 過少計上のため型も強制する
    estimated         INTEGER NOT NULL DEFAULT 0 CHECK (estimated IN (0, 1)),
    outcome           TEXT NOT NULL      -- DEFAULT を持たない — INSERT での明示を必須にする
        CHECK (outcome IN ('succeeded', 'contract_violation', 'expired', 'abandoned',
                           'submit_rejected', 'purged', 'unknown_settled',
                           'fallback_to_full')),
                                         -- 終端確定行の到達理由 (§5.8 の対応表と同一 Tx で必須記載。
                                         --  DEFAULT 'succeeded' を許すと省略記帳が成功に化け、
                                         --  ON CONFLICT 冪等の下で訂正不能になる)。
                                         --  reset (--reset-violations) 後も違反履歴が台帳に恒久に残る
    month             TEXT NOT NULL      -- 'YYYY-MM' (確定月配賦 — cap 集計キー。書式と月範囲も強制 —
        CHECK (month GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]'
               AND substr(month, 6, 2) BETWEEN '01' AND '12'),
                                         --  不正書式・00/13〜99 月は当月合算から漏れ cap を過少判定する)
    recorded_at       INTEGER NOT NULL,  -- UTC ミリ秒
    UNIQUE (scope_id, adapter_kind, input_hash, tool_profile_hash, submission_seq)
);";

pub const CREATE_IDX_COST_LEDGER_MONTH_SQL: &str =
    "CREATE INDEX idx_cost_ledger_month ON cost_ledger(month, scope_id, adapter_kind);";

pub const CREATE_BATCH_REQUESTS_SQL: &str = "CREATE TABLE batch_requests (            -- in-flight Batch intent の正本 (§5.8 の状態機械)
    scope_id          TEXT NOT NULL,
    adapter_kind      TEXT NOT NULL,
    input_hash        TEXT NOT NULL,
    tool_profile_hash TEXT NOT NULL,
    state             INTEGER NOT NULL DEFAULT 0
        CHECK (state IN (0, 1, 2, 3)),   -- 0=投入前/中 1=job 作成済み 2=完了 3=terminal error
    request_kind      TEXT NOT NULL DEFAULT 'batch'
        CHECK (request_kind IN ('batch', 'sync')),
                                         -- 縮退 2 相 (sync online) 行の判別 (§5.4)。回復の適用規則を
                                         --  分岐する — sync 行は job/upload 照合・猶予・期限の対象外
    intent_token      TEXT,              -- UUIDv7 (相 1 で発行)。NULL 化は残骸掃除の完了時のみ (§5.8)
    upload_id         TEXT,              -- 相 2a 成功直後に記録
    batch_job_id      TEXT,              -- 相 2b 成功後・または回復の found 自己記述化で記録。
                                         --  sync 行では provider request id (応答受信直後に記録 — §5.4)
    provider_scope_id TEXT,              -- 相 2a の upload 直前に記録 (§5.8 手順 2 — 非 NULL は
                                         --  「相 2a 着手」の印)。相 1 の再発行で NULL へ戻る (手順 1)
    job_create_started_at INTEGER,       -- UTC ミリ秒。batch 行 = 可視化猶予・回復期限の起点 (§5.8)。
                                         --  sync 行 = 相 1 の開始時刻 (bounded sweep の選択順キー — §5.4)
    stale_after_at    INTEGER,           -- UTC ミリ秒。sync 行のみ: 相 1 で耐久保存する回収期限 (§5.4 —
                                         --  実効 timeout の最大値 + 60 秒、下限 600 秒。Retry-After 受信で
                                         --  自 token CAS により延長)。batch 行は NULL (§5.8 の期限が担う)。
                                         --  列追加の migration は既存の未終端 sync 行へ backfill が必須
                                         --  (10 §7.5.3 の例外規範 — NULL 残置は回収から恒久に漏れる)
    submission_seq    INTEGER NOT NULL DEFAULT 0,
                                         -- 行 (再) 作成時は cost_ledger 同キーの MAX(submission_seq)
                                         --  から継承する (通算連番の高水位の正本は ledger — 0 から
                                         --  数え直すと既存記帳と UNIQUE 衝突する)
    attempts          INTEGER NOT NULL DEFAULT 0,
    contract_violation_count INTEGER NOT NULL DEFAULT 0,
                                         -- reject 終端 Tx (§5.8 相 3) で increment。相 1 の NULL 戻しの
                                         --  対象外 — 「同一 mode で 1 回のみ」の durable 判定源
    estimated_usd     REAL NOT NULL      -- budget 予約額 (§5.4 判定式)。相 1 作成時に保守見積を必須設定
        CHECK (estimated_usd >= 0 AND    --  (NULL/負を許すと SUM が予約を取りこぼし cap を過少判定。
               estimated_usd < 1e999 AND --  +Inf 拒否 (cost_ledger.usd と同じ理由)
               typeof(estimated_usd) IN ('integer', 'real')),
                                         --   typeof 検査は cost_ledger.usd と同じ理由)
    error             TEXT,              -- 'submit_rejected' | 'expired' | 'abandoned' | ...
                                         --  拒否課金 provider (07 §5.7 条件 6) の submit_rejected は
                                         --  terminal 化と同一 Tx で記帳 (Adapter 返却の usage
                                         --  (usd = 宣言請求額 | billable_units — 07 §4) が有効なら
                                         --  provider 値 (estimated=0)、無効・欠落は行の estimated_usd
                                         --  を estimated=1 で — §5.4 の事前検証。
                                         --  ledger 0 行のままの terminal 化を許さない)
    completed_at      INTEGER,           -- state を 2/3 へ確定する全ての UPDATE で同時に書く。
                                         --  未終端は NULL (status の滞留検知に使う)
    created_at        INTEGER NOT NULL,
    PRIMARY KEY (scope_id, adapter_kind, input_hash, tool_profile_hash)
) WITHOUT ROWID;";

pub const CREATE_IDX_BATCH_REQUESTS_INFLIGHT_SQL: &str =
    "CREATE INDEX idx_batch_requests_inflight ON batch_requests(state) WHERE state IN (0, 1);";

pub const CREATE_SCHEMA_MIGRATIONS_SQL: &str = "CREATE TABLE schema_migrations (         -- 一度きりの移行の marker (10 §7.5.3 — JSONL cutover 等)
    name        TEXT NOT NULL PRIMARY KEY, -- 例: 'jsonl-cutover' (rowid 表の TEXT PRIMARY KEY は NULL を拒否しないため NOT NULL 必須)
    applied_at  INTEGER NOT NULL         -- UTC ミリ秒
);";

/// Marker name for the one-time JSONL → SQLite cutover (10 §7.5.3).
pub const JSONL_CUTOVER_MARKER: &str = "jsonl-cutover";

/// `$XDG_DATA_HOME/kio/cost-ledger.sqlite`, falling back to
/// `$HOME/.local/share/kio/cost-ledger.sqlite` (04 §5.4: "デバイスグローバル 1 個").
/// Mirrors `kio_index::registry::default_registry_path`'s XDG resolution exactly.
pub fn default_ledger_path() -> Result<PathBuf> {
    let data_home = kio_core::xdg::xdg_dir("XDG_DATA_HOME")
        .or_else(|| kio_core::xdg::home_dir().map(|home| home.join(".local/share")))
        .ok_or_else(|| {
            PipelineError::Schema(
                "cannot resolve an absolute user data directory; refusing a CWD-relative cost ledger"
                    .to_owned(),
            )
        })?;
    Ok(data_home.join("kio/cost-ledger.sqlite"))
}

/// Open (creating/repairing as needed) the device-global cost ledger.
pub struct LedgerDb {
    pub(crate) conn: Connection,
}

impl LedgerDb {
    pub fn open(path: impl AsRef<Path>) -> Result<Self> {
        let path = path.as_ref();
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).map_err(|err| PipelineError::Io {
                path: parent.display().to_string(),
                message: err.to_string(),
            })?;
            // P2 precedent (registry.rs): the device data dir carries a
            // device-global budget/audit trail — owner-only best effort.
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                let _ = std::fs::set_permissions(parent, std::fs::Permissions::from_mode(0o700));
            }
        }
        let conn = Connection::open(path)?;
        // CL70: WAL + busy_timeout, the same precedent as scope-registry.sqlite.
        conn.busy_timeout(Duration::from_millis(5000))?;
        let _journal_mode: String =
            conn.query_row("PRAGMA journal_mode=WAL", [], |row| row.get(0))?;

        // QA14 (10-operations.md §7.5.2, step4b-contract-tests-p3a.md L307-321):
        // restore-from-backup detection. `PRAGMA user_version` is a monotonic
        // write-sequence counter this module bumps on every mutating ledger
        // operation (see `ops::phase1_intent`/`ops::terminal_transaction`/
        // `ops::cas_update_one`'s doc comments for the exact — and, between
        // them, exhaustive — bump sites). Unlike an in-table column, the
        // counter lives in the SQLite file HEADER, so it travels with the raw
        // file 10 §7.5.2's documented `sqlite3 ... .backup` procedure copies.
        // A companion file next to the DB (`<path>.write-seq`) records the
        // highest value THIS device has observed. If the DB we just opened
        // reports a value LOWER than the companion remembers, the file must
        // have been replaced by an older snapshot (ordinary forward operation
        // only ever increases the counter) — flag it.
        let current_write_seq = read_write_seq(&conn)?;
        let companion_path = write_seq_companion_path(path);
        let restored = match read_write_seq_companion(&companion_path) {
            // Companion absent: first run on this device, or this feature was
            // just introduced against a pre-existing store — adopt the
            // current value as the new baseline rather than flagging
            // (operator-honesty mechanism, not a security boundary: the
            // documented 10 §7.5.2 backup/restore procedure replaces only the
            // DB file, which is exactly the case this detects; there is
            // nothing to compare the very first observation against).
            None => false,
            Some(companion_value) => current_write_seq < companion_value,
        };
        if restored {
            // 10 §7.5.2 L650: report a corrupt restore as corrupt BEFORE
            // anything else — integrity_check runs first, so a truncated or
            // partial backup file is diagnosed clearly rather than surfacing
            // as a confusing table-shape mismatch (`ensure_schema`, below) or
            // an opaque SQL error (the marker INSERT below needs
            // `schema_migrations` to already be verified).
            let integrity = integrity_check(&conn)?;
            if integrity != "ok" {
                return Err(PipelineError::corrupt(
                    path.display().to_string(),
                    format!(
                        "PRAGMA integrity_check reported corruption after a detected \
                         restore-from-backup (10-operations.md §7.5.2): {integrity}"
                    ),
                ));
            }
        }

        ensure_schema(&conn)?;

        if restored {
            // Idempotent: `record_marker` uses a bare INSERT (schema_migrations.name
            // is PRIMARY KEY) — guard with `marker_present` so a marker already
            // persisted by an earlier detection (not yet cleared by `kio ledger
            // reconcile`) cannot cause a duplicate-key error on a later `open`.
            if !crate::ledger::migrate::marker_present(&conn, RESTORE_RECONCILE_PENDING_MARKER)? {
                crate::ledger::migrate::record_marker(&conn, RESTORE_RECONCILE_PENDING_MARKER)?;
            }
        }
        // Refresh the companion to the DB's current value in every case
        // (first-run adoption, ordinary forward progress that left the
        // companion trailing from a crash between a prior commit and its
        // companion write, or the post-detection re-arm so the flag does not
        // re-fire on the next open — the PERSISTED marker above is the gate's
        // durable source of truth from here on). Best-effort: never fails
        // `open` — the companion is an operator-honesty aid, not a
        // correctness requirement of the writes it trails.
        let _ = write_write_seq_companion(&companion_path, current_write_seq);

        Ok(Self { conn })
    }

    pub fn open_default() -> Result<Self> {
        Self::open(default_ledger_path()?)
    }

    #[must_use]
    pub fn connection(&self) -> &Connection {
        &self.conn
    }
}

// ---------------------------------------------------------------------------
// QA14 — write-sequence counter (`PRAGMA user_version`) + restore-from-backup
// detection (10-operations.md §7.5.2, step4b-contract-tests-p3a.md L307-321)
// ---------------------------------------------------------------------------

/// Marker recorded in `schema_migrations` (reusing `migrate.rs`'s generic
/// `marker_present`/`record_marker` — both already take a `name: &str`, so no
/// new SQL/table is needed here) when [`LedgerDb::open`] detects a
/// restored-from-backup DB. `schema_migrations` is this store's one existing
/// generic "operational marker" table (see `JSONL_CUTOVER_MARKER`), and this
/// marker is exactly that shape: a durable, idempotent completion flag — not
/// ledger row DATA, so it does not belong in `cost_ledger`/`batch_requests`.
/// While present, `ops::phase1_intent` refuses new online submissions
/// (`KIO-E-BATCH-RESTORE-RECONCILE-001`). Cleared by `kio ledger reconcile`
/// (`clear_restore_reconcile_marker`) once the 10 §7.5.2 recovery walk
/// completes — unlike [`JSONL_CUTOVER_MARKER`], which is permanent.
pub const RESTORE_RECONCILE_PENDING_MARKER: &str = "restore-reconcile-pending";

/// Clear the QA14 restore-reconcile marker (idempotent — `false` when it was
/// already absent, e.g. a `kio ledger reconcile` run when no restore was ever
/// detected).
pub fn clear_restore_reconcile_marker(conn: &Connection) -> Result<bool> {
    let changed = conn.execute(
        "DELETE FROM schema_migrations WHERE name = ?1",
        rusqlite::params![RESTORE_RECONCILE_PENDING_MARKER],
    )?;
    Ok(changed > 0)
}

/// Whether the QA14 restore-reconcile marker is currently set — the gate
/// `ops::phase1_intent` checks before issuing a new submission. A thin,
/// crate-public wrapper over `migrate::marker_present` so `ops.rs` does not
/// need to depend on `migrate.rs`'s module path directly for this one call.
pub(crate) fn restore_reconcile_marker_present(conn: &Connection) -> Result<bool> {
    crate::ledger::migrate::marker_present(conn, RESTORE_RECONCILE_PENDING_MARKER)
}

/// Runs `PRAGMA integrity_check`, returning the raw result string (`"ok"` on
/// a healthy store; otherwise SQLite's own description of the first problem
/// found). Exposed (not just used internally by [`LedgerDb::open`]'s
/// restore-detection) so `kio ledger reconcile` (QA14 design step a) can run
/// the same check explicitly as its own first action, independent of whether
/// `open` already ran it this process.
pub fn integrity_check(conn: &Connection) -> Result<String> {
    conn.query_row("PRAGMA integrity_check", [], |row| row.get(0))
        .map_err(Into::into)
}

/// Read the DB's current write-sequence counter (`PRAGMA user_version`) — a
/// plain 32-bit signed integer stored in the SQLite file header (present on
/// every valid SQLite file regardless of whether this crate's tables exist
/// yet, and read here strictly BEFORE `ensure_schema` runs).
fn read_write_seq(conn: &Connection) -> Result<i64> {
    conn.query_row("PRAGMA user_version", [], |row| row.get(0))
        .map_err(Into::into)
}

/// Bump the write-sequence counter by 1, saturating at `i32::MAX` (`PRAGMA
/// user_version` is a 32-bit SIGNED integer — SQLite truncates/wraps a value
/// written past that range rather than rejecting it, so the cap must be
/// enforced here). `PRAGMA user_version = <literal>` does not accept a bound
/// parameter, but `next` is always a value this function computed itself
/// (never attacker/user-controlled text), so string interpolation is safe.
///
/// **Transactional by construction** (verified by
/// `ops::qa14_bump_write_seq_is_rolled_back_with_its_transaction`): the
/// user_version field is part of the database file's normal page/header
/// state, so a write to it inside an open transaction or SAVEPOINT commits or
/// rolls back with everything else in that same transaction — no different
/// from an ordinary table UPDATE. Callers rely on this to keep the counter
/// bump atomic with the row mutation it accompanies (see `ops.rs`'s 3 call
/// sites: `phase1_intent`, `terminal_transaction`, `cas_update_one`).
pub(crate) fn bump_write_seq(conn: &Connection) -> Result<()> {
    let current = read_write_seq(conn)?;
    let next = current.saturating_add(1).min(i64::from(i32::MAX));
    conn.execute_batch(&format!("PRAGMA user_version = {next};"))?;
    Ok(())
}

/// `<db path>.write-seq` — the companion file design point 2 names literally
/// (e.g. `cost-ledger.sqlite.write-seq`).
pub(crate) fn write_seq_companion_path(db_path: &Path) -> PathBuf {
    let mut os = db_path.as_os_str().to_owned();
    os.push(".write-seq");
    PathBuf::from(os)
}

/// `None` on any I/O or parse failure — treated identically to "absent" by
/// [`LedgerDb::open`]'s caller (a malformed companion is exactly as
/// uninformative as a missing one; this is an operator-honesty aid, not a
/// security boundary, so failing open rather than degrading would be the
/// wrong tradeoff).
fn read_write_seq_companion(companion_path: &Path) -> Option<i64> {
    std::fs::read_to_string(companion_path)
        .ok()?
        .trim()
        .parse::<i64>()
        .ok()
}

/// Write the companion file atomically (temp file + rename, so a concurrent
/// reader never observes a torn/partial write) — best-effort: I/O errors are
/// the caller's to decide whether to ignore (every call site in this crate
/// does, per the companion's "advisory, not correctness-bearing" contract).
fn write_write_seq_companion(companion_path: &Path, value: i64) -> std::io::Result<()> {
    let mut tmp_os = companion_path.as_os_str().to_owned();
    tmp_os.push(".tmp");
    let tmp_path = PathBuf::from(tmp_os);
    std::fs::write(&tmp_path, value.to_string())?;
    std::fs::rename(&tmp_path, companion_path)
}

/// Best-effort: after a mutating ledger call's own SAVEPOINT (or the outer
/// `BEGIN IMMEDIATE` transaction it may be nested inside) has fully released,
/// refresh the write-seq companion file to match the CURRENT `user_version`
/// — but only when `conn.is_autocommit()` reports there is no ambient
/// transaction still pending above the caller. A released SAVEPOINT does not
/// mean "durably committed to disk" when it is nested inside an outer,
/// still-open transaction (e.g. `phase1_intent` called from within
/// `with_immediate_transaction`) — writing the companion at that point would
/// advance it past a value the DB could still roll back to, which is exactly
/// the dangerous self-inflicted false positive this guard exists to prevent
/// (a later, genuinely-outermost commit calls this again and captures the
/// final state correctly). A no-op when the connection has no backing file
/// (`:memory:`/temp — no companion concept applies) or when `user_version`
/// cannot be read. Never propagates an error — see [`write_write_seq_companion`].
pub(crate) fn sync_write_seq_companion_if_committed(conn: &Connection) {
    if !conn.is_autocommit() {
        return;
    }
    let Some(db_path) = conn.path().filter(|path| !path.is_empty()) else {
        return;
    };
    let db_path = PathBuf::from(db_path);
    let Ok(current) = read_write_seq(conn) else {
        return;
    };
    let _ = write_write_seq_companion(&write_seq_companion_path(&db_path), current);
}

/// Create the 3-table schema on a fresh store, or self-heal a missing/malformed
/// required index on an existing one (CL08 / 10 §7.5.3). Table-shape MIGRATION
/// beyond the one-time JSONL cutover is deliberately not attempted here (R23-24
/// reduced scope — see [`detect_table_shape_mismatch`]'s doc comment): the only
/// self-healing this routine performs on an existing store is the index repair
/// below. A table whose shape does not match this build's DDL-of-record is
/// detected and refused (fail-closed), not silently migrated in place.
fn ensure_schema(conn: &Connection) -> Result<()> {
    let tables = table_names(conn)?;
    let has_any = tables.contains("cost_ledger")
        || tables.contains("batch_requests")
        || tables.contains("schema_migrations");
    if !has_any {
        with_savepoint(conn, "kio_ledger_create_schema", || {
            conn.execute_batch(CREATE_COST_LEDGER_SQL)?;
            conn.execute_batch(CREATE_IDX_COST_LEDGER_MONTH_SQL)?;
            conn.execute_batch(CREATE_BATCH_REQUESTS_SQL)?;
            conn.execute_batch(CREATE_IDX_BATCH_REQUESTS_INFLIGHT_SQL)?;
            conn.execute_batch(CREATE_SCHEMA_MIGRATIONS_SQL)?;
            Ok(())
        })?;
        return Ok(());
    }
    // R23-24: fail-closed on a table-shape mismatch (or a partial table set)
    // BEFORE any index self-heal DDL runs against a store this build cannot
    // verify the row invariants of.
    detect_table_shape_mismatch(conn)?;
    // CL08: repair a missing or shape-mismatched required index without
    // touching the tables themselves.
    repair_index_shape(
        conn,
        "idx_cost_ledger_month",
        "cost_ledger",
        CREATE_IDX_COST_LEDGER_MONTH_SQL,
    )?;
    repair_index_shape(
        conn,
        "idx_batch_requests_inflight",
        "batch_requests",
        CREATE_IDX_BATCH_REQUESTS_INFLIGHT_SQL,
    )?;
    Ok(())
}

/// R23-24 (10 §7.5.3: "形状検出は sqlite_master の CREATE 文 (列・CHECK 制約を
/// 含む) の canonical 比較で行う — 対象は `cost_ledger` / `batch_requests` /
/// `schema_migrations` の 3 表すべて"; reduced adjudicated scope — the
/// in-place table-shape MIGRATION 10 §7.5.3 also describes is explicit backlog,
/// not implemented here): on an EXISTING store (this is only called once
/// `ensure_schema` has already established at least one of the 3 tables is
/// present), every one of the 3 tables must both exist and canonical-compare
/// equal to this build's DDL-of-record. A table existing with a non-canonical
/// shape (an added/removed/retyped column, a changed CHECK constraint, ...)
/// means the store was created or migrated by a different code version than
/// this build expects — this build's row invariants (the CHECK constraints
/// `classify_check_violation`/§5.8's "1 回のみ" durability rely on, among
/// others) cannot be trusted to hold, so this refuses to open rather than
/// operate silently against an unverified shape. A table missing while
/// `ensure_schema`'s caller already determined `has_any` is torn/partial store
/// state no legitimate code path produces (all 3 tables are always created
/// together, in one savepoint) — treated identically to a shape mismatch.
fn detect_table_shape_mismatch(conn: &Connection) -> Result<()> {
    for (table_name, create_sql) in [
        ("cost_ledger", CREATE_COST_LEDGER_SQL),
        ("batch_requests", CREATE_BATCH_REQUESTS_SQL),
        ("schema_migrations", CREATE_SCHEMA_MIGRATIONS_SQL),
    ] {
        let current = object_sql(conn, "table", table_name)?.ok_or_else(|| {
            PipelineError::corrupt(
                table_name,
                format!(
                    "cost-ledger.sqlite is missing table `{table_name}` while other \
                     cost-ledger.sqlite tables already exist (10-operations.md §7.5.3 shape \
                     detection) — a legitimate store always creates all 3 tables together in one \
                     savepoint; this is a torn or hand-edited store, not a supported partial shape."
                ),
            )
        })?;
        if canonical_sql_tokens(&current) != canonical_sql_tokens(create_sql) {
            return Err(PipelineError::corrupt(
                table_name,
                format!(
                    "cost-ledger.sqlite table `{table_name}` shape does not match this build's \
                     DDL-of-record (04-pipeline.md §5.4 SQL 正本) — refusing to open a store whose \
                     row invariants this build cannot verify (10-operations.md §7.5.3 canonical \
                     shape detection: table/column/CHECK constraint comparison). In-place \
                     table-shape migration is not implemented; recovery requires a \
                     schema-compatible build."
                ),
            ));
        }
    }
    Ok(())
}

fn table_names(conn: &Connection) -> Result<BTreeSet<String>> {
    let mut stmt = conn.prepare("SELECT name FROM sqlite_master WHERE type = 'table'")?;
    let rows = stmt.query_map([], |row| row.get::<_, String>(0))?;
    let mut set = BTreeSet::new();
    for row in rows {
        set.insert(row?);
    }
    Ok(set)
}

/// The literal `sql` text sqlite_master stores for a table/index, or `None` if
/// it does not exist.
pub fn object_sql(conn: &Connection, kind: &str, name: &str) -> Result<Option<String>> {
    conn.query_row(
        "SELECT sql FROM sqlite_master WHERE type = ?1 AND name = ?2",
        rusqlite::params![kind, name],
        |row| row.get(0),
    )
    .optional()
    .map_err(Into::into)
}

/// CL08: detect a missing or shape-mismatched index and converge it to
/// canonical inside one savepoint, recording completion to `schema_migrations`
/// (idempotent — `INSERT OR IGNORE`, since a no-op repair never gets here: the
/// canonical-match check short-circuits first).
fn repair_index_shape(
    conn: &Connection,
    index_name: &str,
    table_name: &str,
    create_sql: &'static str,
) -> Result<()> {
    let expected = canonical_sql_tokens(create_sql);
    let current = object_sql(conn, "index", index_name)?;
    if current.as_deref().map(canonical_sql_tokens).as_ref() == Some(&expected) {
        return Ok(());
    }
    let _ = table_name; // documents which table this index belongs to at call sites
    with_savepoint(conn, "kio_ledger_repair_index", || {
        if current.is_some() {
            // IF NOT EXISTS alone cannot fix a same-named, differently-shaped
            // index (10 §7.5.3): drop and recreate canonical.
            conn.execute_batch(&format!("DROP INDEX {index_name};"))?;
        }
        conn.execute_batch(create_sql)?;
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations (name, applied_at) VALUES (?1, ?2)",
            rusqlite::params![
                format!("index-shape-repair:{index_name}"),
                crate::ledger::time::now_millis()
            ],
        )?;
        Ok(())
    })
}

/// Named-savepoint helper (same idiom as `kio_index::embedding_store`'s
/// `with_savepoint` / `kio_index::fts`'s — duplicated locally per this
/// codebase's existing convention of not sharing this tiny helper cross-crate).
pub(crate) fn with_savepoint<T>(
    conn: &Connection,
    name: &str,
    operation: impl FnOnce() -> Result<T>,
) -> Result<T> {
    conn.execute_batch(&format!("SAVEPOINT {name};"))?;
    match operation() {
        Ok(value) => {
            conn.execute_batch(&format!("RELEASE {name};"))?;
            Ok(value)
        }
        Err(err) => {
            let _ = conn.execute_batch(&format!("ROLLBACK TO {name}; RELEASE {name};"));
            Err(err)
        }
    }
}

/// Normalize SQL text into a token stream for canonical-shape comparison (10
/// §7.5.3: "形状検出は sqlite_master の CREATE 文...の canonical 比較で行う").
/// Strips `--` line comments, then splits on whitespace while making `(`, `)`,
/// `,` their own tokens (so `typeof(usd)` and `typeof (usd)` compare equal, but
/// `usd>=0` and `usd >= 0` are unaffected since `>`/`=` are not punctuation
/// boundaries here — the DDL-of-record always spaces its operators, so exact
/// token equality on those still holds byte-for-byte). `;` is dropped entirely
/// (treated as a separator, not a token) — `sqlite_master.sql` never stores the
/// terminating semicolon of the statement it was created from, so keeping it as
/// a token would make every comparison against a hand-authored DDL constant
/// (which does end in `;`) spuriously mismatch.
#[must_use]
pub fn canonical_sql_tokens(sql: &str) -> Vec<String> {
    let mut without_comments = String::with_capacity(sql.len());
    let mut chars = sql.chars().peekable();
    while let Some(c) = chars.next() {
        if c == '-' && chars.peek() == Some(&'-') {
            chars.next();
            for c2 in chars.by_ref() {
                if c2 == '\n' {
                    without_comments.push('\n');
                    break;
                }
            }
            continue;
        }
        without_comments.push(c);
    }
    let mut tokens = Vec::new();
    let mut current = String::new();
    for c in without_comments.chars() {
        if c.is_whitespace() || c == ';' {
            // `;` is a separator like whitespace, never a token of its own —
            // see the doc comment above.
            if !current.is_empty() {
                tokens.push(std::mem::take(&mut current));
            }
        } else if matches!(c, '(' | ')' | ',') {
            if !current.is_empty() {
                tokens.push(std::mem::take(&mut current));
            }
            tokens.push(c.to_string());
        } else {
            current.push(c);
        }
    }
    if !current.is_empty() {
        tokens.push(current);
    }
    tokens
}

#[cfg(test)]
mod tests {
    use super::*;

    fn open_temp() -> (tempfile::TempDir, LedgerDb) {
        let dir = tempfile::tempdir().unwrap();
        let db = LedgerDb::open(dir.path().join("cost-ledger.sqlite")).unwrap();
        (dir, db)
    }

    #[test]
    fn open_creates_all_three_tables_and_two_indexes() {
        let (_dir, db) = open_temp();
        let tables = table_names(&db.conn).unwrap();
        assert!(tables.contains("cost_ledger"));
        assert!(tables.contains("batch_requests"));
        assert!(tables.contains("schema_migrations"));
        assert!(object_sql(&db.conn, "index", "idx_cost_ledger_month")
            .unwrap()
            .is_some());
        assert!(object_sql(&db.conn, "index", "idx_batch_requests_inflight")
            .unwrap()
            .is_some());
    }

    #[test]
    fn open_sets_wal_and_busy_timeout() {
        let (_dir, db) = open_temp();
        let journal: String = db
            .conn
            .query_row("PRAGMA journal_mode", [], |row| row.get(0))
            .unwrap();
        assert_eq!(journal.to_lowercase(), "wal");
        let timeout: i64 = db
            .conn
            .query_row("PRAGMA busy_timeout", [], |row| row.get(0))
            .unwrap();
        assert!(timeout > 0);
    }

    #[test]
    fn reopen_is_idempotent_and_preserves_rows() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("cost-ledger.sqlite");
        {
            let db = LedgerDb::open(&path).unwrap();
            db.conn
                .execute(
                    "INSERT INTO schema_migrations (name, applied_at) VALUES ('probe', 1)",
                    [],
                )
                .unwrap();
        }
        let db2 = LedgerDb::open(&path).unwrap();
        let count: i64 = db2
            .conn
            .query_row("SELECT COUNT(*) FROM schema_migrations", [], |row| {
                row.get(0)
            })
            .unwrap();
        assert_eq!(count, 1, "reopening must not recreate/wipe the schema");
    }

    // CL08(a): a missing `idx_batch_requests_inflight` is created via the same
    // savepoint-guarded self-heal path `ensure_schema` uses on open, and the
    // completion is recorded to schema_migrations.
    #[test]
    fn missing_index_is_self_healed_on_open() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("cost-ledger.sqlite");
        {
            let conn = Connection::open(&path).unwrap();
            conn.execute_batch(CREATE_COST_LEDGER_SQL).unwrap();
            conn.execute_batch(CREATE_IDX_COST_LEDGER_MONTH_SQL)
                .unwrap();
            conn.execute_batch(CREATE_BATCH_REQUESTS_SQL).unwrap();
            conn.execute_batch(CREATE_SCHEMA_MIGRATIONS_SQL).unwrap();
            // Deliberately omit idx_batch_requests_inflight.
        }
        let db = LedgerDb::open(&path).unwrap();
        let sql = object_sql(&db.conn, "index", "idx_batch_requests_inflight")
            .unwrap()
            .expect("self-healed");
        assert_eq!(
            canonical_sql_tokens(&sql),
            canonical_sql_tokens(CREATE_IDX_BATCH_REQUESTS_INFLIGHT_SQL)
        );
        let marker: i64 = db
            .conn
            .query_row(
                "SELECT COUNT(*) FROM schema_migrations WHERE name = 'index-shape-repair:idx_batch_requests_inflight'",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(marker, 1);
    }

    // CL08(b): a same-named but differently-shaped index (missing the WHERE
    // clause) is DROP+CREATE converged to canonical — IF NOT EXISTS alone would
    // leave the wrong shape in place.
    #[test]
    fn malformed_index_is_dropped_and_recreated_on_open() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("cost-ledger.sqlite");
        {
            let conn = Connection::open(&path).unwrap();
            conn.execute_batch(CREATE_COST_LEDGER_SQL).unwrap();
            conn.execute_batch(CREATE_IDX_COST_LEDGER_MONTH_SQL)
                .unwrap();
            conn.execute_batch(CREATE_BATCH_REQUESTS_SQL).unwrap();
            conn.execute_batch(CREATE_SCHEMA_MIGRATIONS_SQL).unwrap();
            // Malformed: no partial-index WHERE clause.
            conn.execute_batch(
                "CREATE INDEX idx_batch_requests_inflight ON batch_requests(state);",
            )
            .unwrap();
        }
        let db = LedgerDb::open(&path).unwrap();
        let sql = object_sql(&db.conn, "index", "idx_batch_requests_inflight")
            .unwrap()
            .expect("still present");
        assert_eq!(
            canonical_sql_tokens(&sql),
            canonical_sql_tokens(CREATE_IDX_BATCH_REQUESTS_INFLIGHT_SQL)
        );
    }

    #[test]
    fn canonical_sql_tokens_ignores_comments_and_whitespace_layout() {
        let a = "CREATE INDEX foo ON t(a); -- trailing comment\n";
        let b = "CREATE   INDEX\nfoo\nON\nt(a);";
        assert_eq!(canonical_sql_tokens(a), canonical_sql_tokens(b));
    }

    // R23-24 (10 §7.5.3 shape detection, reduced scope: detection only, no
    // in-place migration): a `cost_ledger` table that exists but is missing the
    // `usd` CHECK constraint entirely (same columns, weaker invariants — the
    // exact "CHECK differs, column existence check would miss it" case 10
    // §7.5.3 calls out) must refuse to open rather than silently trust a
    // shape this build never validated.
    #[test]
    fn r23_24_table_shape_mismatch_refuses_to_open() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("cost-ledger.sqlite");
        {
            let conn = Connection::open(&path).unwrap();
            conn.execute_batch(
                "CREATE TABLE cost_ledger (
                    scope_id          TEXT NOT NULL,
                    adapter_kind      TEXT NOT NULL,
                    input_hash        TEXT NOT NULL,
                    tool_profile_hash TEXT NOT NULL,
                    submission_seq    INTEGER NOT NULL,
                    batch_job_id      TEXT NOT NULL,
                    usd               REAL NOT NULL,
                    estimated         INTEGER NOT NULL DEFAULT 0 CHECK (estimated IN (0, 1)),
                    outcome           TEXT NOT NULL,
                    month             TEXT NOT NULL,
                    recorded_at       INTEGER NOT NULL,
                    UNIQUE (scope_id, adapter_kind, input_hash, tool_profile_hash, submission_seq)
                );",
            )
            .unwrap();
            conn.execute_batch(CREATE_IDX_COST_LEDGER_MONTH_SQL)
                .unwrap();
            conn.execute_batch(CREATE_BATCH_REQUESTS_SQL).unwrap();
            conn.execute_batch(CREATE_IDX_BATCH_REQUESTS_INFLIGHT_SQL)
                .unwrap();
            conn.execute_batch(CREATE_SCHEMA_MIGRATIONS_SQL).unwrap();
        }
        // `LedgerDb` does not implement `Debug` (its `rusqlite::Connection`
        // field does not), so `.unwrap_err()` (which requires `T: Debug`) is
        // not usable here — match instead.
        let err = match LedgerDb::open(&path) {
            Ok(_) => panic!("expected LedgerDb::open to refuse a shape-mismatched cost_ledger"),
            Err(err) => err,
        };
        assert!(
            err.to_string().contains("KIO-E-STORE-CORRUPT-001"),
            "got {err:?}"
        );
    }

    // R23-24: a store with only SOME of the 3 required tables (a torn/partial
    // shape no legitimate code path produces — `ensure_schema`'s fresh-create
    // branch always creates all 3 together in one savepoint) must also refuse
    // to open, rather than let a later `CREATE INDEX ... ON <missing table>`
    // fail with an opaque, uncategorized SQL error.
    #[test]
    fn r23_24_partial_table_set_refuses_to_open() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("cost-ledger.sqlite");
        {
            let conn = Connection::open(&path).unwrap();
            conn.execute_batch(CREATE_COST_LEDGER_SQL).unwrap();
            conn.execute_batch(CREATE_IDX_COST_LEDGER_MONTH_SQL)
                .unwrap();
            // batch_requests and schema_migrations deliberately omitted.
        }
        let err = match LedgerDb::open(&path) {
            Ok(_) => panic!("expected LedgerDb::open to refuse a partial table set"),
            Err(err) => err,
        };
        assert!(
            err.to_string().contains("KIO-E-STORE-CORRUPT-001"),
            "got {err:?}"
        );
    }

    // R23-24: a store whose 3 tables exactly match the DDL-of-record must open
    // normally and still reach the existing CL08 index self-heal — the new
    // detection must not false-positive on a legitimately-shaped store (every
    // OTHER test in this module already exercises this implicitly; this test
    // names the R23-24 non-regression explicitly).
    #[test]
    fn r23_24_matching_table_shape_opens_and_still_self_heals_index() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("cost-ledger.sqlite");
        {
            let conn = Connection::open(&path).unwrap();
            conn.execute_batch(CREATE_COST_LEDGER_SQL).unwrap();
            conn.execute_batch(CREATE_IDX_COST_LEDGER_MONTH_SQL)
                .unwrap();
            conn.execute_batch(CREATE_BATCH_REQUESTS_SQL).unwrap();
            conn.execute_batch(CREATE_SCHEMA_MIGRATIONS_SQL).unwrap();
            // idx_batch_requests_inflight deliberately omitted — proves shape
            // detection runs (and passes) BEFORE the pre-existing index repair.
        }
        let db = LedgerDb::open(&path).unwrap();
        assert!(object_sql(&db.conn, "index", "idx_batch_requests_inflight")
            .unwrap()
            .is_some());
    }

    // -----------------------------------------------------------------
    // QA14 — write-sequence counter + restore-from-backup detection
    // (step4b-contract-tests-p3a.md L307-321, 10-operations.md §7.5.2)
    // -----------------------------------------------------------------

    /// `PRAGMA user_version` writes participate in the ambient transaction
    /// like any ordinary table write — a `bump_write_seq` call inside a
    /// transaction that later ROLLS BACK must leave the counter unchanged
    /// (this is what makes `phase1_intent`/`terminal_transaction`/
    /// `cas_update_one`'s own SAVEPOINT-wrapped bumps safe: an error midway
    /// through the wrapped write correctly un-bumps too).
    #[test]
    fn qa14_bump_write_seq_is_rolled_back_with_its_transaction() {
        let (_dir, db) = open_temp();
        let before = read_write_seq(&db.conn).unwrap();
        db.conn.execute_batch("BEGIN;").unwrap();
        bump_write_seq(&db.conn).unwrap();
        assert_eq!(
            read_write_seq(&db.conn).unwrap(),
            before + 1,
            "the bump is visible within its own still-open transaction"
        );
        db.conn.execute_batch("ROLLBACK;").unwrap();
        assert_eq!(
            read_write_seq(&db.conn).unwrap(),
            before,
            "a rolled-back transaction must not leave the bump in place"
        );
    }

    /// The COMMIT-side counterpart: a bump inside a transaction that
    /// actually commits persists (sanity check the rollback test above is
    /// exercising a real transactional property, not merely "writes never
    /// stick").
    #[test]
    fn qa14_bump_write_seq_persists_across_commit() {
        let (_dir, db) = open_temp();
        let before = read_write_seq(&db.conn).unwrap();
        db.conn.execute_batch("BEGIN;").unwrap();
        bump_write_seq(&db.conn).unwrap();
        db.conn.execute_batch("COMMIT;").unwrap();
        assert_eq!(read_write_seq(&db.conn).unwrap(), before + 1);
    }

    /// `bump_write_seq` saturates at `i32::MAX` rather than wrapping past it.
    #[test]
    fn qa14_bump_write_seq_saturates_at_i32_max() {
        let (_dir, db) = open_temp();
        db.conn
            .execute_batch(&format!("PRAGMA user_version = {};", i32::MAX))
            .unwrap();
        bump_write_seq(&db.conn).unwrap();
        assert_eq!(read_write_seq(&db.conn).unwrap(), i64::from(i32::MAX));
    }

    /// The companion file: absent -> `None`; written -> read back exactly;
    /// atomic (temp+rename leaves no `.tmp` litter behind).
    #[test]
    fn qa14_write_seq_companion_roundtrips_and_absent_reads_as_none() {
        let dir = tempfile::tempdir().unwrap();
        let db_path = dir.path().join("cost-ledger.sqlite");
        let companion_path = write_seq_companion_path(&db_path);
        assert_eq!(read_write_seq_companion(&companion_path), None);

        write_write_seq_companion(&companion_path, 42).unwrap();
        assert_eq!(read_write_seq_companion(&companion_path), Some(42));

        write_write_seq_companion(&companion_path, 43).unwrap();
        assert_eq!(read_write_seq_companion(&companion_path), Some(43));

        let mut tmp_os = companion_path.as_os_str().to_owned();
        tmp_os.push(".tmp");
        assert!(
            !PathBuf::from(tmp_os).exists(),
            "the temp file must be renamed away, not left behind"
        );
    }

    /// A fresh store (no companion, no prior observation) never flags a
    /// restore — first-run adoption — and leaves a companion behind for the
    /// next open to compare against.
    #[test]
    fn qa14_fresh_store_first_open_adopts_baseline_without_flagging() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("cost-ledger.sqlite");
        let db = LedgerDb::open(&path).unwrap();
        assert!(!restore_reconcile_marker_present(&db.conn).unwrap());
        let companion = write_seq_companion_path(&path);
        assert_eq!(
            read_write_seq_companion(&companion),
            Some(read_write_seq(&db.conn).unwrap())
        );
    }

    /// The full QA14 detection flow, driven purely through this module's own
    /// primitives (no dependency on `ops.rs`): open once (baseline
    /// companion=0) -> the DB's `user_version` is advanced (simulating any
    /// mutating ledger operation) -> the companion is refreshed to observe
    /// that advance (simulating the post-commit sync every real bump site
    /// performs) -> the DB is rolled back to an OLDER `user_version` without
    /// touching the companion (simulating a `.backup`/restore, which is
    /// indistinguishable at this layer from "someone rewrote the header") ->
    /// the next `open` must flag it, persist the marker (idempotently on a
    /// THIRD open), and re-arm the companion to the restored value.
    #[test]
    fn qa14_open_detects_restore_persists_marker_and_refreshes_companion() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("cost-ledger.sqlite");
        let companion = write_seq_companion_path(&path);

        {
            let db = LedgerDb::open(&path).unwrap();
            assert_eq!(read_write_seq(&db.conn).unwrap(), 0);
        }
        assert_eq!(read_write_seq_companion(&companion), Some(0));

        // Simulate ordinary forward operation advancing the counter, and the
        // post-commit companion sync every real bump site performs.
        {
            let db = LedgerDb::open(&path).unwrap();
            db.conn.execute_batch("PRAGMA user_version = 5;").unwrap();
            write_write_seq_companion(&companion, 5).unwrap();
        }
        assert_eq!(read_write_seq_companion(&companion), Some(5));

        // Simulate a restore: the DB file now reports an OLDER value than
        // the companion last observed, with the companion itself untouched
        // (a real `.backup`/restore only ever replaces the DB file).
        {
            let conn = Connection::open(&path).unwrap();
            conn.execute_batch("PRAGMA user_version = 2;").unwrap();
        }
        assert_eq!(read_write_seq_companion(&companion), Some(5));

        let db2 = LedgerDb::open(&path).unwrap();
        assert!(
            restore_reconcile_marker_present(&db2.conn).unwrap(),
            "user_version regressing (2 < companion's 5) must flag a restore"
        );
        assert_eq!(
            read_write_seq_companion(&companion),
            Some(2),
            "the companion must re-arm to the (restored) DB's current value"
        );
        drop(db2);

        // A THIRD open (no further tampering): the companion now equals the
        // DB's value, so detection does not re-fire — but the marker,
        // already persisted, is the durable source of truth and must still
        // be present (and re-persisting it must not panic on the
        // schema_migrations PRIMARY KEY — this is the idempotency guard).
        let db3 = LedgerDb::open(&path).unwrap();
        assert!(restore_reconcile_marker_present(&db3.conn).unwrap());
    }

    /// `clear_restore_reconcile_marker`: idempotent (`false` when absent),
    /// and actually removes a present marker.
    #[test]
    fn qa14_clear_restore_reconcile_marker_is_idempotent() {
        let (_dir, db) = open_temp();
        assert!(!clear_restore_reconcile_marker(&db.conn).unwrap());
        crate::ledger::migrate::record_marker(&db.conn, RESTORE_RECONCILE_PENDING_MARKER).unwrap();
        assert!(restore_reconcile_marker_present(&db.conn).unwrap());
        assert!(clear_restore_reconcile_marker(&db.conn).unwrap());
        assert!(!restore_reconcile_marker_present(&db.conn).unwrap());
        // A second clear on an already-absent marker is a no-op, not an error.
        assert!(!clear_restore_reconcile_marker(&db.conn).unwrap());
    }

    /// `PRAGMA integrity_check` on a healthy store reports `"ok"`.
    #[test]
    fn qa14_integrity_check_reports_ok_on_a_healthy_store() {
        let (_dir, db) = open_temp();
        assert_eq!(integrity_check(&db.conn).unwrap(), "ok");
    }
}
