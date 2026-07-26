//! FTS5 external-content index contracts.

use std::collections::BTreeSet;

use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use unicode_normalization::UnicodeNormalization;

use crate::{ChunkRow, IndexError, Result};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FtsTokenizer {
    Trigram,
    Unicode61RemoveDiacritics2,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FtsSchemaConfig {
    pub tokenizer: FtsTokenizer,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct FtsMatch {
    pub chunk_id: String,
    pub rank: u64,
    pub bm25_score: f64,
}

/// Rows removed from the derived index for one purged raw object.
///
/// `chunk_ids` is sorted so callers can deterministically remove the matching
/// chunk CAS objects and durable-ledger records after this transaction commits.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct PurgeRawIndexReport {
    pub chunk_ids: Vec<String>,
    pub deleted_chunks: u64,
    pub deleted_associations: u64,
    pub deleted_chunk_vectors: u64,
    /// `image_vec` rows removed (05 §3.5). Separate from
    /// `deleted_chunk_vectors` because the two are decided by different rules:
    /// a chunk vector goes with its chunk, an image vector only when no
    /// surviving chunk still references the image.
    pub deleted_image_vectors: u64,
    pub deleted_orphan_embeddings: u64,
    /// The `embeddings.id` of every orphan row just deleted — the CAS objects
    /// purge must remove alongside them (05 §3.5). A count cannot name a file,
    /// and the rows are gone by the time the caller could ask.
    pub deleted_embedding_ids: Vec<String>,
}

pub struct SqliteFtsIndex {
    conn: Connection,
}

impl SqliteFtsIndex {
    pub fn open(path: impl AsRef<std::path::Path>, config: FtsSchemaConfig) -> Result<Self> {
        // The `vec0` module must be registered before the connection opens, else
        // the `chunk_vec` virtual table cannot be created or queried (04 §4.3).
        crate::vec::ensure_registered();
        let conn = Connection::open(path)?;
        ensure_schema_on_connection(&conn, config)?;
        Ok(Self { conn })
    }

    pub fn in_memory(config: FtsSchemaConfig) -> Result<Self> {
        crate::vec::ensure_registered();
        let conn = Connection::open_in_memory()?;
        ensure_schema_on_connection(&conn, config)?;
        Ok(Self { conn })
    }

    #[must_use]
    pub fn connection(&self) -> &Connection {
        &self.conn
    }

    pub fn ensure_schema(&mut self, config: FtsSchemaConfig) -> Result<()> {
        ensure_schema_on_connection(&self.conn, config)
    }

    pub fn index_chunk(&mut self, row: &ChunkRow) -> Result<()> {
        self.index_chunk_with_association_rowid(row, None)
            .map(|_| ())
    }

    /// Insert an immutable chunk row and append its chunking-config generation.
    ///
    /// Fresh indexing passes `None` and lets SQLite allocate the monotonically
    /// increasing association rowid. Durable-ledger replay may pass the recorded
    /// rowid so a rebuilt database preserves cursor ordering exactly.
    /// `row.chunking_config_introduction_commit` (PC40) is recorded exactly as
    /// [`Self::index_chunk_with_rowids`] does — `None` unless the caller's
    /// `row` carries one.
    pub fn index_chunk_with_association_rowid(
        &mut self,
        row: &ChunkRow,
        association_rowid: Option<u64>,
    ) -> Result<u64> {
        self.index_chunk_with_rowids(row, None, association_rowid)
            .map(|(_, association_rowid)| association_rowid)
    }

    /// Replay one durable chunk/config ledger record with stable rowids.
    ///
    /// `chunk_rowid` is shared by every association record for the immutable
    /// chunk. Both explicit rowids are collision-checked inside one savepoint so
    /// a malformed ledger cannot partially publish either side of the relation.
    ///
    /// `row.chunking_config_introduction_commit` (PC40, 05 §1.6 L266) is the
    /// commit at which THIS `(chunk_id, chunking_config_hash)` association was
    /// created — read from the row rather than taken as a separate parameter
    /// so a rebuild replaying an already-durable `chunks.jsonl` record cannot
    /// accidentally re-stamp it with "today's HEAD" (it is stamped only when
    /// the association is genuinely new, matching
    /// `record_chunk_config_association`'s existing-row branch, which never
    /// touches an already-existing row's `introduction_commit`). Chunk-level
    /// publication events (PC37, potentially several per chunk) are a
    /// separate, caller-driven concern — see [`record_chunk_publication`].
    pub fn index_chunk_with_rowids(
        &mut self,
        row: &ChunkRow,
        chunk_rowid: Option<u64>,
        association_rowid: Option<u64>,
    ) -> Result<(u64, u64)> {
        let association_introduction_commit = row.chunking_config_introduction_commit.as_deref();
        if chunk_rowid == Some(0) {
            return Err(IndexError::Contract(
                "chunk rowid must be positive".to_owned(),
            ));
        }
        // Q4: the trigram tokenizer stops at a NUL byte, so any text after a
        // U+0000 (e.g. a UTF-16-LE `.txt` decoded lossily keeps interleaved NULs)
        // would be silently unsearchable even though `index` reported success.
        // Strip NULs from the value bound into the external-content `text` column
        // (which feeds `chunk_fts`) so the whole chunk is tokenizable. Identity /
        // evidence are untouched: `chunk_id`, `text_hash`, `byte_start/end` and the
        // persisted `chunks.jsonl` / normalized markdown all still carry the
        // original bytes — only this derived search index projection is sanitized.
        //
        // F2: normalize the projection to NFC first. The trigram tokenizer is not
        // Unicode-normalizing, so NFD content (common on macOS/APFS, some IMEs, and
        // OCR/PDF extraction) would be silently unsearchable by an NFC query and
        // vice versa. The CLI query path is normalized to the same NFC form, so
        // canonically-equivalent content and queries match regardless of input
        // form. This is a derived-index projection only; the char offsets that
        // evidence resolves against remain over the original `row.text`.
        let indexed_text = row.text.nfc().collect::<String>().replace('\u{0}', "");
        with_savepoint(&self.conn, "kio_index_chunk", || {
            let requested_chunk_rowid = chunk_rowid.map(sql_rowid).transpose()?;
            let existing_chunk_rowid = self
                .conn
                .query_row(
                    "SELECT rowid FROM chunks WHERE chunk_id = ?1",
                    params![row.chunk_id],
                    |result| result.get::<_, i64>(0),
                )
                .optional()?;
            let actual_chunk_rowid = match existing_chunk_rowid {
                Some(existing) => {
                    if requested_chunk_rowid.is_some_and(|requested| requested != existing) {
                        return Err(IndexError::Contract(format!(
                            "chunk {} has rowid {existing}, not requested rowid {}",
                            row.chunk_id,
                            requested_chunk_rowid.expect("checked as some")
                        )));
                    }
                    existing
                }
                None => {
                    let heading_path =
                        serde_json::to_string(&row.heading_path.clone().unwrap_or_default())?;
                    if let Some(requested) = requested_chunk_rowid {
                        let occupied = self
                            .conn
                            .query_row(
                                "SELECT chunk_id FROM chunks WHERE rowid = ?1",
                                params![requested],
                                |result| result.get::<_, String>(0),
                            )
                            .optional()?;
                        if let Some(occupied) = occupied {
                            return Err(IndexError::Contract(format!(
                                "chunk rowid {requested} is already occupied by {occupied}"
                            )));
                        }
                        self.conn.execute(
                            "INSERT INTO chunks(
                                rowid, chunk_id, raw_hash, tool_profile_hash, gen, unit_key,
                                raw_path, heading_path, section_id, byte_start, byte_end,
                                text_hash, text, first_seen_commit, created_at
                             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15)",
                            params![
                                requested,
                                row.chunk_id,
                                row.raw_hash,
                                row.tool_profile_hash,
                                row.gen,
                                row.unit_key,
                                row.raw_path,
                                heading_path,
                                row.section_id,
                                row.byte_start,
                                row.byte_end,
                                row.text_hash,
                                indexed_text,
                                row.first_seen_commit,
                                row.created_at,
                            ],
                        )?;
                        requested
                    } else {
                        self.conn.execute(
                            "INSERT INTO chunks(
                                chunk_id, raw_hash, tool_profile_hash, gen, unit_key,
                                raw_path, heading_path, section_id, byte_start, byte_end,
                                text_hash, text, first_seen_commit, created_at
                             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14)",
                            params![
                                row.chunk_id,
                                row.raw_hash,
                                row.tool_profile_hash,
                                row.gen,
                                row.unit_key,
                                row.raw_path,
                                heading_path,
                                row.section_id,
                                row.byte_start,
                                row.byte_end,
                                row.text_hash,
                                indexed_text,
                                row.first_seen_commit,
                                row.created_at,
                            ],
                        )?;
                        self.conn.last_insert_rowid()
                    }
                }
            };
            let association_rowid = record_chunk_config_association(
                &self.conn,
                &row.chunk_id,
                &row.chunking_config_hash,
                &row.created_at,
                association_rowid,
                association_introduction_commit,
            )?;
            Ok((sql_u64_rowid(actual_chunk_rowid)?, association_rowid))
        })
    }

    /// Transactionally remove every derived-index row owned by `raw_hash`.
    ///
    /// Embeddings are keyed by normalized text rather than raw objects, so an
    /// embedding is removed only when no surviving chunk references its text
    /// hash. `tree_entries` is intentionally untouched: immutable commit/tree
    /// history is governed by the purge tombstone/barrier rather than rewritten.
    pub fn purge_raw(
        &mut self,
        raw_hash: &str,
        orphaned_image_hashes: &BTreeSet<String>,
    ) -> Result<PurgeRawIndexReport> {
        with_savepoint(&self.conn, "kio_purge_raw", || {
            let targets = {
                let mut statement = self.conn.prepare(
                    "SELECT chunk_id, text_hash
                     FROM chunks
                     WHERE raw_hash = ?1
                     ORDER BY chunk_id",
                )?;
                let rows = statement.query_map(params![raw_hash], |row| {
                    Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
                })?;
                rows.collect::<std::result::Result<Vec<_>, _>>()?
            };

            let mut report = PurgeRawIndexReport {
                chunk_ids: targets
                    .iter()
                    .map(|(chunk_id, _)| chunk_id.clone())
                    .collect(),
                ..PurgeRawIndexReport::default()
            };
            let text_hashes = targets
                .iter()
                .map(|(_, text_hash)| text_hash.clone())
                .collect::<BTreeSet<_>>();

            for (chunk_id, _) in &targets {
                report.deleted_chunk_vectors += u64::try_from(self.conn.execute(
                    "DELETE FROM chunk_vec WHERE chunk_id = ?1",
                    params![chunk_id],
                )?)
                .map_err(|_| IndexError::Contract("deleted row count exceeds u64".to_owned()))?;
                report.deleted_associations += u64::try_from(self.conn.execute(
                    "DELETE FROM chunk_config_generations WHERE chunk_id = ?1",
                    params![chunk_id],
                )?)
                .map_err(|_| IndexError::Contract("deleted row count exceeds u64".to_owned()))?;
            }

            report.deleted_chunks = u64::try_from(
                self.conn
                    .execute("DELETE FROM chunks WHERE raw_hash = ?1", params![raw_hash])?,
            )
            .map_err(|_| IndexError::Contract("deleted row count exceeds u64".to_owned()))?;

            for text_hash in text_hashes {
                // RETURNING the ids rather than only counting them: the CAS
                // object under `objects/embeddings/<id>` is the same vector and
                // purge has to take it too, but nothing can enumerate the rows
                // once they are deleted.
                let mut orphans = self.conn.prepare(
                    "DELETE FROM embeddings
                     WHERE target_type = 'chunk'
                       AND target_id = ?1
                       AND NOT EXISTS (
                           SELECT 1 FROM chunks WHERE text_hash = ?1 LIMIT 1
                       )
                     RETURNING id",
                )?;
                let ids = orphans.query_map(params![text_hash], |row| row.get::<_, String>(0))?;
                for id in ids {
                    report.deleted_embedding_ids.push(id?);
                    report.deleted_orphan_embeddings += 1;
                }
            }

            // 05 §3.5: image vectors go the same way, on the same
            // live-reference-0 rule. Which images are orphaned is decided by
            // the CALLER, because the answer lives in the Markdown image
            // grammar (`kio://…/object/image/…`) and that parser belongs to
            // kio-search — a second copy of it here is the kind of duplicate
            // liveness rule that drifts. The caller computes
            // "referenced by the purge target, and by nothing that survives"
            // before any row is deleted, and this deletes them inside the same
            // savepoint so the two halves cannot land apart.
            for image_hash in orphaned_image_hashes {
                report.deleted_image_vectors += u64::try_from(self.conn.execute(
                    "DELETE FROM image_vec WHERE image_id = ?1",
                    params![image_hash],
                )?)
                .map_err(|_| IndexError::Contract("deleted row count exceeds u64".to_owned()))?;
                let mut orphans = self.conn.prepare(
                    "DELETE FROM embeddings
                     WHERE target_type = 'image' AND target_id = ?1
                     RETURNING id",
                )?;
                let ids = orphans.query_map(params![image_hash], |row| row.get::<_, String>(0))?;
                for id in ids {
                    report.deleted_embedding_ids.push(id?);
                    report.deleted_orphan_embeddings += 1;
                }
            }

            Ok(report)
        })
    }

    /// Schema/tokenizer contract probe: a bare `chunk_fts MATCH` over the whole
    /// table, used by the CT3-FTS unit tests to pin the external-content
    /// trigger sync and trigram behavior. The production query path is
    /// kio-cli's `execute_fts_tier`, which layers the liveness filters
    /// (tree_entries join, current chunking_config_hash, `rowid <= max_rowid`)
    /// and column-weighted BM25 on the same index.
    pub fn search(&self, query: &str, limit: u64) -> Result<Vec<FtsMatch>> {
        if query.chars().count() < 2 {
            return Ok(Vec::new());
        }
        let sql = "SELECT c.chunk_id, rank
                   FROM chunk_fts f
                   JOIN chunks c ON c.rowid = f.rowid
                   WHERE chunk_fts MATCH ?1
                   ORDER BY rank, c.chunk_id
                   LIMIT ?2";
        let mut stmt = self.conn.prepare(sql)?;
        let rows = stmt.query_map(params![query, limit], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, f64>(1)?))
        })?;
        let mut matches = Vec::new();
        for (index, row) in rows.enumerate() {
            let (chunk_id, bm25_score) = row?;
            matches.push(FtsMatch {
                chunk_id,
                rank: index as u64 + 1,
                bm25_score,
            });
        }
        Ok(matches)
    }
}

/// Append a chunk/config generation association and return its stable rowid.
///
/// The `(chunk_id, chunking_config_hash)` relation is idempotent. When an
/// explicit rowid is supplied (during durable-ledger rebuild), both the pair and
/// rowid must agree with an existing record; a collision is a contract error
/// rather than a silent renumbering that could invalidate signed cursors.
///
/// `introduction_commit` (PC40, 05 §1.6 L266) is stamped only on a genuinely
/// new association row — an already-existing pair's `introduction_commit`
/// never changes on replay, matching every other immutable-once-set column
/// this function's existing-row branch already leaves untouched.
pub fn record_chunk_config_association(
    conn: &Connection,
    chunk_id: &str,
    chunking_config_hash: &str,
    created_at: &str,
    association_rowid: Option<u64>,
    introduction_commit: Option<&str>,
) -> Result<u64> {
    if association_rowid == Some(0) {
        return Err(IndexError::Contract(
            "chunk/config association rowid must be positive".to_owned(),
        ));
    }
    let chunk_exists = conn
        .query_row(
            "SELECT 1 FROM chunks WHERE chunk_id = ?1 LIMIT 1",
            params![chunk_id],
            |_| Ok(()),
        )
        .optional()?
        .is_some();
    if !chunk_exists {
        return Err(IndexError::Contract(format!(
            "cannot associate missing chunk {chunk_id}"
        )));
    }

    let requested_rowid = association_rowid.map(sql_rowid).transpose()?;
    let existing_for_pair = conn
        .query_row(
            "SELECT association_rowid
             FROM chunk_config_generations
             WHERE chunk_id = ?1 AND chunking_config_hash = ?2",
            params![chunk_id, chunking_config_hash],
            |row| row.get::<_, i64>(0),
        )
        .optional()?;

    if let Some(existing_rowid) = existing_for_pair {
        if let Some(requested_rowid) = requested_rowid {
            if existing_rowid != requested_rowid {
                return Err(IndexError::Contract(format!(
                    "chunk/config association {chunk_id}/{chunking_config_hash} has rowid \
                     {existing_rowid}, not requested rowid {requested_rowid}"
                )));
            }
        }
        return sql_u64_rowid(existing_rowid);
    }

    if let Some(requested_rowid) = requested_rowid {
        let occupied = conn
            .query_row(
                "SELECT chunk_id, chunking_config_hash
                 FROM chunk_config_generations
                 WHERE association_rowid = ?1",
                params![requested_rowid],
                |row| Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?)),
            )
            .optional()?;
        if let Some((occupied_chunk, occupied_config)) = occupied {
            return Err(IndexError::Contract(format!(
                "chunk/config association rowid {requested_rowid} is already occupied by \
                 {occupied_chunk}/{occupied_config}"
            )));
        }
        conn.execute(
            "INSERT INTO chunk_config_generations(
                association_rowid, chunk_id, chunking_config_hash, created_at, introduction_commit
             ) VALUES (?1, ?2, ?3, ?4, ?5)",
            params![
                requested_rowid,
                chunk_id,
                chunking_config_hash,
                created_at,
                introduction_commit
            ],
        )?;
        return sql_u64_rowid(requested_rowid);
    }

    conn.execute(
        "INSERT INTO chunk_config_generations(
            chunk_id, chunking_config_hash, created_at, introduction_commit
         ) VALUES (?1, ?2, ?3, ?4)",
        params![
            chunk_id,
            chunking_config_hash,
            created_at,
            introduction_commit
        ],
    )?;
    sql_u64_rowid(conn.last_insert_rowid())
}

/// Maximum generation-association rowid frozen into a page-1 cursor.
/// Empty databases use zero, which cannot name an AUTOINCREMENT row.
pub fn max_chunk_config_association_rowid(conn: &Connection) -> Result<u64> {
    let maximum = conn.query_row(
        "SELECT COALESCE(MAX(association_rowid), 0) FROM chunk_config_generations",
        [],
        |row| row.get::<_, i64>(0),
    )?;
    sql_u64_rowid(maximum)
}

/// Whether a chunk had an association with the effective config at the frozen
/// association maximum.
pub fn chunk_has_current_config_association(
    conn: &Connection,
    chunk_id: &str,
    chunking_config_hash: &str,
    max_association_rowid: u64,
) -> Result<bool> {
    let max_association_rowid = sql_rowid(max_association_rowid)?;
    Ok(conn
        .query_row(
            "SELECT 1
             FROM chunk_config_generations
             WHERE chunk_id = ?1
               AND chunking_config_hash = ?2
               AND association_rowid <= ?3
             LIMIT 1",
            params![chunk_id, chunking_config_hash, max_association_rowid],
            |_| Ok(()),
        )
        .optional()?
        .is_some())
}

/// Return chunks satisfying the shared row/config cursor eligibility filter.
/// Snapshot/tree liveness is intentionally layered on by the caller because it
/// differs between default, `--at`, all-history, and include-deleted modes.
pub fn current_config_eligible_chunk_ids(
    conn: &Connection,
    chunking_config_hash: &str,
    max_chunk_rowid: u64,
    max_association_rowid: u64,
) -> Result<BTreeSet<String>> {
    let max_chunk_rowid = sql_rowid(max_chunk_rowid)?;
    let max_association_rowid = sql_rowid(max_association_rowid)?;
    let mut stmt = conn.prepare(
        "SELECT c.chunk_id
         FROM chunks c
         JOIN chunk_config_generations g ON g.chunk_id = c.chunk_id
         WHERE c.first_seen_commit IS NOT NULL
           AND c.rowid <= ?1
           AND g.chunking_config_hash = ?2
           AND g.association_rowid <= ?3
         ORDER BY c.chunk_id",
    )?;
    let rows = stmt.query_map(
        params![max_chunk_rowid, chunking_config_hash, max_association_rowid],
        |row| row.get::<_, String>(0),
    )?;
    rows.collect::<std::result::Result<BTreeSet<_>, _>>()
        .map_err(IndexError::from)
}

/// PC37 (04 §4.1 / 05 §1.6): append one `(chunk_id, introduction_commit)` row —
/// idempotent (`INSERT OR IGNORE`, `UNIQUE(chunk_id, introduction_commit)`), so
/// re-publishing the same chunk at the same commit (a resurrection, a repeated
/// rebuild pass) never duplicates a row. Distinct commits for the same
/// `chunk_id` accumulate (the multi-introduction case — merge side branches,
/// independent imports — a single `chunks.first_seen_commit` cannot represent).
pub fn record_chunk_publication(
    conn: &Connection,
    chunk_id: &str,
    introduction_commit: &str,
) -> Result<()> {
    conn.execute(
        "INSERT OR IGNORE INTO chunk_publications(chunk_id, introduction_commit)
         VALUES (?1, ?2)",
        params![chunk_id, introduction_commit],
    )?;
    Ok(())
}

/// Every recorded introduction commit for `chunk_id`, in byte order (PC32's
/// deterministic tie-break for a "no directly-matching current value"
/// fallback selects the byte-order-minimum among these). Empty when the chunk
/// has no `chunk_publications` row yet — search callers fall back to
/// `chunks.first_seen_commit` in that case (04 §4.1's "便宜列" — the single-
/// valued convenience column `chunk_publications` supersedes as the time-point
/// source of truth once populated).
pub fn chunk_publication_introductions(conn: &Connection, chunk_id: &str) -> Result<Vec<String>> {
    let mut stmt = conn.prepare(
        "SELECT introduction_commit FROM chunk_publications
         WHERE chunk_id = ?1 ORDER BY introduction_commit",
    )?;
    let rows = stmt.query_map(params![chunk_id], |row| row.get::<_, String>(0))?;
    rows.collect::<std::result::Result<Vec<_>, _>>()
        .map_err(IndexError::from)
}

pub fn ensure_schema_on_connection(conn: &Connection, config: FtsSchemaConfig) -> Result<()> {
    let fts_existed = table_exists(conn, "chunk_fts")?;
    let migrated_legacy_chunks = migrate_legacy_chunk_config_column(conn)?;
    conn.execute_batch(
        r#"
        CREATE TABLE IF NOT EXISTS chunks (
            -- QB29 (step4b-contract-tests-p3b.md §C, 04 §4.1 L385-386 /
            -- 03-data-model.md §8, U98): a rowid table's `TEXT PRIMARY KEY`
            -- does NOT imply NOT NULL by itself — spelled out explicitly.
            chunk_id TEXT NOT NULL PRIMARY KEY,
            raw_hash TEXT NOT NULL,
            tool_profile_hash TEXT NOT NULL,
            gen INTEGER NOT NULL,
            unit_key TEXT NOT NULL,
            raw_path TEXT NOT NULL,
            heading_path TEXT NOT NULL,
            section_id TEXT,
            byte_start INTEGER NOT NULL,
            byte_end INTEGER NOT NULL,
            text_hash TEXT NOT NULL,
            text TEXT NOT NULL,
            first_seen_commit TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_chunks_ident
            ON chunks(raw_hash, tool_profile_hash, gen);
        CREATE TABLE IF NOT EXISTS chunk_config_generations (
            association_rowid INTEGER PRIMARY KEY AUTOINCREMENT,
            chunk_id TEXT NOT NULL,
            chunking_config_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            introduction_commit TEXT,
            UNIQUE(chunk_id, chunking_config_hash)
        );
        CREATE TABLE IF NOT EXISTS chunk_publications (
            publication_rowid INTEGER PRIMARY KEY AUTOINCREMENT,
            chunk_id TEXT NOT NULL,
            introduction_commit TEXT NOT NULL,
            UNIQUE(chunk_id, introduction_commit)
        );
        CREATE INDEX IF NOT EXISTS idx_chunk_publications_chunk_id
            ON chunk_publications(chunk_id);
        CREATE TABLE IF NOT EXISTS embeddings (
            -- QB29: see the `chunks.chunk_id` comment above — same rowid-table
            -- TEXT PRIMARY KEY nullability gap, closed explicitly.
            id TEXT NOT NULL PRIMARY KEY,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            modality TEXT NOT NULL,
            vector BLOB NOT NULL,
            dimensions INTEGER NOT NULL,
            distance TEXT NOT NULL,
            profile_hash TEXT NOT NULL,
            -- 2026-07-24 (07 §5.3 contextual-embedding addendum): the humanized
            -- filename context a chunk vector was embedded with, so a rebuild
            -- can disambiguate several rows sharing one `target_id` (text_hash).
            -- NULL for non-contextual (legacy / symbolic-name) chunk embeddings.
            context_key TEXT
        );
        -- QB32 (step4b-contract-tests-p3b.md §C, 04 §4.3 L534-536): so the
        -- query_cache 256-row prune/enumerate (once wired, QB33/34) does not
        -- SCAN the full corpus-sized `embeddings` table to find its rows.
        CREATE INDEX IF NOT EXISTS idx_embeddings_type ON embeddings(target_type);
        CREATE TABLE IF NOT EXISTS tree_entries (
            commit_hash TEXT NOT NULL,
            path TEXT NOT NULL,
            raw_hash TEXT NOT NULL,
            tool_profile_hash TEXT,
            gen INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (commit_hash, path)
        );
        CREATE TABLE IF NOT EXISTS index_metadata (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            index_generation TEXT NOT NULL,
            last_lifecycle_epoch INTEGER NOT NULL DEFAULT 0
        );
        "#,
    )?;

    // 2026-07-24 (07 §5.3 contextual-embedding addendum): a pre-addendum store's
    // `embeddings` table predates `context_key`; `CREATE TABLE IF NOT EXISTS`
    // above leaves it untouched, so add the column in place. Idempotent (guarded
    // by the column probe); existing rows read back as NULL (non-contextual),
    // which the single-candidate rebuild path handles unchanged.
    if table_exists(conn, "embeddings")? && !table_has_column(conn, "embeddings", "context_key")? {
        conn.execute_batch("ALTER TABLE embeddings ADD COLUMN context_key TEXT;")?;
    }

    let tokenizer = match config.tokenizer {
        FtsTokenizer::Trigram => "trigram",
        FtsTokenizer::Unicode61RemoveDiacritics2 => "unicode61 remove_diacritics 2",
    };
    conn.execute_batch(&format!(
        r#"
        CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts
        USING fts5(text, heading_path, content='chunks', content_rowid='rowid', tokenize='{tokenizer}');

        CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
            INSERT INTO chunk_fts(rowid, text, heading_path)
            VALUES (new.rowid, new.text, new.heading_path);
        END;

        CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
            INSERT INTO chunk_fts(chunk_fts, rowid, text, heading_path)
            VALUES ('delete', old.rowid, old.text, old.heading_path);
        END;

        CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE OF text, heading_path ON chunks BEGIN
            INSERT INTO chunk_fts(chunk_fts, rowid, text, heading_path)
            VALUES ('delete', old.rowid, old.text, old.heading_path);
            INSERT INTO chunk_fts(rowid, text, heading_path)
            VALUES (new.rowid, new.text, new.heading_path);
        END;
        "#
    ))?;
    if migrated_legacy_chunks || !fts_existed {
        conn.execute("INSERT INTO chunk_fts(chunk_fts) VALUES('rebuild')", [])?;
    }

    // `chunk_vec` is a sqlite-vec `vec0` virtual table (04 §4.3): the KNN
    // acceleration layer derived from the `embeddings` table. Fixed at the adopted
    // profile's 768 dimensions / cosine distance (07 §5.3). Since our stored and
    // query vectors are L2-normalized, cosine distance ordering is exact.
    crate::vec::ensure_registered();
    conn.execute_batch(&format!(
        "CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vec USING vec0(
            chunk_id TEXT PRIMARY KEY,
            embedding float[{CHUNK_VEC_DIMENSIONS}] distance_metric=cosine
        );"
    ))?;
    // `image_vec` is `chunk_vec`'s counterpart for image objects (04 §4.3).
    // `embeddings.target_type` has admitted `'image'` since it was written, but
    // with no vec0 table to hold them there was no way to search one.
    //
    // Same width and metric on purpose: 03 §7 fixes ONE multimodal vector
    // space, so image and chunk vectors are directly comparable and the split
    // is only sqlite-vec's one-primary-key-type-per-table constraint, not a
    // semantic boundary. `image_id` is the `objects/image/` content hash.
    conn.execute_batch(&format!(
        "CREATE VIRTUAL TABLE IF NOT EXISTS image_vec USING vec0(
            image_id TEXT PRIMARY KEY,
            embedding float[{CHUNK_VEC_DIMENSIONS}] distance_metric=cosine
        );"
    ))?;
    Ok(())
}

/// `index_metadata`'s single row (04-pipeline.md §4.1 / Step4b LC42-45): the
/// search-cursor-generation ULID and the lifecycle-epoch value this row was
/// last synchronized against. `kio_core::purge` owns the counter files this
/// mirrors; this crate only stores the caller-supplied snapshot.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct IndexMetadata {
    pub index_generation: String,
    pub last_lifecycle_epoch: u64,
}

/// The one `index_metadata` row, or `None` on a store that predates this
/// table (LC42) — the table only ever holds zero or one row (`id=1`), never
/// a partial one. Tolerates the table itself being absent (an
/// un-schema'd connection, or a pre-Step4b `sqlite.db`) the same way as a
/// present-but-empty table, so callers do not each need their own
/// `table_exists` probe before this call.
pub fn read_index_metadata(conn: &Connection) -> Result<Option<IndexMetadata>> {
    if !table_exists(conn, "index_metadata")? {
        return Ok(None);
    }
    Ok(conn
        .query_row(
            "SELECT index_generation, last_lifecycle_epoch FROM index_metadata WHERE id = 1",
            [],
            |row| {
                let last_lifecycle_epoch: i64 = row.get(1)?;
                Ok(IndexMetadata {
                    index_generation: row.get(0)?,
                    last_lifecycle_epoch: u64::try_from(last_lifecycle_epoch).unwrap_or(0),
                })
            },
        )
        .optional()?)
}

/// LC42: create the single `index_metadata` row only if absent — never
/// overwrites an existing row (a fresh store's first write-command visit, or
/// a pre-Step4b store's first encounter with this table). `generation` is
/// the caller-minted ULID; `last_lifecycle_epoch` must be the *current*
/// `.kio/tombstones/lifecycle-epoch` counter value at the moment of this
/// call — never the column's own `DEFAULT 0`, which LC42 explicitly warns
/// would falsely read as a permanent rollback on every subsequent LC45
/// read-side check.
pub fn ensure_index_metadata(
    conn: &Connection,
    generation: &str,
    last_lifecycle_epoch: u64,
) -> Result<()> {
    conn.execute(
        "INSERT OR IGNORE INTO index_metadata (id, index_generation, last_lifecycle_epoch)
         VALUES (1, ?1, ?2)",
        params![
            generation,
            i64::try_from(last_lifecycle_epoch).unwrap_or(i64::MAX)
        ],
    )?;
    Ok(())
}

/// LC25/LC44: unconditionally replace `index_metadata`'s row — a fresh
/// `index_generation` ULID (retiring every outstanding search cursor, LC25)
/// paired with the lifecycle-epoch value this rotation is now synchronized
/// to (LC44's post-rollback-recovery write). Callers hold `.kio/.lock` (a
/// write command) when calling this; never called from a read-only path.
pub fn rotate_index_generation(
    conn: &Connection,
    generation: &str,
    last_lifecycle_epoch: u64,
) -> Result<()> {
    conn.execute(
        "INSERT INTO index_metadata (id, index_generation, last_lifecycle_epoch)
         VALUES (1, ?1, ?2)
         ON CONFLICT (id) DO UPDATE SET
             index_generation = excluded.index_generation,
             last_lifecycle_epoch = excluded.last_lifecycle_epoch",
        params![
            generation,
            i64::try_from(last_lifecycle_epoch).unwrap_or(i64::MAX)
        ],
    )?;
    Ok(())
}

fn migrate_legacy_chunk_config_column(conn: &Connection) -> Result<bool> {
    if !table_exists(conn, "chunks")? || !table_has_column(conn, "chunks", "chunking_config_hash")?
    {
        return Ok(false);
    }

    with_savepoint(conn, "kio_migrate_chunk_config", || {
        conn.execute_batch(
            r#"
            DROP TRIGGER IF EXISTS chunks_ai;
            DROP TRIGGER IF EXISTS chunks_ad;
            DROP TRIGGER IF EXISTS chunks_au;
            DROP TABLE IF EXISTS chunk_fts;

            ALTER TABLE chunks RENAME TO chunks_legacy_chunk_config;
            CREATE TABLE chunks (
                -- QB29: matches ensure_schema_on_connection's corrected DDL —
                -- a migrated table gets the same NOT NULL fix a fresh one does.
                chunk_id TEXT NOT NULL PRIMARY KEY,
                raw_hash TEXT NOT NULL,
                tool_profile_hash TEXT NOT NULL,
                gen INTEGER NOT NULL,
                unit_key TEXT NOT NULL,
                raw_path TEXT NOT NULL,
                heading_path TEXT NOT NULL,
                section_id TEXT,
                byte_start INTEGER NOT NULL,
                byte_end INTEGER NOT NULL,
                text_hash TEXT NOT NULL,
                text TEXT NOT NULL,
                first_seen_commit TEXT,
                created_at TEXT NOT NULL
            );
            INSERT INTO chunks(
                rowid, chunk_id, raw_hash, tool_profile_hash, gen, unit_key,
                raw_path, heading_path, section_id, byte_start, byte_end,
                text_hash, text, first_seen_commit, created_at
            )
            SELECT
                rowid, chunk_id, raw_hash, tool_profile_hash, gen, unit_key,
                raw_path, heading_path, section_id, byte_start, byte_end,
                text_hash, text, first_seen_commit, created_at
            FROM chunks_legacy_chunk_config
            ORDER BY rowid;

            CREATE TABLE IF NOT EXISTS chunk_config_generations (
                association_rowid INTEGER PRIMARY KEY AUTOINCREMENT,
                chunk_id TEXT NOT NULL,
                chunking_config_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(chunk_id, chunking_config_hash)
            );
            INSERT OR IGNORE INTO chunk_config_generations(
                chunk_id, chunking_config_hash, created_at
            )
            SELECT chunk_id, chunking_config_hash, created_at
            FROM chunks_legacy_chunk_config
            ORDER BY rowid;

            DROP TABLE chunks_legacy_chunk_config;
            "#,
        )?;
        Ok(())
    })?;
    Ok(true)
}

fn table_exists(conn: &Connection, table_name: &str) -> Result<bool> {
    Ok(conn
        .query_row(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?1 LIMIT 1",
            params![table_name],
            |_| Ok(()),
        )
        .optional()?
        .is_some())
}

fn table_has_column(conn: &Connection, table_name: &str, column_name: &str) -> Result<bool> {
    let quoted_table_name = format!("'{}'", table_name.replace('\'', "''"));
    let mut stmt = conn.prepare(&format!("PRAGMA table_info({quoted_table_name})"))?;
    let columns = stmt.query_map([], |row| row.get::<_, String>(1))?;
    for column in columns {
        if column? == column_name {
            return Ok(true);
        }
    }
    Ok(false)
}

fn with_savepoint<T>(
    conn: &Connection,
    name: &str,
    operation: impl FnOnce() -> Result<T>,
) -> Result<T> {
    conn.execute_batch(&format!("SAVEPOINT {name}"))?;
    match operation() {
        Ok(value) => {
            conn.execute_batch(&format!("RELEASE SAVEPOINT {name}"))?;
            Ok(value)
        }
        Err(error) => {
            let _ = conn.execute_batch(&format!(
                "ROLLBACK TO SAVEPOINT {name}; RELEASE SAVEPOINT {name}"
            ));
            Err(error)
        }
    }
}

fn sql_rowid(value: u64) -> Result<i64> {
    i64::try_from(value).map_err(|_| {
        IndexError::Contract(format!(
            "SQLite rowid must not exceed {} (received {value})",
            i64::MAX
        ))
    })
}

fn sql_u64_rowid(value: i64) -> Result<u64> {
    u64::try_from(value)
        .map_err(|_| IndexError::Schema(format!("SQLite returned a negative rowid: {value}")))
}

/// Adopted embedding dimensionality (07 §5.3 / 03 §7). `chunk_vec` is fixed to
/// this width; incompatible-width embeddings never reach vector search.
pub const CHUNK_VEC_DIMENSIONS: usize = 768;

#[cfg(test)]
mod tests {
    use super::*;

    fn row(chunk_id: &str, text: &str) -> ChunkRow {
        ChunkRow {
            chunk_id: chunk_id.to_owned(),
            raw_hash: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                .to_owned(),
            tool_profile_hash:
                "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb".to_owned(),
            gen: 0,
            unit_key: "doc:1".to_owned(),
            chunking_config_hash:
                "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc".to_owned(),
            raw_path: "a.md".to_owned(),
            heading_path: Some(vec!["認証仕様".to_owned()]),
            section_id: Some("認証仕様".to_owned()),
            byte_start: 0,
            byte_end: text.len() as u64,
            text_hash: "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
                .to_owned(),
            text: text.to_owned(),
            first_seen_commit: None,
            chunking_config_introduction_commit: None,
            created_at: "2026-07-03T00:00:00Z".to_owned(),
        }
    }

    fn basis_vector_bytes(axis: usize) -> Vec<u8> {
        let mut vector = vec![0.0_f32; CHUNK_VEC_DIMENSIONS];
        vector[axis] = 1.0;
        vector.into_iter().flat_map(f32::to_le_bytes).collect()
    }

    #[test]
    fn ct3_fts_001_external_content_triggers_sync_insert_delete() {
        let mut fts = SqliteFtsIndex::in_memory(FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        })
        .unwrap();
        fts.index_chunk(&row("c1", "認証仕様の更新")).unwrap();
        assert_eq!(fts.search("認証仕様", 10).unwrap()[0].chunk_id, "c1");
        fts.purge_raw(&row("c1", "認証仕様の更新").raw_hash, &BTreeSet::new())
            .unwrap();
        assert!(fts.search("認証仕様", 10).unwrap().is_empty());
    }

    /// PC37 (04 §4.1): `chunk_publications` accepts multiple distinct
    /// introduction commits per `chunk_id` (the multi-introduction case), is
    /// idempotent on a repeated `(chunk_id, introduction_commit)` pair, and
    /// reads back in byte order (PC32's deterministic tie-break input).
    #[test]
    fn pc37_chunk_publications_records_multiple_introductions_idempotently() {
        let mut fts = SqliteFtsIndex::in_memory(FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        })
        .unwrap();
        fts.index_chunk(&row("c1", "merge introduction test"))
            .unwrap();
        let conn = fts.connection();
        record_chunk_publication(conn, "c1", "sha256:cccccccc").unwrap();
        record_chunk_publication(conn, "c1", "sha256:aaaaaaaa").unwrap();
        // Re-publishing the same (chunk_id, introduction_commit) pair (a
        // resurrection or a repeated rebuild pass) does not duplicate the row.
        record_chunk_publication(conn, "c1", "sha256:aaaaaaaa").unwrap();

        let introductions = chunk_publication_introductions(conn, "c1").unwrap();
        assert_eq!(
            introductions,
            vec!["sha256:aaaaaaaa".to_owned(), "sha256:cccccccc".to_owned()]
        );
        assert!(chunk_publication_introductions(conn, "c-never-published")
            .unwrap()
            .is_empty());
    }

    #[test]
    fn purge_raw_is_atomic_and_preserves_shared_content_embeddings() {
        const RAW_TARGET: &str =
            "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
        const RAW_SURVIVOR: &str =
            "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
        const TEXT_SHARED: &str =
            "sha256:1111111111111111111111111111111111111111111111111111111111111111";
        const TEXT_UNIQUE: &str =
            "sha256:2222222222222222222222222222222222222222222222222222222222222222";

        let mut fts = SqliteFtsIndex::in_memory(FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        })
        .unwrap();
        let mut target_shared = row("c-target-shared", "shared searchable phrase");
        target_shared.raw_hash = RAW_TARGET.to_owned();
        target_shared.text_hash = TEXT_SHARED.to_owned();
        let mut survivor = row("c-survivor", "shared searchable phrase");
        survivor.raw_hash = RAW_SURVIVOR.to_owned();
        survivor.text_hash = TEXT_SHARED.to_owned();
        let mut target_unique = row("c-target-unique", "unique purge phrase");
        target_unique.raw_hash = RAW_TARGET.to_owned();
        target_unique.text_hash = TEXT_UNIQUE.to_owned();

        fts.index_chunk(&target_shared).unwrap();
        fts.index_chunk(&survivor).unwrap();
        fts.index_chunk(&target_unique).unwrap();
        crate::embedding_store::write_chunk_embedding(
            fts.connection(),
            "sha256:embedding-shared",
            TEXT_SHARED,
            &target_shared.chunk_id,
            &basis_vector_bytes(0),
            CHUNK_VEC_DIMENSIONS as u64,
            "cosine",
            "multimodal",
            "sha256:profile",
            None,
        )
        .unwrap();
        crate::embedding_store::write_chunk_embedding(
            fts.connection(),
            "sha256:embedding-shared",
            TEXT_SHARED,
            &survivor.chunk_id,
            &basis_vector_bytes(0),
            CHUNK_VEC_DIMENSIONS as u64,
            "cosine",
            "multimodal",
            "sha256:profile",
            None,
        )
        .unwrap();
        crate::embedding_store::write_chunk_embedding(
            fts.connection(),
            "sha256:embedding-unique",
            TEXT_UNIQUE,
            &target_unique.chunk_id,
            &basis_vector_bytes(1),
            CHUNK_VEC_DIMENSIONS as u64,
            "cosine",
            "multimodal",
            "sha256:profile",
            None,
        )
        .unwrap();

        let report = fts.purge_raw(RAW_TARGET, &BTreeSet::new()).unwrap();
        assert_eq!(
            report,
            PurgeRawIndexReport {
                chunk_ids: vec!["c-target-shared".to_owned(), "c-target-unique".to_owned()],
                deleted_chunks: 2,
                deleted_associations: 2,
                deleted_chunk_vectors: 2,
                deleted_image_vectors: 0,
                deleted_orphan_embeddings: 1,
                // The unique chunk's own embedding; the shared one survives
                // because another chunk still carries its `text_hash`.
                deleted_embedding_ids: vec!["sha256:embedding-unique".to_owned()],
            }
        );
        assert_eq!(
            fts.search("shared searchable", 10)
                .unwrap()
                .into_iter()
                .map(|hit| hit.chunk_id)
                .collect::<Vec<_>>(),
            vec!["c-survivor"]
        );
        assert!(fts.search("unique purge", 10).unwrap().is_empty());
        assert!(crate::embedding_store::read_chunk_vector(
            fts.connection(),
            &target_shared.chunk_id
        )
        .unwrap()
        .is_none());
        assert!(crate::embedding_store::read_chunk_vector(
            fts.connection(),
            &target_unique.chunk_id
        )
        .unwrap()
        .is_none());
        assert!(
            crate::embedding_store::read_chunk_vector(fts.connection(), &survivor.chunk_id)
                .unwrap()
                .is_some()
        );
        assert_eq!(
            fts.connection()
                .query_row(
                    "SELECT COUNT(*) FROM embeddings WHERE target_id = ?1",
                    params![TEXT_SHARED],
                    |row| row.get::<_, u64>(0)
                )
                .unwrap(),
            1
        );
        assert_eq!(
            fts.connection()
                .query_row(
                    "SELECT COUNT(*) FROM embeddings WHERE target_id = ?1",
                    params![TEXT_UNIQUE],
                    |row| row.get::<_, u64>(0)
                )
                .unwrap(),
            0
        );

        assert_eq!(
            fts.purge_raw(RAW_TARGET, &BTreeSet::new()).unwrap(),
            PurgeRawIndexReport::default(),
            "replay after a completed purge is idempotent"
        );
    }

    /// 05 §3.5: an image vector left behind is the purged figure still
    /// rankable by vector search. Which images are orphaned is the caller's
    /// judgement (the rule needs the Markdown image grammar); this pins that
    /// what it names is deleted, and that an image it does NOT name — one a
    /// surviving document still shows — is preserved.
    #[test]
    fn purge_raw_deletes_the_image_vectors_the_caller_named_and_no_others() {
        let mut fts = SqliteFtsIndex::in_memory(FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        })
        .unwrap();
        const ORPHANED: &str =
            "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
        const SHARED: &str =
            "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
        let target = row("c-target", "target body");
        fts.index_chunk(&target).unwrap();
        for (index, image_hash) in [ORPHANED, SHARED].iter().enumerate() {
            crate::embedding_store::write_image_embedding(
                fts.connection(),
                &format!("sha256:embedding-image-{index}"),
                image_hash,
                &basis_vector_bytes(index),
                CHUNK_VEC_DIMENSIONS as u64,
                "cosine",
                "multimodal",
                "sha256:profile",
            )
            .unwrap();
        }

        let orphaned = BTreeSet::from([ORPHANED.to_owned()]);
        let report = fts.purge_raw(&target.raw_hash, &orphaned).unwrap();
        assert_eq!(report.deleted_image_vectors, 1);
        assert!(report
            .deleted_embedding_ids
            .contains(&"sha256:embedding-image-0".to_owned()));

        assert!(
            crate::embedding_store::read_image_vector(fts.connection(), ORPHANED)
                .unwrap()
                .is_none(),
            "an image only the purged document referenced must lose its vector"
        );
        assert!(
            crate::embedding_store::read_image_vector(fts.connection(), SHARED)
                .unwrap()
                .is_some(),
            "an image a surviving document still shows has not stopped existing"
        );
    }

    #[test]
    fn purge_raw_rolls_back_all_index_layers_when_chunk_delete_fails() {
        let mut fts = SqliteFtsIndex::in_memory(FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        })
        .unwrap();
        let target = row("c-target", "rollback searchable phrase");
        fts.index_chunk(&target).unwrap();
        crate::embedding_store::write_chunk_embedding(
            fts.connection(),
            "sha256:embedding-rollback",
            &target.text_hash,
            &target.chunk_id,
            &basis_vector_bytes(0),
            CHUNK_VEC_DIMENSIONS as u64,
            "cosine",
            "multimodal",
            "sha256:profile",
            None,
        )
        .unwrap();
        fts.connection()
            .execute_batch(
                "CREATE TRIGGER reject_purge BEFORE DELETE ON chunks BEGIN
                     SELECT RAISE(ABORT, 'synthetic purge failure');
                 END;",
            )
            .unwrap();

        let error = fts
            .purge_raw(&target.raw_hash, &BTreeSet::new())
            .unwrap_err();
        assert!(error.to_string().contains("synthetic purge failure"));
        assert_eq!(fts.search("rollback searchable", 10).unwrap().len(), 1);
        assert!(
            crate::embedding_store::read_chunk_vector(fts.connection(), &target.chunk_id)
                .unwrap()
                .is_some()
        );
        assert_eq!(
            fts.connection()
                .query_row("SELECT COUNT(*) FROM chunk_config_generations", [], |row| {
                    row.get::<_, u64>(0)
                })
                .unwrap(),
            1,
            "config association deletion must roll back with the chunk"
        );
    }

    #[test]
    fn ct3_fts_002_first_seen_commit_update_does_not_rewrite_fts() {
        let mut fts = SqliteFtsIndex::in_memory(FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        })
        .unwrap();
        fts.index_chunk(&row("c1", "認証仕様の更新")).unwrap();
        fts.connection()
            .execute(
                "UPDATE chunks SET first_seen_commit = ?1 WHERE chunk_id = ?2",
                params!["sha256:commit", "c1"],
            )
            .unwrap();
        assert_eq!(fts.search("認証仕様", 10).unwrap()[0].chunk_id, "c1");
    }

    #[test]
    fn ct3_fts_003_trigram_matches_cjk_substrings_and_short_query_skips() {
        let mut fts = SqliteFtsIndex::in_memory(FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        })
        .unwrap();
        fts.index_chunk(&row("c1", "認証仕様の更新")).unwrap();
        assert_eq!(fts.search("認証仕様", 10).unwrap().len(), 1);
        assert!(fts.search("認", 10).unwrap().is_empty());
    }

    #[test]
    fn ct3_fts_004_schema_can_be_rebuilt_from_chunks() {
        let conn = Connection::open_in_memory().unwrap();
        ensure_schema_on_connection(
            &conn,
            FtsSchemaConfig {
                tokenizer: FtsTokenizer::Trigram,
            },
        )
        .unwrap();
    }

    #[test]
    fn ct4_chunk_config_schema_is_an_append_only_association() {
        let mut fts = SqliteFtsIndex::in_memory(FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        })
        .unwrap();
        let conn = fts.connection();
        assert!(!table_has_column(conn, "chunks", "chunking_config_hash").unwrap());
        assert!(table_has_column(conn, "chunk_config_generations", "association_rowid").unwrap());
        assert_eq!(max_chunk_config_association_rowid(conn).unwrap(), 0);

        let mut first = row("c1", "認証仕様の更新");
        first.first_seen_commit = Some("sha256:commit".to_owned());
        fts.index_chunk_with_association_rowid(&first, Some(17))
            .unwrap();
        // Replaying the same durable association is idempotent and does not burn
        // another AUTOINCREMENT value.
        fts.index_chunk_with_association_rowid(&first, Some(17))
            .unwrap();

        let mut next_generation = first.clone();
        next_generation.chunking_config_hash = "sha256:next-config".to_owned();
        fts.index_chunk(&next_generation).unwrap();

        let conn = fts.connection();
        assert_eq!(
            conn.query_row("SELECT COUNT(*) FROM chunks", [], |row| row
                .get::<_, u64>(0))
                .unwrap(),
            1,
            "one immutable chunk row is shared by both configs"
        );
        assert_eq!(
            conn.query_row("SELECT COUNT(*) FROM chunk_config_generations", [], |row| {
                row.get::<_, u64>(0)
            })
            .unwrap(),
            2
        );
        assert_eq!(max_chunk_config_association_rowid(conn).unwrap(), 18);
        assert!(
            chunk_has_current_config_association(conn, "c1", &first.chunking_config_hash, 17)
                .unwrap()
        );
        assert!(!chunk_has_current_config_association(
            conn,
            "c1",
            &next_generation.chunking_config_hash,
            17
        )
        .unwrap());
        assert_eq!(
            current_config_eligible_chunk_ids(conn, &next_generation.chunking_config_hash, 1, 17)
                .unwrap(),
            BTreeSet::new(),
            "a page-1 association maximum excludes a later generation"
        );
        assert_eq!(
            current_config_eligible_chunk_ids(conn, &next_generation.chunking_config_hash, 1, 18)
                .unwrap(),
            BTreeSet::from(["c1".to_owned()])
        );
    }

    #[test]
    fn ct4_explicit_association_rowid_conflicts_roll_back_the_chunk() {
        let mut fts = SqliteFtsIndex::in_memory(FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        })
        .unwrap();
        fts.index_chunk_with_association_rowid(&row("c1", "first chunk"), Some(9))
            .unwrap();

        let error = fts
            .index_chunk_with_association_rowid(&row("c2", "second chunk"), Some(9))
            .unwrap_err();
        assert!(error.to_string().contains("already occupied"));
        assert_eq!(
            fts.connection()
                .query_row(
                    "SELECT COUNT(*) FROM chunks WHERE chunk_id = 'c2'",
                    [],
                    |row| row.get::<_, u64>(0)
                )
                .unwrap(),
            0,
            "chunk and association publication are atomic"
        );

        let error = fts
            .index_chunk_with_association_rowid(&row("c1", "first chunk"), Some(10))
            .unwrap_err();
        assert!(error.to_string().contains("not requested rowid"));
        assert_eq!(
            max_chunk_config_association_rowid(fts.connection()).unwrap(),
            9
        );
    }

    #[test]
    fn ct4_durable_replay_preserves_chunk_and_association_rowids() {
        let mut fts = SqliteFtsIndex::in_memory(FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        })
        .unwrap();
        let first = row("c1", "first chunk");
        assert_eq!(
            fts.index_chunk_with_rowids(&first, Some(41), Some(101))
                .unwrap(),
            (41, 101)
        );

        let mut second_config = first.clone();
        second_config.chunking_config_hash = "sha256:next-config".to_owned();
        assert_eq!(
            fts.index_chunk_with_rowids(&second_config, Some(41), Some(205))
                .unwrap(),
            (41, 205)
        );
        assert_eq!(
            fts.connection()
                .query_row("SELECT COUNT(*) FROM chunks", [], |row| row
                    .get::<_, u64>(0))
                .unwrap(),
            1
        );

        let error = fts
            .index_chunk_with_rowids(&row("c2", "collision"), Some(41), Some(206))
            .unwrap_err();
        assert!(error.to_string().contains("already occupied"));
        assert_eq!(
            max_chunk_config_association_rowid(fts.connection()).unwrap(),
            205
        );
    }

    #[test]
    fn ct4_legacy_chunk_config_column_migrates_without_changing_chunk_rowids() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("sqlite.db");
        {
            let conn = Connection::open(&path).unwrap();
            conn.execute_batch(
                r#"
                CREATE TABLE chunks (
                    chunk_id TEXT PRIMARY KEY,
                    raw_hash TEXT NOT NULL,
                    tool_profile_hash TEXT NOT NULL,
                    gen INTEGER NOT NULL,
                    unit_key TEXT NOT NULL,
                    chunking_config_hash TEXT NOT NULL,
                    raw_path TEXT NOT NULL,
                    heading_path TEXT NOT NULL,
                    section_id TEXT,
                    byte_start INTEGER NOT NULL,
                    byte_end INTEGER NOT NULL,
                    text_hash TEXT NOT NULL,
                    text TEXT NOT NULL,
                    first_seen_commit TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE VIRTUAL TABLE chunk_fts
                USING fts5(
                    text,
                    heading_path,
                    content='chunks',
                    content_rowid='rowid',
                    tokenize='trigram'
                );
                CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
                    INSERT INTO chunk_fts(rowid, text, heading_path)
                    VALUES (new.rowid, new.text, new.heading_path);
                END;
                CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
                    INSERT INTO chunk_fts(chunk_fts, rowid, text, heading_path)
                    VALUES ('delete', old.rowid, old.text, old.heading_path);
                END;
                CREATE TRIGGER chunks_au AFTER UPDATE OF text, heading_path ON chunks BEGIN
                    INSERT INTO chunk_fts(chunk_fts, rowid, text, heading_path)
                    VALUES ('delete', old.rowid, old.text, old.heading_path);
                    INSERT INTO chunk_fts(rowid, text, heading_path)
                    VALUES (new.rowid, new.text, new.heading_path);
                END;
                INSERT INTO chunks(
                    rowid, chunk_id, raw_hash, tool_profile_hash, gen, unit_key,
                    chunking_config_hash, raw_path, heading_path, section_id,
                    byte_start, byte_end, text_hash, text, first_seen_commit, created_at
                ) VALUES
                    (7, 'c7', 'sha256:raw7', 'sha256:profile', 0, 'doc:7',
                     'sha256:cfg7', 'seven.md', '[]', NULL, 0, 16,
                     'sha256:text7', '認証仕様の更新', 'sha256:commit7', '2026-07-01T00:00:00Z'),
                    (42, 'c42', 'sha256:raw42', 'sha256:profile', 0, 'doc:42',
                     'sha256:cfg42', 'forty-two.md', '[]', NULL, 0, 18,
                     'sha256:text42', '検索インデックス', 'sha256:commit42', '2026-07-02T00:00:00Z');
                "#,
            )
            .unwrap();
        }

        let fts = SqliteFtsIndex::open(
            &path,
            FtsSchemaConfig {
                tokenizer: FtsTokenizer::Trigram,
            },
        )
        .unwrap();
        let conn = fts.connection();
        assert!(!table_has_column(conn, "chunks", "chunking_config_hash").unwrap());
        assert_eq!(
            conn.query_row(
                "SELECT rowid FROM chunks WHERE chunk_id = 'c7'",
                [],
                |row| { row.get::<_, u64>(0) }
            )
            .unwrap(),
            7
        );
        assert_eq!(
            conn.query_row(
                "SELECT rowid FROM chunks WHERE chunk_id = 'c42'",
                [],
                |row| row.get::<_, u64>(0)
            )
            .unwrap(),
            42
        );
        let associations = conn
            .prepare(
                "SELECT association_rowid, chunk_id, chunking_config_hash
                 FROM chunk_config_generations ORDER BY association_rowid",
            )
            .unwrap()
            .query_map([], |row| {
                Ok((
                    row.get::<_, u64>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                ))
            })
            .unwrap()
            .collect::<std::result::Result<Vec<_>, _>>()
            .unwrap();
        assert_eq!(
            associations,
            vec![
                (1, "c7".to_owned(), "sha256:cfg7".to_owned()),
                (2, "c42".to_owned(), "sha256:cfg42".to_owned())
            ]
        );
        assert_eq!(fts.search("認証仕様", 10).unwrap()[0].chunk_id, "c7");
    }

    #[test]
    fn q4_nul_bytes_are_stripped_from_the_fts_index() {
        let mut fts = SqliteFtsIndex::in_memory(FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        })
        .unwrap();
        // A UTF-16-LE ".txt" decoded lossily keeps a NUL after every ASCII char.
        // The trigram tokenizer stops at the first NUL, so before the fix every
        // word after the leading `d` ("distinctword") was silently unsearchable
        // even though `index` reported success.
        let nul_text = "d\u{0}i\u{0}s\u{0}t\u{0}i\u{0}n\u{0}c\u{0}t\u{0}w\u{0}o\u{0}r\u{0}d\u{0}";
        fts.index_chunk(&row("c1", nul_text)).unwrap();
        let hits = fts.search("distinct", 10).unwrap();
        assert_eq!(hits.len(), 1, "NUL-suffixed word must be searchable");
        assert_eq!(hits[0].chunk_id, "c1");
    }

    #[test]
    fn f2_nfd_content_is_searchable_by_nfc_query() {
        let mut fts = SqliteFtsIndex::in_memory(FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        })
        .unwrap();
        // Body carries the DECOMPOSED (NFD) form: "cafe" + U+0301 COMBINING ACUTE.
        // The index projection normalizes it to NFC, so the trigram tokenizer sees
        // the same bytes a composed query produces.
        let nfd_body = "cafe\u{301} latte menu";
        assert!(nfd_body.contains('\u{301}'), "test body must be NFD");
        fts.index_chunk(&row("c1", nfd_body)).unwrap();
        // Composed (NFC) query "café" must hit the NFD-stored content.
        let hits = fts.search("caf\u{e9}", 10).unwrap();
        assert_eq!(hits.len(), 1, "NFC query must match NFD-stored content");
        assert_eq!(hits[0].chunk_id, "c1");
    }
}
