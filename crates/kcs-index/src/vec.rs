//! sqlite-vec extension registration.
//!
//! `sqlite-vec` ships the `vec0` virtual table module (`chunk_vec`, 04 §4.3) and
//! the vector helper functions. It is registered with libsqlite3 via
//! `sqlite3_auto_extension`, which installs the module for **every connection
//! opened afterwards in this process**. We therefore register exactly once, as
//! early as possible, before any `Connection::open` touches `chunk_vec`.
//!
//! Compatibility note: the crate binds against the same bundled libsqlite3-sys
//! that `rusqlite` (0.32, `bundled`) links, using `SQLITE_EXTENSION_INIT` (the
//! init function receives libsqlite3's api table at load time), so no separate
//! SQLite build is pulled in and the vec0 requirement is met against bundled
//! rusqlite without downgrading `chunk_vec` to a plain table.

use std::sync::Once;

static REGISTER: Once = Once::new();

/// Register the sqlite-vec auto-extension exactly once for this process. Safe to
/// call repeatedly and from every connection-opening path.
pub fn ensure_registered() {
    REGISTER.call_once(|| {
        // SAFETY: `sqlite3_auto_extension` records a global init callback consumed
        // by libsqlite3 when a connection opens. `sqlite3_vec_init` matches the
        // expected `xEntryPoint` signature. Called once (guarded by `Once`) before
        // any connection that references `chunk_vec`.
        #[allow(clippy::missing_transmute_annotations)]
        unsafe {
            rusqlite::ffi::sqlite3_auto_extension(Some(std::mem::transmute(
                sqlite_vec::sqlite3_vec_init as *const (),
            )));
        }
    });
}

#[cfg(test)]
mod tests {
    use rusqlite::Connection;

    #[test]
    fn sqlite_vec_vec0_module_is_available() {
        super::ensure_registered();
        let conn = Connection::open_in_memory().unwrap();
        conn.execute_batch(
            "CREATE VIRTUAL TABLE chunk_vec USING vec0(chunk_id TEXT PRIMARY KEY, embedding float[3] distance_metric=cosine);",
        )
        .unwrap();
        // A unit vector along x; query along x should be the nearest.
        let v = |x: f32, y: f32, z: f32| -> Vec<u8> {
            [x, y, z].iter().flat_map(|f| f.to_le_bytes()).collect()
        };
        conn.execute(
            "INSERT INTO chunk_vec(chunk_id, embedding) VALUES ('a', ?1)",
            [v(1.0, 0.0, 0.0)],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO chunk_vec(chunk_id, embedding) VALUES ('b', ?1)",
            [v(0.0, 1.0, 0.0)],
        )
        .unwrap();
        let mut stmt = conn
            .prepare(
                "SELECT chunk_id, distance FROM chunk_vec WHERE embedding MATCH ?1 ORDER BY distance LIMIT ?2",
            )
            .unwrap();
        let rows = stmt
            .query_map(rusqlite::params![v(1.0, 0.0, 0.0), 2i64], |row| {
                row.get::<_, String>(0)
            })
            .unwrap()
            .collect::<Result<Vec<_>, _>>()
            .unwrap();
        assert_eq!(rows[0], "a");
        // Read the stored vector back as raw f32 bytes for the MMR path.
        let blob: Vec<u8> = conn
            .query_row(
                "SELECT embedding FROM chunk_vec WHERE chunk_id = 'a'",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(blob.len(), 12);
    }
}
