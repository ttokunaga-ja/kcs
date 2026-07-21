//! `cost-ledger.sqlite` schema: DDL SQL-of-record (04-pipeline.md §5.4), device
//! path resolution, connection bootstrap (WAL + busy_timeout, same precedent as
//! `crates/kcs-index/src/registry.rs`'s scope-registry.sqlite), and the shape
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

/// `$XDG_DATA_HOME/kcs/cost-ledger.sqlite`, falling back to
/// `$HOME/.local/share/kcs/cost-ledger.sqlite` (04 §5.4: "デバイスグローバル 1 個").
/// Mirrors `kcs_index::registry::default_registry_path`'s XDG resolution exactly.
pub fn default_ledger_path() -> Result<PathBuf> {
    let data_home = kcs_core::xdg::xdg_dir("XDG_DATA_HOME")
        .or_else(|| kcs_core::xdg::home_dir().map(|home| home.join(".local/share")))
        .ok_or_else(|| {
            PipelineError::Schema(
                "cannot resolve an absolute user data directory; refusing a CWD-relative cost ledger"
                    .to_owned(),
            )
        })?;
    Ok(data_home.join("kcs/cost-ledger.sqlite"))
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
        ensure_schema(&conn)?;
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

/// Create the 3-table schema on a fresh store, or self-heal a missing/malformed
/// required index on an existing one (CL08 / 10 §7.5.3). Table-shape migration
/// beyond the one-time JSONL cutover is deliberately not attempted here — this
/// store is greenfield (no prior `cost-ledger.sqlite` releases exist to diverge
/// from), so the only legitimate "existing but wrong" case in practice is an
/// index left behind by an interrupted earlier run of this same routine.
fn ensure_schema(conn: &Connection) -> Result<()> {
    let tables = table_names(conn)?;
    let has_any = tables.contains("cost_ledger")
        || tables.contains("batch_requests")
        || tables.contains("schema_migrations");
    if !has_any {
        with_savepoint(conn, "kcs_ledger_create_schema", || {
            conn.execute_batch(CREATE_COST_LEDGER_SQL)?;
            conn.execute_batch(CREATE_IDX_COST_LEDGER_MONTH_SQL)?;
            conn.execute_batch(CREATE_BATCH_REQUESTS_SQL)?;
            conn.execute_batch(CREATE_IDX_BATCH_REQUESTS_INFLIGHT_SQL)?;
            conn.execute_batch(CREATE_SCHEMA_MIGRATIONS_SQL)?;
            Ok(())
        })?;
        return Ok(());
    }
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
    with_savepoint(conn, "kcs_ledger_repair_index", || {
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

/// Named-savepoint helper (same idiom as `kcs_index::embedding_store`'s
/// `with_savepoint` / `kcs_index::fts`'s — duplicated locally per this
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
}
