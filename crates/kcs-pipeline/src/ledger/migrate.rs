//! One-time JSONL → SQLite cutover (10-operations.md §7.5.3, CL09-CL12).
//!
//! Two phases: **(1)** import old `cost-ledger.jsonl` rows into `cost_ledger` and
//! record the `schema_migrations` marker row in the *same* Tx (a savepoint — crash
//! before commit leaves zero imported rows and no marker); **(2)** rename the old
//! JSONL files to `.migrated` (a plain filesystem rename cannot join the savepoint,
//! so it is retried independently on every call — idempotent because a
//! already-`.migrated` source is simply absent on the next attempt).
//!
//! **Field-mapping gap (flagged, not silently resolved):** the pre-2026-07-18
//! `cost-ledger.jsonl` format (`{month, scope_id, adapter_kind, usd}`) predates
//! the per-task granularity `cost_ledger` now requires
//! (`input_hash`/`tool_profile_hash`/`submission_seq`/`batch_job_id`/`outcome`) —
//! none of docs/04-pipeline.md §5.4, §5.8, or `tasks/step4b-contract-tests-ledger.md`
//! define how a pre-cutover charge row should populate those columns (the CL09-12
//! "期待" sections only assert transactional mechanics — row counts, marker
//! presence, rollback atomicity — never specific field values). This
//! implementation's resolution: each legacy row becomes one `cost_ledger` row with
//! `outcome='succeeded'`, `estimated=0` (the old ledger only ever recorded settled
//! charges), a per-row-unique synthetic `input_hash`/`batch_job_id`
//! (`sha256:legacy-import-<line index>` / `legacy-import-<line index>`, so the
//! UNIQUE constraint is trivially satisfied) and a fixed `tool_profile_hash =
//! 'legacy-import'`, with `recorded_at` backfilled to that row's UTC month start
//! (the exact original timestamp was never persisted by the old format). The
//! sibling `cost-ledger-reservations.jsonl` (in-flight, un-settled reservations)
//! and `cost-ledger-reclaimed.jsonl` (phantom-charge credits) are *not* imported:
//! reservations have no schema-compatible representation without a real
//! `intent_token`/upload/job state, and `cost_ledger.usd` is `CHECK`-constrained
//! non-negative so a credit/reclaim row cannot be represented at all. Any
//! historical charge that the old system would have reclaimed is therefore
//! imported at its original (unreclaimed) amount — a bounded, one-time
//! over-count, consistent with this spec's general "over-count is safer than
//! under-count" posture (e.g. CL45's sync crash recovery). Both files are still
//! renamed to `.migrated` in phase 2 so their content is preserved for manual
//! inspection. Report this resolution to the spec owner (§ "spec と契約書の
//! 食い違い" — genuinely unspecified, not a third invented interpretation of an
//! existing rule).

use std::path::{Path, PathBuf};

use rusqlite::{params, Connection};
use serde::Deserialize;

use crate::ledger::schema::{with_savepoint, JSONL_CUTOVER_MARKER};
use crate::ledger::time::{month_start_millis, now_millis, parse_month};
use crate::{PipelineError, Result};

/// The legacy JSONL file basenames migrated together (10 §12.7 rename table).
/// Every entry is renamed independently in phase 2 when present; a missing file
/// (e.g. a device that never wrote reservations) is simply skipped.
pub const LEGACY_JSONL_BASENAMES: &[&str] = &[
    "cost-ledger.jsonl",
    "cost-ledger-reservations.jsonl",
    "cost-ledger-reclaimed.jsonl",
    "cost-ledger.lock",
];

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct JsonlMigrationOutcome {
    /// Rows imported into `cost_ledger` this call. Zero both when there was
    /// nothing to import and when phase 1 had already completed on a prior run
    /// (see `already_migrated`).
    pub imported_rows: usize,
    /// True when the `jsonl-cutover` marker already existed on entry (phase 1
    /// was skipped; only phase 2's rename retry ran).
    pub already_migrated: bool,
    /// Legacy basenames actually renamed to `.migrated` this call.
    pub renamed_files: Vec<String>,
}

/// Legacy `cost-ledger.jsonl` row shape (pre-cutover `MonthlyCostLedgerEntry`).
/// Deliberately a fresh, read-only type local to the migration path rather than
/// a re-export of `budget::MonthlyCostLedgerEntry` — the write-path JSONL ledger
/// this mirrors is being retired, and the migration's on-disk contract should
/// not move if that struct's derives/fields change for unrelated reasons.
#[derive(Debug, Deserialize)]
struct LegacyChargeRow {
    month: String,
    scope_id: String,
    adapter_kind: String,
    usd: f64,
}

/// Run both migration phases against `jsonl_dir` (the directory that historically
/// held `cost-ledger.jsonl` and its siblings — `$XDG_DATA_HOME/kcs`). Safe to call
/// on every ledger-touching command's startup: phase 1 is a no-op once the marker
/// exists, and phase 2's rename is a no-op once the source files are gone.
pub fn migrate_jsonl_if_needed(
    conn: &Connection,
    jsonl_dir: &Path,
) -> Result<JsonlMigrationOutcome> {
    let already_migrated = marker_present(conn, JSONL_CUTOVER_MARKER)?;
    let imported_rows = if already_migrated {
        0
    } else {
        with_savepoint(conn, "kcs_ledger_jsonl_cutover", || {
            let imported = import_cost_ledger_rows(conn, &jsonl_dir.join("cost-ledger.jsonl"))?;
            record_marker(conn, JSONL_CUTOVER_MARKER)?;
            Ok(imported)
        })?
    };
    let renamed_files = rename_legacy_files(jsonl_dir)?;
    Ok(JsonlMigrationOutcome {
        imported_rows,
        already_migrated,
        renamed_files,
    })
}

pub(crate) fn marker_present(conn: &Connection, name: &str) -> Result<bool> {
    let count: i64 = conn.query_row(
        "SELECT COUNT(*) FROM schema_migrations WHERE name = ?1",
        params![name],
        |row| row.get(0),
    )?;
    Ok(count > 0)
}

pub(crate) fn record_marker(conn: &Connection, name: &str) -> Result<()> {
    conn.execute(
        "INSERT INTO schema_migrations (name, applied_at) VALUES (?1, ?2)",
        params![name, now_millis()],
    )?;
    Ok(())
}

/// Phase 1's row-import half, exposed separately (not just via
/// [`migrate_jsonl_if_needed`]) so CL09's "crash before the marker INSERT" and
/// CL12's "single savepoint, corrupt row rolls back everything imported so far"
/// contracts can be driven directly: a test opens its own savepoint, calls this,
/// and asserts on the *un-committed* transaction before deciding whether to
/// finish (commit) or crash-simulate (drop/rollback without ever calling
/// [`record_marker`]).
pub(crate) fn import_cost_ledger_rows(conn: &Connection, path: &Path) -> Result<usize> {
    let Some(text) = read_optional_utf8(path)? else {
        return Ok(0);
    };
    let mut imported = 0usize;
    for (index, line) in text.lines().enumerate() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        let row: LegacyChargeRow = serde_json::from_str(line).map_err(|err| {
            PipelineError::corrupt(
                path.display().to_string(),
                format!("line {}: {err}", index + 1),
            )
        })?;
        let recorded_at = parse_month(&row.month)
            .map(|(year, month)| month_start_millis(year, month))
            .ok_or_else(|| {
                PipelineError::corrupt(
                    path.display().to_string(),
                    format!("line {}: invalid month {:?}", index + 1, row.month),
                )
            })?;
        conn.execute(
            "INSERT INTO cost_ledger (
                scope_id, adapter_kind, input_hash, tool_profile_hash,
                submission_seq, batch_job_id, usd, estimated, outcome, month, recorded_at
            ) VALUES (?1, ?2, ?3, 'legacy-import', 0, ?4, ?5, 0, 'succeeded', ?6, ?7)",
            params![
                row.scope_id,
                row.adapter_kind,
                format!("sha256:legacy-import-{index:016x}"),
                format!("legacy-import-{index}"),
                row.usd,
                row.month,
                recorded_at,
            ],
        )?;
        imported += 1;
    }
    Ok(imported)
}

fn read_optional_utf8(path: &Path) -> Result<Option<String>> {
    match std::fs::read_to_string(path) {
        Ok(text) => Ok(Some(text)),
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(err) => Err(PipelineError::Io {
            path: path.display().to_string(),
            message: err.to_string(),
        }),
    }
}

/// Phase 2: rename every present legacy file to `<name>.migrated`. Idempotent —
/// a file already renamed (or never present) is silently skipped. Cannot join
/// the phase-1 savepoint (a filesystem rename is not part of the SQLite Tx), so
/// this is always attempted independently, on every call, until it has renamed
/// everything (10 §7.5.3: "savepoint は外部ファイルの rename を含められない").
fn rename_legacy_files(jsonl_dir: &Path) -> Result<Vec<String>> {
    let mut renamed = Vec::new();
    for basename in LEGACY_JSONL_BASENAMES {
        let source: PathBuf = jsonl_dir.join(basename);
        if !source.exists() {
            continue;
        }
        let dest = jsonl_dir.join(format!("{basename}.migrated"));
        std::fs::rename(&source, &dest).map_err(|err| PipelineError::Io {
            path: source.display().to_string(),
            message: err.to_string(),
        })?;
        renamed.push((*basename).to_owned());
    }
    Ok(renamed)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ledger::schema::LedgerDb;

    fn open_temp() -> (tempfile::TempDir, LedgerDb) {
        let dir = tempfile::tempdir().unwrap();
        let db = LedgerDb::open(dir.path().join("cost-ledger.sqlite")).unwrap();
        (dir, db)
    }

    fn write_jsonl(dir: &Path, name: &str, lines: &[&str]) {
        let mut text = lines.join("\n");
        if !lines.is_empty() {
            text.push('\n');
        }
        std::fs::write(dir.join(name), text).unwrap();
    }

    // CL09: crash between import and the marker INSERT (simulated by opening a
    // savepoint, importing, and dropping the connection without ever calling
    // record_marker or committing) leaves zero imported rows, no marker, and the
    // old JSONL files untouched.
    #[test]
    fn cl09_crash_before_marker_commit_leaves_no_partial_import() {
        let jsonl_dir = tempfile::tempdir().unwrap();
        write_jsonl(
            jsonl_dir.path(),
            "cost-ledger.jsonl",
            &[r#"{"month":"2026-07","scope_id":"scope-a","adapter_kind":"markdownize","usd":1.5}"#],
        );
        let db_dir = tempfile::tempdir().unwrap();
        let db_path = db_dir.path().join("cost-ledger.sqlite");
        {
            let db = LedgerDb::open(&db_path).unwrap();
            // Simulate "kill -9 immediately before the marker INSERT": open the
            // same savepoint migrate_jsonl_if_needed would, import, then abandon
            // (rollback) without ever recording the marker.
            db.conn.execute_batch("SAVEPOINT crash_sim;").unwrap();
            let imported =
                import_cost_ledger_rows(&db.conn, &jsonl_dir.path().join("cost-ledger.jsonl"))
                    .unwrap();
            assert_eq!(imported, 1, "the row was staged inside the savepoint");
            db.conn
                .execute_batch("ROLLBACK TO crash_sim; RELEASE crash_sim;")
                .unwrap();
        }
        let db = LedgerDb::open(&db_path).unwrap();
        let rows: i64 = db
            .conn
            .query_row("SELECT COUNT(*) FROM cost_ledger", [], |row| row.get(0))
            .unwrap();
        assert_eq!(rows, 0, "rolled-back Tx must not leave partial import rows");
        assert!(!marker_present(&db.conn, JSONL_CUTOVER_MARKER).unwrap());
        assert!(
            jsonl_dir.path().join("cost-ledger.jsonl").exists(),
            "phase 2 (rename) must not have run — phase 1 never committed"
        );
        assert!(!jsonl_dir.path().join("cost-ledger.jsonl.migrated").exists());
    }

    // CL10: once the marker exists, re-running never re-imports (row count
    // stable) but does retry the phase-2 rename if it did not finish before.
    #[test]
    fn cl10_marker_present_skips_import_but_retries_rename() {
        let jsonl_dir = tempfile::tempdir().unwrap();
        write_jsonl(
            jsonl_dir.path(),
            "cost-ledger.jsonl",
            &[r#"{"month":"2026-07","scope_id":"scope-a","adapter_kind":"markdownize","usd":2.0}"#],
        );
        let (_db_dir, db) = open_temp();
        // Phase 1 already completed (marker present, row imported) but phase 2
        // (rename) crashed before it ran.
        db.conn.execute_batch("SAVEPOINT setup;").unwrap();
        import_cost_ledger_rows(&db.conn, &jsonl_dir.path().join("cost-ledger.jsonl")).unwrap();
        record_marker(&db.conn, JSONL_CUTOVER_MARKER).unwrap();
        db.conn.execute_batch("RELEASE setup;").unwrap();

        let before: i64 = db
            .conn
            .query_row("SELECT COUNT(*) FROM cost_ledger", [], |row| row.get(0))
            .unwrap();
        assert_eq!(before, 1);

        let outcome = migrate_jsonl_if_needed(&db.conn, jsonl_dir.path()).unwrap();
        assert!(outcome.already_migrated);
        assert_eq!(outcome.imported_rows, 0, "must not re-import");
        assert_eq!(outcome.renamed_files, vec!["cost-ledger.jsonl".to_owned()]);

        let after: i64 = db
            .conn
            .query_row("SELECT COUNT(*) FROM cost_ledger", [], |row| row.get(0))
            .unwrap();
        assert_eq!(after, 1, "row count must be unchanged by the retry");
        assert!(jsonl_dir.path().join("cost-ledger.jsonl.migrated").exists());
        assert!(!jsonl_dir.path().join("cost-ledger.jsonl").exists());

        // Idempotent third call: nothing left to rename, still succeeds.
        let again = migrate_jsonl_if_needed(&db.conn, jsonl_dir.path()).unwrap();
        assert!(again.renamed_files.is_empty());
    }

    // CL11: an empty (0-byte) legacy file still produces a marker recording
    // "0 rows imported", distinguishable on replay from "never migrated".
    #[test]
    fn cl11_empty_legacy_file_still_gets_a_marker() {
        let jsonl_dir = tempfile::tempdir().unwrap();
        std::fs::write(jsonl_dir.path().join("cost-ledger.jsonl"), "").unwrap();
        let (_db_dir, db) = open_temp();

        let first = migrate_jsonl_if_needed(&db.conn, jsonl_dir.path()).unwrap();
        assert!(!first.already_migrated);
        assert_eq!(first.imported_rows, 0);
        assert!(marker_present(&db.conn, JSONL_CUTOVER_MARKER).unwrap());

        // Re-running must recognize "already migrated" from the marker alone,
        // not misread the 0 prior rows as "never imported".
        let second = migrate_jsonl_if_needed(&db.conn, jsonl_dir.path()).unwrap();
        assert!(second.already_migrated);
    }

    // CL12: a corrupt row (here: a CHECK-violating negative usd) aborts the
    // entire savepoint — zero rows land, no marker, no rename.
    #[test]
    fn cl12_corrupt_row_rolls_back_the_whole_savepoint() {
        let jsonl_dir = tempfile::tempdir().unwrap();
        write_jsonl(
            jsonl_dir.path(),
            "cost-ledger.jsonl",
            &[
                r#"{"month":"2026-07","scope_id":"scope-a","adapter_kind":"markdownize","usd":1.0}"#,
                r#"{"month":"2026-07","scope_id":"scope-a","adapter_kind":"markdownize","usd":-5.0}"#,
            ],
        );
        let (_db_dir, db) = open_temp();
        let err = migrate_jsonl_if_needed(&db.conn, jsonl_dir.path()).unwrap_err();
        assert!(matches!(err, PipelineError::Sqlite(_)), "got {err:?}");

        let rows: i64 = db
            .conn
            .query_row("SELECT COUNT(*) FROM cost_ledger", [], |row| row.get(0))
            .unwrap();
        assert_eq!(rows, 0, "the first (valid) row must not survive either");
        assert!(!marker_present(&db.conn, JSONL_CUTOVER_MARKER).unwrap());
        assert!(jsonl_dir.path().join("cost-ledger.jsonl").exists());
    }

    #[test]
    fn all_four_legacy_basenames_are_renamed_when_present() {
        let jsonl_dir = tempfile::tempdir().unwrap();
        for name in LEGACY_JSONL_BASENAMES {
            std::fs::write(jsonl_dir.path().join(name), "").unwrap();
        }
        let (_db_dir, db) = open_temp();
        let outcome = migrate_jsonl_if_needed(&db.conn, jsonl_dir.path()).unwrap();
        assert_eq!(outcome.renamed_files.len(), LEGACY_JSONL_BASENAMES.len());
        for name in LEGACY_JSONL_BASENAMES {
            assert!(jsonl_dir.path().join(format!("{name}.migrated")).exists());
            assert!(!jsonl_dir.path().join(name).exists());
        }
    }
}
