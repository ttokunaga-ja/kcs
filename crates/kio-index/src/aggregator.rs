//! Device-level read replica of every scope's live chunks (`aggregator.sqlite`).
//!
//! Cross-scope search used to be scatter-gather: query each `.kio` on its own
//! index, then merge the per-scope results. That model cannot score text.
//! BM25 is defined against a collection — its IDF reads that collection's `N`
//! and per-term document frequency, its length normalization reads that
//! collection's `avgdl` — so splitting one corpus into per-folder FTS tables
//! makes every folder its own collection, and a chunk's rank means "best in
//! this folder", not "best in the corpus". Measured on the dogfood corpus (428
//! scopes, 3851 chunks, median 6 chunks per scope): a term appearing in exactly
//! one chunk earns IDF 0.69 in the smallest scope against 7.85 globally, and
//! the global-vs-per-scope IDF ratio runs to 24.8x. Summing such a rank with a
//! globally-ranked vector term adds two numbers that are not on the same scale.
//!
//! Replication removes the premise instead of correcting the symptom: one
//! collection, one BM25, no normalization function and no tuned constant. This
//! is the answer distributed IR has given since `dfs_query_then_fetch`.
//!
//! # Every scope shares one schema, so every scope shares one table
//!
//! `agg_chunks` is the per-scope `chunks` table's searchable columns plus a
//! `scope_id`, and `agg_fts` is one FTS5 over all of it. Nothing here is
//! per-scope except that column.
//!
//! # What this replica holds — resolved sets, not raw tables
//!
//! It deliberately does NOT copy `chunk_config_generations` / `tree_entries` /
//! `first_seen_commit` / `kio_eligible_identity` and re-derive eligibility here.
//! That would put liveness logic in two places, and the two would drift. Instead
//! each refresh asks the scope's own code which chunks are live and stores that
//! ANSWER (03 §4 invariant 7). This file therefore contains no liveness rule.
//!
//! Which is a rule about WHERE the answer comes from, not permission to skip
//! the question: the first implementation projected every row with
//! `first_seen_commit IS NOT NULL` — every chunk ever committed, deleted files
//! and superseded chunking generations included. Those rows are unreturnable by
//! any search and still counted toward `N` and document frequency, distorting
//! every surviving chunk's IDF, and still took slots in the depth cut. The
//! caller now asks the per-scope planner (R25-9).
//!
//! It also holds only what a rank needs today — text, heading, vector. Chunk
//! metadata (raw_hash, byte span, …) and scope metadata beyond the generation
//! stamp belong to the stage where the replica also SELECTS candidates and
//! re-verifies the scopes it answered from; storing them before there is a
//! reader would be 3851 rows of data no code consults (05 §1.8, "候補選択の所在").
//!
//! # What it is not allowed to decide
//!
//! It is a CACHE, never truth (03 §4). Deleting it costs a re-projection and
//! nothing else, which is why it lives under the cache root.

use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

use rusqlite::{params, Connection, OptionalExtension};
use sha2::{Digest, Sha256};

use crate::embedding_store::{f32_from_le_bytes, f32_to_le_bytes};
use crate::Result;

/// One live chunk as the collection sees it: what BM25 scores, what cosine
/// ranks, and the key both are reported under.
#[derive(Debug, Clone, PartialEq)]
pub struct AggChunk {
    /// The scope's `chunks.chunk_id`. Paired with `scope_id` it addresses the
    /// row the way the cross-scope merge addresses a candidate.
    pub chunk_id: String,
    pub text: String,
    pub heading_path: Option<String>,
    /// `None` when this chunk has no vector (scope not enriched, or the vector
    /// lane never reached it). Such a chunk still belongs to the text
    /// collection and must keep counting toward `N` and `avgdl`.
    pub embedding: Option<Vec<f32>>,
}

/// BM25 against the WHOLE corpus. Lower is better — SQLite's `bm25()` sign
/// convention, kept rather than negated so a value can be compared against a
/// per-scope score during debugging without a mental flip.
#[derive(Debug, Clone, PartialEq)]
pub struct TextScore {
    pub scope_id: String,
    pub chunk_id: String,
    pub bm25: f64,
}

/// Cosine against the query over the whole corpus. Higher is better.
#[derive(Debug, Clone, PartialEq)]
pub struct VectorScore {
    pub scope_id: String,
    pub chunk_id: String,
    pub cosine: f64,
}

/// One scope's incremental change, as the writer that made it already knows it.
///
/// The embedding lane is the one writer that reaches the replica without
/// rebuilding the whole index, and it knows exactly which chunks it touched, so
/// it sends that instead of a re-projection — no diff, no read-back.
///
/// There is deliberately no `inserted` variant: a new chunk only ever enters
/// the index through a full rebuild into a fresh temp db, and that path
/// replaces the scope's whole projection (`refresh_scope`). A delta that could
/// also insert text would be a second, unexercised way to populate a scope.
#[derive(Debug, Default, Clone, PartialEq)]
pub struct ScopeDelta {
    /// `(chunk_id, vector)` for the chunks that just gained a vector — the ids
    /// `link_chunk_vecs_to_content_vector` reported as linked, never the ids
    /// the caller offered it (a secrets hold or a width mismatch drops members
    /// there, and the replica must not resurrect them).
    pub vectors_added: Vec<(String, Vec<f32>)>,
}

// R25-7: there is deliberately no `removed` variant either. It existed, with a
// doc comment naming purge as its writer, and purge never used it — purge takes
// a full re-projection because it deletes chunks, config associations, chunk
// vectors AND orphaned embeddings, and being exactly right about the surviving
// set matters more there than the milliseconds a delta would save (05 §3.5). A
// field whose stated writer does not write it is a standing invitation to read
// the code as if some path were unhandled.

impl ScopeDelta {
    #[must_use]
    pub fn is_empty(&self) -> bool {
        self.vectors_added.is_empty()
    }
}

pub struct Aggregator {
    conn: Connection,
}

impl Aggregator {
    /// Open (creating if absent) the replica.
    ///
    /// The FTS tokenizer and the `bm25()` column weights MUST match the
    /// per-scope FTS (`fts::ensure_schema`, `execute_fts_tier`): the same MATCH
    /// expression runs against both — the replica when it answers, the scope
    /// when the scatter-gather fallback does — and a rank computed under
    /// different tokenization would be ranking a different query.
    pub fn open(path: &Path) -> Result<Self> {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).map_err(|error| {
                crate::IndexError::Schema(format!("aggregator cache dir: {error}"))
            })?;
        }
        let conn = Connection::open(path)?;
        conn.pragma_update(None, "journal_mode", "WAL")?;
        conn.busy_timeout(std::time::Duration::from_secs(10))?;
        conn.execute_batch(
            r#"
            CREATE TABLE IF NOT EXISTS agg_scopes (
                scope_id         TEXT PRIMARY KEY,
                -- The scope's `index_metadata.index_generation` when its rows
                -- were written. Any index change rotates it, so an inequality
                -- is the whole staleness test.
                index_generation TEXT NOT NULL,
                refreshed_at     INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS agg_chunks (
                rowid        INTEGER PRIMARY KEY,
                scope_id     TEXT NOT NULL,
                chunk_id     TEXT NOT NULL,
                text         TEXT NOT NULL,
                heading_path TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS agg_chunks_key
                ON agg_chunks(scope_id, chunk_id);
            CREATE INDEX IF NOT EXISTS agg_chunks_scope ON agg_chunks(scope_id);
            CREATE VIRTUAL TABLE IF NOT EXISTS agg_fts USING fts5(
                text, heading_path,
                content='agg_chunks', content_rowid='rowid',
                tokenize='trigram'
            );
            CREATE TABLE IF NOT EXISTS agg_embeddings (
                chunk_rowid INTEGER PRIMARY KEY,
                scope_id    TEXT NOT NULL,
                vector      BLOB NOT NULL,
                dimensions  INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS agg_embeddings_scope
                ON agg_embeddings(scope_id);
            "#,
        )?;
        Ok(Self { conn })
    }

    /// One stamp for the whole collection: every scope this replica holds,
    /// paired with the generation it holds for that scope.
    ///
    /// BM25 is the reason this exists. `bm25()` reads `agg_fts`'s document
    /// frequency, `N` and `avgdl` — statistics of the ENTIRE index, which no
    /// per-scope filter can narrow (FTS5 computes them before any `WHERE` on a
    /// joined column runs). So a searched scope's ranks move when a scope
    /// nobody searched is indexed, and the per-scope `index_generation` a
    /// cursor freezes cannot see that: every searched scope is unchanged and
    /// the cursor still validates. Freezing this stamp alongside them makes
    /// "the collection that produced page 1" a thing a later page can check
    /// (05 §1.8 "replica 世代が cursor と一致する page N").
    ///
    /// It is a hash rather than a counter because the replica has no writer
    /// that could own a monotonic one: three commands and two lanes write it,
    /// and a stamp that any of them could forget to bump is a stale-read bug
    /// waiting for the path that forgets.
    pub fn collection_generation(&self) -> Result<String> {
        let mut stmt = self
            .conn
            .prepare("SELECT scope_id, index_generation FROM agg_scopes ORDER BY scope_id")?;
        let rows = stmt.query_map([], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
        })?;
        let mut hasher = Sha256::new();
        for row in rows {
            let (scope_id, generation) = row?;
            hasher.update(scope_id.as_bytes());
            hasher.update(b"\t");
            hasher.update(generation.as_bytes());
            hasher.update(b"\n");
        }
        Ok(format!("sha256:{}", lower_hex(&hasher.finalize())))
    }

    /// The generation this replica holds for `scope_id`, or `None` if it holds
    /// nothing for it. Equality against the scope's live generation is the
    /// entire refresh decision.
    pub fn scope_generation(&self, scope_id: &str) -> Result<Option<String>> {
        Ok(self
            .conn
            .query_row(
                "SELECT index_generation FROM agg_scopes WHERE scope_id = ?1",
                params![scope_id],
                |row| row.get::<_, String>(0),
            )
            .optional()?)
    }

    /// Replace everything this replica holds for one scope, in one transaction.
    ///
    /// Whole-scope replace rather than a row-level delta. `index_generation` is
    /// a ULID that rotates on ANY index change — it says THAT the scope moved,
    /// never WHAT moved — so a delta would have to diff the scope's chunk id set
    /// against the replica's. That diff is cheap (ids only), but the projection
    /// is only reached at all when a scope actually moved, and a scope holds 6
    /// chunks at the median and 49 at the maximum on the dogfood corpus (the
    /// scope model is non-recursive, 03 §3), so a re-projection writes tens of
    /// rows and measures 5.4 ms.
    ///
    /// Delete-then-insert rather than upsert: a refresh must drop chunks the
    /// scope no longer has, or their terms keep inflating the corpus document
    /// frequency forever — which silently lowers every other chunk's IDF for
    /// those terms.
    pub fn refresh_scope(
        &mut self,
        scope_id: &str,
        index_generation: &str,
        chunks: &[AggChunk],
        now_ms: i64,
    ) -> Result<()> {
        let tx = self.conn.transaction()?;
        delete_scope_rows(&tx, scope_id)?;
        {
            let mut ins = tx.prepare(
                "INSERT INTO agg_chunks(scope_id, chunk_id, text, heading_path)
                 VALUES (?1, ?2, ?3, ?4)",
            )?;
            let mut fts =
                tx.prepare("INSERT INTO agg_fts(rowid, text, heading_path) VALUES (?1, ?2, ?3)")?;
            let mut vecs = tx.prepare(
                "INSERT INTO agg_embeddings(chunk_rowid, scope_id, vector, dimensions)
                 VALUES (?1, ?2, ?3, ?4)",
            )?;
            for chunk in chunks {
                ins.execute(params![
                    scope_id,
                    chunk.chunk_id,
                    chunk.text,
                    chunk.heading_path
                ])?;
                let rowid = tx.last_insert_rowid();
                fts.execute(params![rowid, chunk.text, chunk.heading_path])?;
                if let Some(vector) = chunk.embedding.as_deref() {
                    vecs.execute(params![
                        rowid,
                        scope_id,
                        f32_to_le_bytes(vector),
                        vector.len() as i64
                    ])?;
                }
            }
        }
        // Written LAST, deliberately: the generation stamp is this projection's
        // commit marker. Anything that fails before it leaves the stamp stale,
        // and the next search re-projects the scope. That is what lets the
        // replica be correct without a cross-database atomic commit.
        tx.execute(
            "INSERT INTO agg_scopes(scope_id, index_generation, refreshed_at)
             VALUES (?1, ?2, ?3)
             ON CONFLICT(scope_id) DO UPDATE SET
                 index_generation = excluded.index_generation,
                 refreshed_at = excluded.refreshed_at",
            params![scope_id, index_generation, now_ms],
        )?;
        tx.commit()?;
        Ok(())
    }

    /// Apply a change the writer already knows about, then re-stamp the scope.
    ///
    /// Returns `false` — writing nothing at all — unless the replica holds
    /// EXACTLY `expected_generation` for this scope. A delta carries only what
    /// changed, so it can correct a replica that is level with the pre-change
    /// index and nothing else. Two states fail that test:
    ///
    /// - The replica has never projected this scope. Stamping a generation over
    ///   text that was never replicated would tell the next search this scope is
    ///   current and make it skip the projection it needs.
    /// - The replica holds SOME generation, but not the one this change was
    ///   computed against. This is the state R25-3 found, and the first guard
    ///   alone let it through: a failed write-through leaves the replica a
    ///   generation behind with chunk `b` missing, the embedding lane then
    ///   applies a delta carrying `b`'s vector, `b` is skipped for not being
    ///   there — and the scope is stamped current anyway, so `b` is gone from
    ///   the corpus for good. Refusing costs one projection; accepting costs
    ///   the chunk.
    ///
    /// Callers hold `.kio/.lock`, so the generation they read from the live
    /// index cannot have been rotated out from under them between that read
    /// and this write.
    pub fn apply_delta(
        &mut self,
        scope_id: &str,
        expected_generation: &str,
        index_generation: &str,
        delta: &ScopeDelta,
        now_ms: i64,
    ) -> Result<bool> {
        if self.scope_generation(scope_id)?.as_deref() != Some(expected_generation) {
            return Ok(false);
        }
        let tx = self.conn.transaction()?;
        {
            let mut rowid_of =
                tx.prepare("SELECT rowid FROM agg_chunks WHERE scope_id = ?1 AND chunk_id = ?2")?;
            let mut vecs = tx.prepare(
                "INSERT INTO agg_embeddings(chunk_rowid, scope_id, vector, dimensions)
                 VALUES (?1, ?2, ?3, ?4)
                 ON CONFLICT(chunk_rowid) DO UPDATE SET
                     vector = excluded.vector,
                     dimensions = excluded.dimensions",
            )?;
            for (chunk_id, vector) in &delta.vectors_added {
                // A chunk the replica does not hold is not an error. The scope
                // was projected before this chunk existed, so the projection
                // that first picks the chunk up carries its vector along with
                // it; inserting an orphan vector row here would only leave a
                // row no join can reach.
                let Some(rowid) = rowid_of
                    .query_row(params![scope_id, chunk_id], |row| row.get::<_, i64>(0))
                    .optional()?
                else {
                    continue;
                };
                vecs.execute(params![
                    rowid,
                    scope_id,
                    f32_to_le_bytes(vector),
                    vector.len() as i64
                ])?;
            }
        }
        // Stamped LAST, for the reason spelled out on `refresh_scope`.
        tx.execute(
            "UPDATE agg_scopes SET index_generation = ?2, refreshed_at = ?3
             WHERE scope_id = ?1",
            params![scope_id, index_generation, now_ms],
        )?;
        tx.commit()?;
        Ok(true)
    }

    /// Forget every scope not in `live`, returning how many were dropped. A
    /// scope that vanished from the registry must stop skewing corpus
    /// statistics on the very next search, not at some later rebuild.
    ///
    /// Only an all-scopes search may call this: under a narrowed search the
    /// live set is a deliberate SUBSET of the device, and pruning to it would
    /// evict every scope the user did not ask about (05 §1.8).
    pub fn retain_scopes(&mut self, live: &BTreeSet<String>) -> Result<usize> {
        let doomed: Vec<String> = self
            .scope_ids()?
            .into_iter()
            .filter(|scope_id| !live.contains(scope_id))
            .collect();
        for scope_id in &doomed {
            let tx = self.conn.transaction()?;
            delete_scope_rows(&tx, scope_id)?;
            tx.execute(
                "DELETE FROM agg_scopes WHERE scope_id = ?1",
                params![scope_id],
            )?;
            tx.commit()?;
        }
        Ok(doomed.len())
    }

    /// Every scope this replica holds — the `scopes` argument for a caller that
    /// means "the whole collection".
    pub fn scope_ids(&self) -> Result<BTreeSet<String>> {
        let mut stmt = self.conn.prepare("SELECT scope_id FROM agg_scopes")?;
        let rows = stmt.query_map([], |row| row.get::<_, String>(0))?;
        let mut out = BTreeSet::new();
        for row in rows {
            out.insert(row?);
        }
        Ok(out)
    }

    /// Score `match_expr` over the collection, returning the best `limit` rows
    /// **from `scopes`**.
    ///
    /// Column weights match `execute_fts_tier`'s `bm25(chunk_fts, 1.0, 0.3)`,
    /// so the only difference from a per-scope score is the collection it is
    /// computed over — which is the entire point.
    ///
    /// `scopes` restricts the ROWS, never the STATISTICS. Both halves matter:
    ///
    /// - Restricting the rows is what makes a narrowed search (`--scope` /
    ///   `--descendants`) rankable at all. Without it the `limit` cut is taken
    ///   over the whole device, so a subtree that ranks below it device-wide
    ///   gets back no rows, every candidate loses its text term, and the merge
    ///   falls through to its `(scope_id, chunk_hash)` tie-break — results
    ///   ordered by hash. Measured on the dogfood corpus: for `the `, 263
    ///   scopes hold a matching chunk and the device-wide top 200 reaches 76 of
    ///   them, leaving 187 scopes whose narrowed search returned nothing but
    ///   zeroes.
    /// - NOT restricting the statistics is what keeps the ranks on one scale.
    ///   `bm25()` reads `agg_fts`'s df/`N`/`avgdl` for the whole index and no
    ///   `WHERE` on a joined column can narrow them, so every caller — narrowed
    ///   or not — gets ranks from the same collection. Recomputing per-subset
    ///   statistics would rebuild the per-corpus problem this replica exists to
    ///   remove.
    pub fn text_scores(
        &self,
        match_expr: &str,
        scopes: &BTreeSet<String>,
        limit: u64,
    ) -> Result<Vec<TextScore>> {
        self.load_query_scopes(scopes)?;
        let mut stmt = self.conn.prepare(
            "SELECT c.scope_id, c.chunk_id, bm25(agg_fts, 1.0, 0.3) AS score
             FROM agg_fts
             JOIN agg_chunks c ON c.rowid = agg_fts.rowid
             JOIN query_scopes q ON q.scope_id = c.scope_id
             WHERE agg_fts MATCH ?1
             ORDER BY score, c.scope_id, c.chunk_id
             LIMIT ?2",
        )?;
        let rows = stmt.query_map(params![match_expr, limit as i64], |row| {
            Ok(TextScore {
                scope_id: row.get(0)?,
                chunk_id: row.get(1)?,
                bm25: row.get(2)?,
            })
        })?;
        let mut out = Vec::new();
        for row in rows {
            out.push(row?);
        }
        Ok(out)
    }

    /// Cosine-rank `scopes`' chunks against `query`.
    ///
    /// A full scan, deliberately: the replica holds one f32 blob per live
    /// chunk (3851 x 768 = 11.8 MB on the dogfood corpus), and an exact scan
    /// keeps the ordering identical to what the per-scope fallback computes.
    /// Rows whose dimensionality differs from the query are skipped rather than
    /// scored — a profile mismatch must not silently produce a garbage cosine.
    ///
    /// Cosine is self-contained per pair, so unlike BM25 there is no
    /// collection statistic to preserve: restricting to `scopes` is purely a
    /// restriction, and the ranks of what remains are unchanged. It is still
    /// required — the `limit` cut is otherwise taken device-wide and a narrowed
    /// search's candidates fall out of it exactly as they do on the text lane.
    pub fn vector_scores(
        &self,
        query: &[f32],
        scopes: &BTreeSet<String>,
        limit: u64,
    ) -> Result<Vec<VectorScore>> {
        self.load_query_scopes(scopes)?;
        let mut stmt = self.conn.prepare(
            "SELECT c.scope_id, c.chunk_id, e.vector, e.dimensions
             FROM agg_embeddings e
             JOIN agg_chunks c ON c.rowid = e.chunk_rowid
             JOIN query_scopes q ON q.scope_id = c.scope_id",
        )?;
        let rows = stmt.query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, Vec<u8>>(2)?,
                row.get::<_, i64>(3)?,
            ))
        })?;
        let mut scored = Vec::new();
        for row in rows {
            let (scope_id, chunk_id, blob, dimensions) = row?;
            if dimensions as usize != query.len() {
                continue;
            }
            let vector = f32_from_le_bytes(&blob);
            if vector.len() != query.len() {
                continue;
            }
            let cosine = cosine_similarity(query, &vector);
            if cosine.is_finite() {
                scored.push(VectorScore {
                    scope_id,
                    chunk_id,
                    cosine,
                });
            }
        }
        // Descending cosine, then the merge's own deterministic tie-break, so
        // the rank a candidate gets does not depend on scan order.
        scored.sort_by(|a, b| {
            b.cosine
                .total_cmp(&a.cosine)
                .then_with(|| a.scope_id.cmp(&b.scope_id))
                .then_with(|| a.chunk_id.cmp(&b.chunk_id))
        });
        scored.truncate(limit as usize);
        Ok(scored)
    }

    /// Stage the scope set both scoring lanes join against.
    ///
    /// A temp table rather than an `IN (?,?,…)` list because the bind count
    /// would otherwise be the device's scope count: 428 on the dogfood corpus,
    /// already within sight of SQLite's 999-parameter default, and an
    /// all-scopes search is the common case rather than the rare one. A
    /// primary-keyed temp table has no such ceiling and gives the join an index.
    fn load_query_scopes(&self, scopes: &BTreeSet<String>) -> Result<()> {
        self.conn.execute_batch(
            "CREATE TEMP TABLE IF NOT EXISTS query_scopes (scope_id TEXT PRIMARY KEY);
             DELETE FROM query_scopes;",
        )?;
        let mut insert = self
            .conn
            .prepare("INSERT INTO query_scopes(scope_id) VALUES (?1)")?;
        for scope_id in scopes {
            insert.execute(params![scope_id])?;
        }
        Ok(())
    }

    /// `(scopes, chunks, vectors)` — for diagnostics and for a caller's own
    /// "is this replica populated enough to answer" check.
    pub fn corpus_size(&self) -> Result<(u64, u64, u64)> {
        let scopes: i64 = self
            .conn
            .query_row("SELECT COUNT(*) FROM agg_scopes", [], |row| row.get(0))?;
        let chunks: i64 = self
            .conn
            .query_row("SELECT COUNT(*) FROM agg_chunks", [], |row| row.get(0))?;
        let vectors: i64 =
            self.conn
                .query_row("SELECT COUNT(*) FROM agg_embeddings", [], |row| row.get(0))?;
        Ok((scopes as u64, chunks as u64, vectors as u64))
    }
}

/// Drop every row of one scope (the scope itself is leaving).
fn delete_scope_rows(tx: &rusqlite::Transaction<'_>, scope_id: &str) -> Result<()> {
    let doomed = stored_rows(
        tx,
        "SELECT rowid, text, heading_path FROM agg_chunks WHERE scope_id = ?1",
        params![scope_id],
    )?;
    unindex(tx, &doomed)?;
    tx.execute(
        "DELETE FROM agg_embeddings WHERE scope_id = ?1",
        params![scope_id],
    )?;
    tx.execute(
        "DELETE FROM agg_chunks WHERE scope_id = ?1",
        params![scope_id],
    )?;
    Ok(())
}

type StoredRow = (i64, String, Option<String>);

fn stored_rows(
    tx: &rusqlite::Transaction<'_>,
    sql: &str,
    bound: impl rusqlite::Params,
) -> Result<Vec<StoredRow>> {
    let mut stmt = tx.prepare(sql)?;
    let rows = stmt
        .query_map(bound, |row| {
            Ok((
                row.get::<_, i64>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, Option<String>>(2)?,
            ))
        })?
        .collect::<std::result::Result<Vec<_>, _>>()?;
    Ok(rows)
}

/// The FTS is external-content with no triggers here, so its rows are
/// maintained explicitly — a plain DELETE on the content table would leave the
/// index holding terms for rows that no longer exist, and those terms keep
/// counting toward every other chunk's IDF.
fn unindex(tx: &rusqlite::Transaction<'_>, rows: &[StoredRow]) -> Result<()> {
    let mut del = tx.prepare(
        "INSERT INTO agg_fts(agg_fts, rowid, text, heading_path) VALUES ('delete', ?1, ?2, ?3)",
    )?;
    for (rowid, text, heading) in rows {
        del.execute(params![rowid, text, heading])?;
    }
    Ok(())
}

/// Exact cosine of two equal-length vectors (f64 accumulation). Stored and
/// query embeddings are L2-normalized (07 §5.3), so this equals their dot
/// product in the ideal case; dividing by the norms keeps it exact under any
/// residual denormalization. `NEG_INFINITY` for a zero-norm vector, which the
/// caller drops rather than ranks.
fn lower_hex(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        out.push(HEX[(byte >> 4) as usize] as char);
        out.push(HEX[(byte & 0x0f) as usize] as char);
    }
    out
}

fn cosine_similarity(a: &[f32], b: &[f32]) -> f64 {
    let mut dot = 0f64;
    let mut norm_a = 0f64;
    let mut norm_b = 0f64;
    for (x, y) in a.iter().zip(b.iter()) {
        let x = f64::from(*x);
        let y = f64::from(*y);
        dot += x * y;
        norm_a += x * x;
        norm_b += y * y;
    }
    if norm_a <= 0.0 || norm_b <= 0.0 {
        return f64::NEG_INFINITY;
    }
    dot / (norm_a.sqrt() * norm_b.sqrt())
}

/// Dense 1-based ranks over the whole corpus, keyed `(scope_id, chunk_id)`.
///
/// A candidate the replica does not know about gets NO rank: callers must treat
/// that as "no term on this lane", never as rank 1, or a miss would promote a
/// chunk instead of merely failing to help it.
#[must_use]
pub fn text_ranks(scores: &[TextScore]) -> BTreeMap<(String, String), u64> {
    let mut ordered = scores.to_vec();
    ordered.sort_by(|a, b| {
        a.bm25
            .total_cmp(&b.bm25)
            .then_with(|| a.scope_id.cmp(&b.scope_id))
            .then_with(|| a.chunk_id.cmp(&b.chunk_id))
    });
    ordered
        .into_iter()
        .enumerate()
        .map(|(index, score)| ((score.scope_id, score.chunk_id), index as u64 + 1))
        .collect()
}

/// Dense 1-based ranks by descending cosine. `vector_scores` already returns
/// this order; re-sorting here keeps the function total for callers that
/// filtered or concatenated.
#[must_use]
pub fn vector_ranks(scores: &[VectorScore]) -> BTreeMap<(String, String), u64> {
    let mut ordered = scores.to_vec();
    ordered.sort_by(|a, b| {
        b.cosine
            .total_cmp(&a.cosine)
            .then_with(|| a.scope_id.cmp(&b.scope_id))
            .then_with(|| a.chunk_id.cmp(&b.chunk_id))
    });
    ordered
        .into_iter()
        .enumerate()
        .map(|(index, score)| ((score.scope_id, score.chunk_id), index as u64 + 1))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn chunk(id: &str, text: &str) -> AggChunk {
        AggChunk {
            chunk_id: id.to_owned(),
            text: text.to_owned(),
            heading_path: None,
            embedding: None,
        }
    }

    fn vectored(id: &str, text: &str, embedding: Vec<f32>) -> AggChunk {
        AggChunk {
            embedding: Some(embedding),
            ..chunk(id, text)
        }
    }

    /// The scope set a scoring call restricts to.
    fn only(scope_ids: &[&str]) -> BTreeSet<String> {
        scope_ids.iter().map(|id| (*id).to_owned()).collect()
    }

    fn store() -> (tempfile::TempDir, Aggregator) {
        let dir = tempfile::tempdir().unwrap();
        let index = Aggregator::open(&dir.path().join("aggregator.sqlite")).unwrap();
        (dir, index)
    }

    #[test]
    fn one_collection_scores_the_same_text_the_same_way_in_every_scope() {
        // The defect replication exists to remove: identical content in a
        // 1-chunk scope and a 41-chunk scope must not score differently just
        // because their folders differ in size.
        let (_dir, mut index) = store();
        index
            .refresh_scope("tiny", "gen1", &[chunk("a", "rollback window minutes")], 1)
            .unwrap();
        let mut big = vec![chunk("b", "rollback window minutes")];
        big.extend((0..40).map(|i| chunk(&format!("f{i}"), "unrelated filler about invoices")));
        index.refresh_scope("big", "gen1", &big, 1).unwrap();

        let scores = index
            .text_scores("rollback", &only(&["tiny", "big"]), 100)
            .unwrap();
        let a = scores.iter().find(|s| s.chunk_id == "a").unwrap();
        let b = scores.iter().find(|s| s.chunk_id == "b").unwrap();
        assert!(
            (a.bm25 - b.bm25).abs() < 1e-9,
            "same text, same corpus, same score: {} vs {}",
            a.bm25,
            b.bm25
        );
    }

    #[test]
    fn a_delta_lands_a_vector_the_embedding_lane_just_linked() {
        // The lane writes into the LIVE index without rebuilding it, so nothing
        // downstream re-reads the scope. If the delta did not carry the vector
        // here, the chunk would stay text-only in the replica until some
        // unrelated rebuild happened to rotate the generation.
        let (_dir, mut index) = store();
        index
            .refresh_scope("s", "gen1", &[chunk("a", "alpha"), chunk("b", "beta")], 1)
            .unwrap();
        assert_eq!(index.corpus_size().unwrap(), (1, 2, 0));

        let delta = ScopeDelta {
            vectors_added: vec![("a".to_owned(), vec![1.0, 0.0])],
        };
        assert!(index.apply_delta("s", "gen1", "gen1", &delta, 2).unwrap());
        assert_eq!(index.corpus_size().unwrap(), (1, 2, 1));

        let scored = index.vector_scores(&[1.0, 0.0], &only(&["s"]), 10).unwrap();
        assert_eq!(scored.len(), 1);
        assert_eq!(scored[0].chunk_id, "a");
    }

    #[test]
    fn a_delta_will_not_stamp_a_scope_the_replica_never_projected() {
        // The dangerous failure: stamping a generation for text that was never
        // replicated makes the next search believe the scope is current and
        // skip the projection it needs, so the scope's chunks silently leave
        // the corpus.
        let (_dir, mut index) = store();
        let delta = ScopeDelta {
            vectors_added: vec![("a".to_owned(), vec![1.0, 0.0])],
        };
        assert!(!index
            .apply_delta("never-seen", "gen1", "gen1", &delta, 1)
            .unwrap());
        assert_eq!(index.scope_generation("never-seen").unwrap(), None);
        assert_eq!(index.corpus_size().unwrap(), (0, 0, 0));
    }

    #[test]
    fn a_refresh_is_what_removes_a_purged_chunk_from_the_text_index() {
        // R25-7: the delta path used to carry a `removed` list for this, with a
        // doc comment naming purge as its writer. Purge never used it — it takes
        // a full re-projection (05 §3.5) — so the field and its test described a
        // path that did not exist. This is the same contract against the code
        // that actually runs.
        let (_dir, mut index) = store();
        index
            .refresh_scope(
                "s",
                "gen1",
                &[
                    vectored("a", "alpha secret", vec![1.0, 0.0]),
                    chunk("b", "beta public"),
                ],
                1,
            )
            .unwrap();
        assert_eq!(index.corpus_size().unwrap(), (1, 2, 1));

        index
            .refresh_scope("s", "gen2", &[chunk("b", "beta public")], 2)
            .unwrap();
        assert_eq!(index.corpus_size().unwrap(), (1, 1, 0));
        assert!(
            index
                .text_scores("secret", &only(&["s"]), 10)
                .unwrap()
                .is_empty(),
            "a purged chunk must leave the FTS, not only the content table"
        );
        assert!(index
            .vector_scores(&[1.0, 0.0], &only(&["s"]), 10)
            .unwrap()
            .is_empty());
        assert_eq!(
            index.scope_generation("s").unwrap().as_deref(),
            Some("gen2")
        );
    }

    #[test]
    fn a_delta_ignores_a_vector_for_a_chunk_the_replica_has_not_projected_yet() {
        // Not an error: the scope was projected before this chunk existed, and
        // the projection that first picks the chunk up carries its vector. An
        // orphan vector row would just be unreachable by every join.
        let (_dir, mut index) = store();
        index
            .refresh_scope("s", "gen1", &[chunk("a", "alpha")], 1)
            .unwrap();
        let delta = ScopeDelta {
            vectors_added: vec![("not-yet-projected".to_owned(), vec![1.0, 0.0])],
        };
        assert!(index.apply_delta("s", "gen1", "gen1", &delta, 2).unwrap());
        assert_eq!(index.corpus_size().unwrap(), (1, 1, 0));
    }

    #[test]
    fn a_refresh_drops_the_chunks_the_scope_no_longer_has() {
        // Stale rows keep inflating document frequency, which quietly lowers
        // every other chunk's IDF for those terms.
        let (_dir, mut index) = store();
        index
            .refresh_scope("s", "gen1", &[chunk("a", "alpha"), chunk("b", "beta")], 1)
            .unwrap();
        assert_eq!(index.corpus_size().unwrap(), (1, 2, 0));
        index
            .refresh_scope("s", "gen2", &[chunk("a", "alpha")], 2)
            .unwrap();
        assert_eq!(index.corpus_size().unwrap(), (1, 1, 0));
        assert!(
            index
                .text_scores("beta", &only(&["s"]), 10)
                .unwrap()
                .is_empty(),
            "the dropped chunk must leave the FTS too, not just the content table"
        );
        assert_eq!(
            index.scope_generation("s").unwrap().as_deref(),
            Some("gen2")
        );
    }

    #[test]
    fn a_refresh_drops_the_vectors_the_scope_no_longer_has() {
        // Same argument as the FTS rows: an orphaned vector would keep being
        // cosine-ranked against every query, offering a hit for a chunk that
        // no longer exists.
        let (_dir, mut index) = store();
        index
            .refresh_scope(
                "s",
                "gen1",
                &[
                    vectored("a", "alpha", vec![1.0, 0.0]),
                    vectored("b", "beta", vec![0.0, 1.0]),
                ],
                1,
            )
            .unwrap();
        assert_eq!(index.corpus_size().unwrap(), (1, 2, 2));
        index
            .refresh_scope("s", "gen2", &[vectored("a", "alpha", vec![1.0, 0.0])], 2)
            .unwrap();
        assert_eq!(index.corpus_size().unwrap(), (1, 1, 1));
        let hits = index.vector_scores(&[0.0, 1.0], &only(&["s"]), 10).unwrap();
        assert!(
            hits.iter().all(|hit| hit.chunk_id != "b"),
            "a dropped chunk's vector must not survive the refresh: {hits:?}"
        );
    }

    #[test]
    fn retain_drops_scopes_the_registry_no_longer_lists() {
        // A scope deleted from disk must stop skewing corpus statistics on the
        // very next search, not at some later rebuild.
        let (_dir, mut index) = store();
        index
            .refresh_scope("live", "g", &[chunk("a", "alpha")], 1)
            .unwrap();
        index
            .refresh_scope("dead", "g", &[vectored("b", "alpha", vec![1.0, 0.0])], 1)
            .unwrap();
        assert_eq!(index.corpus_size().unwrap(), (2, 2, 1));
        let live: BTreeSet<String> = ["live".to_owned()].into_iter().collect();
        assert_eq!(index.retain_scopes(&live).unwrap(), 1);
        assert_eq!(index.corpus_size().unwrap(), (1, 1, 0));
        assert!(index.scope_generation("dead").unwrap().is_none());
        assert!(index
            .text_scores("alpha", &only(&["live", "dead"]), 10)
            .unwrap()
            .iter()
            .all(|score| score.scope_id != "dead"));
    }

    #[test]
    fn vectors_rank_by_cosine_across_scopes() {
        let (_dir, mut index) = store();
        index
            .refresh_scope("s1", "g", &[vectored("near", "x", vec![1.0, 0.1])], 1)
            .unwrap();
        index
            .refresh_scope("s2", "g", &[vectored("far", "y", vec![0.0, 1.0])], 1)
            .unwrap();
        let scores = index
            .vector_scores(&[1.0, 0.0], &only(&["s1", "s2"]), 10)
            .unwrap();
        assert_eq!(scores[0].chunk_id, "near");
        assert_eq!(scores[1].chunk_id, "far");
        let ranks = vector_ranks(&scores);
        assert_eq!(ranks[&("s1".into(), "near".into())], 1);
        assert_eq!(ranks[&("s2".into(), "far".into())], 2);
    }

    #[test]
    fn a_delta_will_not_stamp_a_scope_that_is_present_but_behind() {
        // R25-3, and the shape of the bug matters: the first guard here only
        // asked "has this scope ever been projected", which a PARTIALLY stale
        // scope answers yes to. The sequence is the index rotating to gen2, the
        // write-through failing (logged, non-fatal), and the embedding lane
        // then delivering a vector for a chunk the replica never received. The
        // chunk is skipped for not being there — and the scope gets stamped
        // gen2 anyway, so the next search calls it current, skips the
        // projection, and the chunk is gone from the corpus for good.
        let (_dir, mut index) = store();
        index
            .refresh_scope("s", "gen1", &[chunk("a", "alpha")], 1)
            .unwrap();

        // The scope has moved on to gen2 and grown a chunk `b` the replica
        // never received.
        let delta = ScopeDelta {
            vectors_added: vec![("b".to_owned(), vec![1.0, 0.0])],
        };
        assert!(
            !index.apply_delta("s", "gen2", "gen3", &delta, 2).unwrap(),
            "a delta must refuse a replica that is not where it assumed"
        );
        assert_eq!(
            index.scope_generation("s").unwrap().as_deref(),
            Some("gen1"),
            "and must leave the stamp behind, so the next search re-projects"
        );
    }

    #[test]
    fn a_narrowed_search_is_ranked_within_the_scopes_it_asked_for() {
        // The device-wide depth cut is the failure this guards. `big` holds
        // more strong matches than the limit, so an unrestricted top-2 is all
        // `big`; a `--scope small` search would then get back no rows at all,
        // every candidate would lose its term, and the merge would fall
        // through to its (scope_id, chunk_hash) tie-break — results ordered by
        // hash. Measured on the dogfood corpus, that shut out 187 of the 263
        // scopes holding a match for `the `.
        let (_dir, mut index) = store();
        let big: Vec<AggChunk> = (0..8)
            .map(|n| chunk(&format!("b{n}"), "rollback rollback rollback"))
            .collect();
        index.refresh_scope("big", "g", &big, 1).unwrap();
        index
            .refresh_scope(
                "small",
                "g",
                &[chunk(
                    "s0",
                    "rollback happened once in a much longer document",
                )],
                1,
            )
            .unwrap();

        let device_wide = index
            .text_scores("rollback", &only(&["big", "small"]), 2)
            .unwrap();
        assert!(
            device_wide.iter().all(|score| score.scope_id == "big"),
            "premise: the device-wide cut must be all `big`, or this proves nothing"
        );

        let narrowed = index.text_scores("rollback", &only(&["small"]), 2).unwrap();
        assert_eq!(
            narrowed
                .iter()
                .map(|s| s.chunk_id.as_str())
                .collect::<Vec<_>>(),
            ["s0"],
            "a narrowed search must be ranked among the scopes it searched"
        );
    }

    #[test]
    fn narrowing_restricts_the_rows_without_rebasing_the_statistics() {
        // The other half of the same rule: `small`'s chunk must keep the score
        // the whole collection gives it. If narrowing recomputed BM25 over the
        // subset, every folder would become its own collection again — the
        // per-corpus IDF this replica exists to remove.
        let (_dir, mut index) = store();
        let big: Vec<AggChunk> = (0..8)
            .map(|n| chunk(&format!("b{n}"), "rollback rollback rollback"))
            .collect();
        index.refresh_scope("big", "g", &big, 1).unwrap();
        index
            .refresh_scope("small", "g", &[chunk("s0", "rollback once")], 1)
            .unwrap();

        let whole = index
            .text_scores("rollback", &only(&["big", "small"]), 100)
            .unwrap();
        let in_whole = whole
            .iter()
            .find(|score| score.chunk_id == "s0")
            .unwrap()
            .bm25;
        let narrowed = index
            .text_scores("rollback", &only(&["small"]), 100)
            .unwrap();
        assert_eq!(narrowed[0].bm25, in_whole);
    }

    #[test]
    fn the_collection_stamp_follows_any_scope_the_replica_holds() {
        // A cursor freezes this to detect what the per-scope generations
        // cannot: a scope NOBODY searched moving, which shifts the global
        // df/N/avgdl and therefore the ranks of the scopes they did search.
        let (_dir, mut index) = store();
        index
            .refresh_scope("a", "gen1", &[chunk("x", "alpha")], 1)
            .unwrap();
        let before = index.collection_generation().unwrap();

        index
            .refresh_scope("a", "gen1", &[chunk("x", "alpha")], 2)
            .unwrap();
        assert_eq!(
            index.collection_generation().unwrap(),
            before,
            "re-projecting the same generation is not a change"
        );

        index
            .refresh_scope("unsearched", "gen1", &[chunk("y", "beta")], 3)
            .unwrap();
        let after_new_scope = index.collection_generation().unwrap();
        assert_ne!(
            after_new_scope, before,
            "a new scope changes the collection"
        );

        index
            .refresh_scope("a", "gen2", &[chunk("x", "alpha")], 4)
            .unwrap();
        assert_ne!(
            index.collection_generation().unwrap(),
            after_new_scope,
            "a scope moving to a new generation changes the collection"
        );
    }

    #[test]
    fn a_dimension_mismatch_is_skipped_not_scored() {
        // A profile mismatch must not silently produce a garbage cosine that
        // then outranks a correctly-scored chunk.
        let (_dir, mut index) = store();
        index
            .refresh_scope("s", "g", &[vectored("wrong", "x", vec![1.0, 0.0, 0.0])], 1)
            .unwrap();
        assert!(index
            .vector_scores(&[1.0, 0.0], &only(&["s"]), 10)
            .unwrap()
            .is_empty());
    }

    #[test]
    fn ranks_are_dense_and_ordered_by_global_score() {
        let scores = vec![
            TextScore {
                scope_id: "s2".into(),
                chunk_id: "y".into(),
                bm25: -5.0,
            },
            TextScore {
                scope_id: "s1".into(),
                chunk_id: "x".into(),
                bm25: -9.0,
            },
            TextScore {
                scope_id: "s3".into(),
                chunk_id: "z".into(),
                bm25: -1.0,
            },
        ];
        let ranks = text_ranks(&scores);
        // bm25 is negative-is-better, so -9 outranks -5 outranks -1.
        assert_eq!(ranks[&("s1".into(), "x".into())], 1);
        assert_eq!(ranks[&("s2".into(), "y".into())], 2);
        assert_eq!(ranks[&("s3".into(), "z".into())], 3);
    }
}
