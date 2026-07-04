//! Device-local scope registry (`~/.local/share/kcs/scope-registry.sqlite`).
//!
//! The registry is a search cache, never truth (03-data-model.md §4): it lists
//! candidate scopes for multi-scope search (05-runtime.md §1.8) and resolves
//! `scope_id -> kcs_path` for Evidence Pointers (08-evidence-pointer-spec.md
//! §3.1). Losing it must be recoverable by re-running `kcs init` / `kcs index`
//! in each scope.

use std::path::{Path, PathBuf};
use std::time::Duration;

use rusqlite::{params, Connection, OptionalExtension};

use crate::Result;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RegistryEntry {
    pub scope_id: String,
    /// Absolute path of the `.kcs` directory (truth root).
    pub kcs_path: String,
    /// Absolute path of the folder that contains `.kcs`.
    pub root_path: String,
    pub participates_in_global_search: bool,
    /// True once the scope has a search index (`kcs index` completed).
    pub indexed: bool,
    pub last_seen_at: String,
}

pub struct RegistryDb {
    conn: Connection,
}

/// `$XDG_DATA_HOME/kcs/scope-registry.sqlite`, falling back to
/// `$HOME/.local/share/kcs/scope-registry.sqlite` (03-data-model.md §4).
#[must_use]
pub fn default_registry_path() -> PathBuf {
    let data_home = if let Some(path) = std::env::var_os("XDG_DATA_HOME") {
        PathBuf::from(path)
    } else if let Some(home) = std::env::var_os("HOME") {
        PathBuf::from(home).join(".local/share")
    } else {
        PathBuf::from(".")
    };
    data_home.join("kcs/scope-registry.sqlite")
}

impl RegistryDb {
    pub fn open(path: impl AsRef<Path>) -> Result<Self> {
        if let Some(parent) = path.as_ref().parent() {
            std::fs::create_dir_all(parent)
                .map_err(|err| crate::IndexError::Schema(err.to_string()))?;
            // P2: the device data dir (`~/.local/share/kcs`) that holds this
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
        // busy_timeout so a parallel `kcs init`/`index` upsert waits (up to 5s)
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
                kcs_path TEXT NOT NULL,
                root_path TEXT NOT NULL,
                participates_in_global_search INTEGER NOT NULL DEFAULT 1,
                indexed INTEGER NOT NULL DEFAULT 0,
                last_seen_at TEXT NOT NULL,
                PRIMARY KEY (scope_id, kcs_path)
            );",
        )?;
        Ok(Self { conn })
    }

    pub fn open_default() -> Result<Self> {
        Self::open(default_registry_path())
    }

    pub fn upsert(&self, entry: &RegistryEntry) -> Result<()> {
        self.conn.execute(
            "INSERT INTO scopes (
                scope_id, kcs_path, root_path,
                participates_in_global_search, indexed, last_seen_at
            ) VALUES (?1, ?2, ?3, ?4, ?5, ?6)
            ON CONFLICT (scope_id, kcs_path) DO UPDATE SET
                root_path = excluded.root_path,
                participates_in_global_search = excluded.participates_in_global_search,
                indexed = MAX(scopes.indexed, excluded.indexed),
                last_seen_at = excluded.last_seen_at",
            params![
                entry.scope_id,
                entry.kcs_path,
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
            "SELECT scope_id, kcs_path, root_path,
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
            "SELECT scope_id, kcs_path, root_path,
                    participates_in_global_search, indexed, last_seen_at
             FROM scopes
             WHERE scope_id = ?1
             ORDER BY last_seen_at DESC, kcs_path",
            params![scope_id],
        )
    }

    pub fn get(&self, scope_id: &str, kcs_path: &str) -> Result<Option<RegistryEntry>> {
        let entry = self
            .conn
            .query_row(
                "SELECT scope_id, kcs_path, root_path,
                        participates_in_global_search, indexed, last_seen_at
                 FROM scopes
                 WHERE scope_id = ?1 AND kcs_path = ?2",
                params![scope_id, kcs_path],
                row_to_entry,
            )
            .optional()?;
        Ok(entry)
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
        kcs_path: row.get(1)?,
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
            kcs_path: format!("{root}/.kcs"),
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
        let got = db.get("scope_a", "/tmp/a/.kcs").unwrap().unwrap();
        assert!(got.indexed);
        assert_eq!(got.last_seen_at, "2026-07-04T00:00:00Z");
        assert_eq!(db.lookup_scope_id("scope_a").unwrap().len(), 1);
    }

    #[test]
    fn indexed_flag_is_not_cleared_by_later_unindexed_upsert() {
        let (_dir, db) = open_temp();
        db.upsert(&entry("scope_a", "/tmp/a", true, true)).unwrap();
        db.upsert(&entry("scope_a", "/tmp/a", true, false)).unwrap();
        assert!(db.get("scope_a", "/tmp/a/.kcs").unwrap().unwrap().indexed);
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
}
