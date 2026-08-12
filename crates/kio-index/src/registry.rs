//! Device-local scope registry (`~/.local/share/kio/scope-registry.sqlite`).
//!
//! The registry is a search cache, never truth (03-data-model.md §4): it lists
//! candidate scopes for multi-scope search (05-runtime.md §1.8) and resolves
//! `scope_id -> kio_path` for Evidence Pointers (08-evidence-pointer-spec.md
//! §3.1). Losing it must be recoverable by re-running `kio init` / `kio index`
//! in each scope.

use std::path::{Path, PathBuf};
use std::time::Duration;

use rusqlite::{params, Connection, OptionalExtension};

use crate::Result;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RegistryEntry {
    pub scope_id: String,
    /// Absolute path of the `.kio` directory (truth root).
    pub kio_path: String,
    /// Absolute path of the folder that contains `.kio`.
    pub root_path: String,
    pub participates_in_global_search: bool,
    /// True once the scope has a search index (`kio index` completed).
    pub indexed: bool,
    pub last_seen_at: String,
}

pub struct RegistryDb {
    conn: Connection,
}

/// `$XDG_DATA_HOME/kio/scope-registry.sqlite`, falling back to
/// `$HOME/.local/share/kio/scope-registry.sqlite` (03-data-model.md §4).
pub fn default_registry_path() -> Result<PathBuf> {
    // R12-6 / R13-6: honor the XDG validity rules AND require an absolute `HOME`
    // for the fallback (empty/relative treated as unset), so neither a bad
    // `XDG_DATA_HOME` nor a bad `HOME` lands the registry in a CWD-relative `kio/`.
    let data_home = kio_core::xdg::xdg_dir("XDG_DATA_HOME")
        .or_else(|| kio_core::xdg::home_dir().map(|home| home.join(".local/share")))
        .ok_or_else(|| {
            crate::IndexError::Schema(
                "cannot resolve an absolute user data directory; refusing a CWD-relative registry"
                    .to_owned(),
            )
        })?;
    Ok(data_home.join("kio/scope-registry.sqlite"))
}

impl RegistryDb {
    pub fn open(path: impl AsRef<Path>) -> Result<Self> {
        if let Some(parent) = path.as_ref().parent() {
            std::fs::create_dir_all(parent)
                .map_err(|err| crate::IndexError::Schema(err.to_string()))?;
            // P2: the device data dir (`~/.local/share/kio`) that holds this
            // registry, the cost ledger, logs and the open-cache carries usage
            // patterns and the scope map — restrict it to the owner (0700) so a
            // multi-user host cannot read another user's data. Best-effort (the
            // registry is a recoverable cache); no-op on non-unix.
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                let _ = std::fs::set_permissions(parent, std::fs::Permissions::from_mode(0o700));
            }
        }
        let conn = Connection::open(path)?;
        // P6 (05 §1.8 / docs/05:565): serialize concurrent writers with WAL +
        // busy_timeout so a parallel `kio init`/`index` upsert waits (up to 5s)
        // for the write lock instead of hitting SQLITE_BUSY and silently dropping
        // the scope registration, and so a concurrent reader sees the last
        // committed snapshot rather than a transient open failure. WAL is a
        // persistent DB property; busy_timeout is per-connection.
        conn.busy_timeout(Duration::from_millis(5000))?;
        let _journal_mode: String =
            conn.query_row("PRAGMA journal_mode=WAL", [], |row| row.get(0))?;
        conn.execute_batch(
            "CREATE TABLE IF NOT EXISTS scopes (
                scope_id TEXT NOT NULL,
                kio_path TEXT NOT NULL,
                root_path TEXT NOT NULL,
                participates_in_global_search INTEGER NOT NULL DEFAULT 1,
                indexed INTEGER NOT NULL DEFAULT 0,
                last_seen_at TEXT NOT NULL,
                PRIMARY KEY (scope_id, kio_path)
            );",
        )?;
        Ok(Self { conn })
    }

    pub fn open_default() -> Result<Self> {
        Self::open(default_registry_path()?)
    }

    /// R15-3: retire every registration for `kio_path` whose `scope_id` differs
    /// from `current_scope_id`, returning the number of rows removed. A deleted-
    /// then-re-`init`ed `.kio` mints a FRESH `scope_id` at the SAME path; because
    /// the primary key is `(scope_id, kio_path)`, the stale row otherwise survives
    /// forever and multi-scope search returns the same document twice — once via the
    /// dead `scope_id` whose Evidence Pointers can no longer resolve
    /// (`KIO-E-EVIDENCE-SCOPE-UNREACHABLE-001`). The registry is a recoverable search
    /// cache (03 §4), so dropping a stale row is always safe: the live scope re-adds
    /// itself here. Call this immediately before [`upsert`](Self::upsert).
    pub fn retire_stale_kio_path(&self, kio_path: &str, current_scope_id: &str) -> Result<usize> {
        let removed = self.conn.execute(
            "DELETE FROM scopes WHERE kio_path = ?1 AND scope_id != ?2",
            params![kio_path, current_scope_id],
        )?;
        Ok(removed)
    }

    pub fn upsert(&self, entry: &RegistryEntry) -> Result<()> {
        self.conn.execute(
            "INSERT INTO scopes (
                scope_id, kio_path, root_path,
                participates_in_global_search, indexed, last_seen_at
            ) VALUES (?1, ?2, ?3, ?4, ?5, ?6)
            ON CONFLICT (scope_id, kio_path) DO UPDATE SET
                root_path = excluded.root_path,
                participates_in_global_search = excluded.participates_in_global_search,
                indexed = MAX(scopes.indexed, excluded.indexed),
                last_seen_at = excluded.last_seen_at",
            params![
                entry.scope_id,
                entry.kio_path,
                entry.root_path,
                entry.participates_in_global_search as i64,
                entry.indexed as i64,
                entry.last_seen_at,
            ],
        )?;
        Ok(())
    }

    /// Scopes eligible for default cross-scope search (05-runtime.md §1.8):
    /// `participates_in_global_search = true` and indexed. Deterministic order.
    pub fn search_targets(&self) -> Result<Vec<RegistryEntry>> {
        self.query_entries(
            "SELECT scope_id, kio_path, root_path,
                    participates_in_global_search, indexed, last_seen_at
             FROM scopes
             WHERE participates_in_global_search = 1 AND indexed = 1
             ORDER BY root_path, scope_id",
            params![],
        )
    }

    /// All registrations for a scope_id, most recently seen first
    /// (08-evidence-pointer-spec.md §3.1 step 1b).
    pub fn lookup_scope_id(&self, scope_id: &str) -> Result<Vec<RegistryEntry>> {
        self.query_entries(
            "SELECT scope_id, kio_path, root_path,
                    participates_in_global_search, indexed, last_seen_at
             FROM scopes
             WHERE scope_id = ?1
             ORDER BY last_seen_at DESC, kio_path",
            params![scope_id],
        )
    }

    pub fn get(&self, scope_id: &str, kio_path: &str) -> Result<Option<RegistryEntry>> {
        let entry = self
            .conn
            .query_row(
                "SELECT scope_id, kio_path, root_path,
                        participates_in_global_search, indexed, last_seen_at
                 FROM scopes
                 WHERE scope_id = ?1 AND kio_path = ?2",
                params![scope_id, kio_path],
                row_to_entry,
            )
            .optional()?;
        Ok(entry)
    }

    /// Every registration, deterministic order — PB25's `--registry-prune`
    /// (step4b-contract-tests-p2b.md §H) enumerates the whole table to find
    /// unreachable rows, not just search targets or one scope_id's rows.
    pub fn all_entries(&self) -> Result<Vec<RegistryEntry>> {
        self.query_entries(
            "SELECT scope_id, kio_path, root_path,
                    participates_in_global_search, indexed, last_seen_at
             FROM scopes
             ORDER BY root_path, scope_id",
            params![],
        )
    }

    /// PB25: remove one `(scope_id, kio_path)` registration — used only for a
    /// row proven unreachable (no re-init, no re-discovery possible); a live
    /// duplicate is never removed here (PB21's fail-closed dedupe is a user
    /// decision, not automatic).
    pub fn remove(&self, scope_id: &str, kio_path: &str) -> Result<bool> {
        let removed = self.conn.execute(
            "DELETE FROM scopes WHERE scope_id = ?1 AND kio_path = ?2",
            params![scope_id, kio_path],
        )?;
        Ok(removed > 0)
    }

    fn query_entries(
        &self,
        sql: &str,
        params: impl rusqlite::Params,
    ) -> Result<Vec<RegistryEntry>> {
        let mut stmt = self.conn.prepare(sql)?;
        let rows = stmt.query_map(params, row_to_entry)?;
        let mut entries = Vec::new();
        for row in rows {
            entries.push(row?);
        }
        Ok(entries)
    }
}

fn row_to_entry(row: &rusqlite::Row<'_>) -> rusqlite::Result<RegistryEntry> {
    Ok(RegistryEntry {
        scope_id: row.get(0)?,
        kio_path: row.get(1)?,
        root_path: row.get(2)?,
        participates_in_global_search: row.get::<_, i64>(3)? != 0,
        indexed: row.get::<_, i64>(4)? != 0,
        last_seen_at: row.get(5)?,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn entry(scope_id: &str, root: &str, participates: bool, indexed: bool) -> RegistryEntry {
        RegistryEntry {
            scope_id: scope_id.to_owned(),
            kio_path: format!("{root}/.kio"),
            root_path: root.to_owned(),
            participates_in_global_search: participates,
            indexed,
            last_seen_at: "2026-07-03T00:00:00Z".to_owned(),
        }
    }

    fn open_temp() -> (tempfile::TempDir, RegistryDb) {
        let dir = tempfile::tempdir().unwrap();
        let db = RegistryDb::open(dir.path().join("scope-registry.sqlite")).unwrap();
        (dir, db)
    }

    #[test]
    fn open_sets_wal_and_busy_timeout() {
        // P6: the registry must open with WAL + a 5000ms busy_timeout so parallel
        // init/index writers serialize instead of silently dropping registrations.
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
        assert_eq!(timeout, 5000);
    }

    #[test]
    fn search_targets_filters_participation_and_indexed() {
        let (_dir, db) = open_temp();
        db.upsert(&entry("scope_a", "/tmp/a", true, true)).unwrap();
        db.upsert(&entry("scope_b", "/tmp/b", false, true)).unwrap();
        db.upsert(&entry("scope_c", "/tmp/c", true, false)).unwrap();
        let targets = db.search_targets().unwrap();
        assert_eq!(targets.len(), 1);
        assert_eq!(targets[0].scope_id, "scope_a");
    }

    #[test]
    fn upsert_is_idempotent_and_updates_fields() {
        let (_dir, db) = open_temp();
        db.upsert(&entry("scope_a", "/tmp/a", true, false)).unwrap();
        let mut updated = entry("scope_a", "/tmp/a", true, true);
        updated.last_seen_at = "2026-07-04T00:00:00Z".to_owned();
        db.upsert(&updated).unwrap();
        let got = db.get("scope_a", "/tmp/a/.kio").unwrap().unwrap();
        assert!(got.indexed);
        assert_eq!(got.last_seen_at, "2026-07-04T00:00:00Z");
        assert_eq!(db.lookup_scope_id("scope_a").unwrap().len(), 1);
    }

    #[test]
    fn indexed_flag_is_not_cleared_by_later_unindexed_upsert() {
        let (_dir, db) = open_temp();
        db.upsert(&entry("scope_a", "/tmp/a", true, true)).unwrap();
        db.upsert(&entry("scope_a", "/tmp/a", true, false)).unwrap();
        assert!(db.get("scope_a", "/tmp/a/.kio").unwrap().unwrap().indexed);
    }

    // R15-3: a deleted-then-re-`init`ed `.kio` mints a fresh scope_id at the same
    // path. Retiring the stale row before re-registering leaves exactly one row for
    // that path (no duplicate search target, no dead-pointer scope_id).
    #[test]
    fn retire_stale_kio_path_removes_only_other_scope_ids_at_same_path() {
        let (_dir, db) = open_temp();
        // Old scope_id registered + indexed at /tmp/a.
        db.upsert(&entry("scope_old", "/tmp/a", true, true))
            .unwrap();
        // An unrelated path must be untouched.
        db.upsert(&entry("scope_x", "/tmp/other", true, true))
            .unwrap();

        // Re-init: fresh scope_id at the SAME `.kio` path. Retire, then re-register.
        let removed = db
            .retire_stale_kio_path("/tmp/a/.kio", "scope_new")
            .unwrap();
        assert_eq!(removed, 1, "exactly the stale same-path row is retired");
        db.upsert(&entry("scope_new", "/tmp/a", true, true))
            .unwrap();

        // Only the fresh registration survives at /tmp/a.
        assert!(db.lookup_scope_id("scope_old").unwrap().is_empty());
        assert_eq!(db.lookup_scope_id("scope_new").unwrap().len(), 1);
        // The unrelated path is untouched.
        assert_eq!(db.lookup_scope_id("scope_x").unwrap().len(), 1);
        // Exactly one search target remains for the re-init'd path.
        let targets = db.search_targets().unwrap();
        assert_eq!(
            targets
                .iter()
                .filter(|t| t.kio_path == "/tmp/a/.kio")
                .count(),
            1
        );
    }

    #[test]
    fn lookup_scope_id_orders_by_last_seen_desc() {
        let (_dir, db) = open_temp();
        let mut old = entry("scope_a", "/tmp/old", true, true);
        old.last_seen_at = "2026-07-01T00:00:00Z".to_owned();
        db.upsert(&old).unwrap();
        let mut new = entry("scope_a", "/tmp/new", true, true);
        new.last_seen_at = "2026-07-02T00:00:00Z".to_owned();
        db.upsert(&new).unwrap();
        let found = db.lookup_scope_id("scope_a").unwrap();
        assert_eq!(found[0].root_path, "/tmp/new");
    }

    // PB25 (step4b-contract-tests-p2b.md §H): `all_entries`/`remove` are the
    // primitives `kio repair registry-prune` uses to enumerate the whole
    // table and delete a proven-unreachable row.
    #[test]
    fn all_entries_lists_every_row_and_remove_deletes_exactly_one() {
        let (_dir, db) = open_temp();
        db.upsert(&entry("scope_a", "/tmp/a", true, true)).unwrap();
        db.upsert(&entry("scope_b", "/tmp/b", true, true)).unwrap();
        assert_eq!(db.all_entries().unwrap().len(), 2);

        assert!(db.remove("scope_a", "/tmp/a/.kio").unwrap());
        let remaining = db.all_entries().unwrap();
        assert_eq!(remaining.len(), 1);
        assert_eq!(remaining[0].scope_id, "scope_b");

        // Idempotent: removing an already-absent row is `false`, not an error.
        assert!(!db.remove("scope_a", "/tmp/a/.kio").unwrap());
    }
}
