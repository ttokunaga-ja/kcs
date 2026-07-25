//! Device-local global text index (`$XDG_CACHE_HOME/kio/global-text.sqlite`).
//!
//! BM25 is defined against a collection: its IDF reads that collection's `N`
//! and per-term document frequency, and its length normalization reads that
//! collection's `avgdl`. Splitting one corpus into per-folder FTS tables makes
//! every scope its own collection, so a chunk's BM25 score — and therefore its
//! rank — means "best in this folder", not "best in the corpus". Measured on
//! the dogfood corpus (428 scopes, 3851 chunks): `N` spans 2..49 and `avgdl`
//! spans 55..1528, and a term appearing in exactly one chunk earns IDF 0.69 in
//! the smallest scope against 7.85 globally — an 11x spread on the same term.
//! Summing a per-scope text rank with a globally-ranked vector term (which
//! `regrade_vector_rank_globally` produces) therefore adds two numbers that are
//! not on the same scale, and the smaller the scope the more its rank-1 is
//! worth. This is the distributed-IR problem Elasticsearch answers with
//! `dfs_query_then_fetch`; the answer here is the same one a single index
//! gives for free — score against the whole corpus.
//!
//! This index is a CACHE, never truth (03-data-model.md §4). It holds a copy of
//! chunk text purely so BM25 has a corpus-sized collection to score against;
//! the per-scope FTS remains the candidate source, keeping every liveness
//! filter (`kio_eligible_identity`, config-generation association, cursor
//! bound) in exactly one place. Deleting this file costs a rebuild and nothing
//! else, which is why it lives under the cache root rather than beside the
//! registry.

use std::collections::BTreeMap;
use std::path::Path;

use rusqlite::{params, Connection, OptionalExtension};

use crate::Result;

/// One chunk as the global collection sees it. `chunk_hash` pairs with
/// `scope_id` to address the row, matching what the cross-scope merge carries.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GlobalChunk {
    pub chunk_hash: String,
    pub text: String,
    pub heading_path: Option<String>,
}

/// A candidate's BM25 against the WHOLE corpus. Lower is better — this is
/// SQLite's `bm25()` sign convention, kept rather than negated so the value can
/// be compared with a per-scope score during debugging without a mental flip.
#[derive(Debug, Clone, PartialEq)]
pub struct GlobalTextScore {
    pub scope_id: String,
    pub chunk_hash: String,
    pub bm25: f64,
}

pub struct GlobalTextIndex {
    conn: Connection,
}

impl GlobalTextIndex {
    /// Open (creating if absent) the global text index.
    ///
    /// The tokenizer and the `bm25()` column weights MUST match the per-scope
    /// FTS (`fts::ensure_schema`, `execute_fts_tier`): the same MATCH
    /// expression is run against both, and a global rank computed under
    /// different tokenization would rank a different query.
    pub fn open(path: &Path) -> Result<Self> {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).map_err(|error| {
                crate::IndexError::Schema(format!("global text cache dir: {error}"))
            })?;
        }
        let conn = Connection::open(path)?;
        conn.pragma_update(None, "journal_mode", "WAL")?;
        conn.busy_timeout(std::time::Duration::from_secs(10))?;
        conn.execute_batch(
            r#"
            CREATE TABLE IF NOT EXISTS global_scopes (
                scope_id         TEXT PRIMARY KEY,
                -- The scope's `index_metadata.index_generation` at the time its
                -- rows were written. Any change rotates the generation, so an
                -- inequality is the whole staleness test.
                index_generation TEXT NOT NULL,
                refreshed_at     INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS global_chunks (
                rowid        INTEGER PRIMARY KEY,
                scope_id     TEXT NOT NULL,
                chunk_hash   TEXT NOT NULL,
                text         TEXT NOT NULL,
                heading_path TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS global_chunks_key
                ON global_chunks(scope_id, chunk_hash);
            CREATE INDEX IF NOT EXISTS global_chunks_scope
                ON global_chunks(scope_id);
            CREATE VIRTUAL TABLE IF NOT EXISTS global_fts USING fts5(
                text, heading_path,
                content='global_chunks', content_rowid='rowid',
                tokenize='trigram'
            );
            "#,
        )?;
        Ok(Self { conn })
    }

    /// The generation this cache holds for `scope_id`, or `None` if it holds
    /// nothing for it.
    pub fn scope_generation(&self, scope_id: &str) -> Result<Option<String>> {
        Ok(self
            .conn
            .query_row(
                "SELECT index_generation FROM global_scopes WHERE scope_id = ?1",
                params![scope_id],
                |row| row.get::<_, String>(0),
            )
            .optional()?)
    }

    /// Replace everything this cache holds for one scope, in one transaction.
    ///
    /// Delete-then-insert rather than upsert: a refresh must also drop chunks
    /// the scope no longer has, or their terms keep inflating the corpus
    /// document frequency forever.
    pub fn refresh_scope(
        &mut self,
        scope_id: &str,
        index_generation: &str,
        chunks: &[GlobalChunk],
        now_ms: i64,
    ) -> Result<()> {
        let tx = self.conn.transaction()?;
        // The FTS is external-content with no triggers here, so its rows are
        // maintained explicitly — a plain DELETE on the content table would
        // leave the index holding terms for rows that no longer exist.
        {
            let mut stmt = tx.prepare(
                "SELECT rowid, text, heading_path FROM global_chunks WHERE scope_id = ?1",
            )?;
            let doomed = stmt
                .query_map(params![scope_id], |row| {
                    Ok((
                        row.get::<_, i64>(0)?,
                        row.get::<_, String>(1)?,
                        row.get::<_, Option<String>>(2)?,
                    ))
                })?
                .collect::<std::result::Result<Vec<_>, _>>()?;
            let mut del = tx.prepare(
                "INSERT INTO global_fts(global_fts, rowid, text, heading_path)
                 VALUES ('delete', ?1, ?2, ?3)",
            )?;
            for (rowid, text, heading) in doomed {
                del.execute(params![rowid, text, heading])?;
            }
        }
        tx.execute(
            "DELETE FROM global_chunks WHERE scope_id = ?1",
            params![scope_id],
        )?;
        {
            let mut ins = tx.prepare(
                "INSERT INTO global_chunks(scope_id, chunk_hash, text, heading_path)
                 VALUES (?1, ?2, ?3, ?4)",
            )?;
            let mut fts = tx.prepare(
                "INSERT INTO global_fts(rowid, text, heading_path) VALUES (?1, ?2, ?3)",
            )?;
            for chunk in chunks {
                ins.execute(params![
                    scope_id,
                    chunk.chunk_hash,
                    chunk.text,
                    chunk.heading_path
                ])?;
                let rowid = tx.last_insert_rowid();
                fts.execute(params![rowid, chunk.text, chunk.heading_path])?;
            }
        }
        tx.execute(
            "INSERT INTO global_scopes(scope_id, index_generation, refreshed_at)
             VALUES (?1, ?2, ?3)
             ON CONFLICT(scope_id) DO UPDATE
               SET index_generation = excluded.index_generation,
                   refreshed_at = excluded.refreshed_at",
            params![scope_id, index_generation, now_ms],
        )?;
        tx.commit()?;
        Ok(())
    }

    /// Drop a scope entirely — used when the registry can no longer resolve it,
    /// so a deleted folder stops contributing document frequency.
    pub fn forget_scope(&mut self, scope_id: &str) -> Result<()> {
        self.refresh_scope(scope_id, "", &[], 0)?;
        self.conn.execute(
            "DELETE FROM global_scopes WHERE scope_id = ?1",
            params![scope_id],
        )?;
        Ok(())
    }

    /// Score `match_expr` against the whole corpus.
    ///
    /// The column weights match `execute_fts_tier`'s `bm25(chunk_fts, 1.0, 0.3)`
    /// so the only difference between this score and the per-scope one is the
    /// collection it is computed over — which is the entire point.
    pub fn scores(&self, match_expr: &str, limit: u64) -> Result<Vec<GlobalTextScore>> {
        let mut stmt = self.conn.prepare(
            "SELECT c.scope_id, c.chunk_hash, bm25(global_fts, 1.0, 0.3) AS score
             FROM global_fts
             JOIN global_chunks c ON c.rowid = global_fts.rowid
             WHERE global_fts MATCH ?1
             ORDER BY score, c.scope_id, c.chunk_hash
             LIMIT ?2",
        )?;
        let rows = stmt.query_map(params![match_expr, limit as i64], |row| {
            Ok(GlobalTextScore {
                scope_id: row.get(0)?,
                chunk_hash: row.get(1)?,
                bm25: row.get(2)?,
            })
        })?;
        let mut out = Vec::new();
        for row in rows {
            out.push(row?);
        }
        Ok(out)
    }

    /// Corpus size, for diagnostics and for the "is this cache worth trusting"
    /// check a caller may want before letting it override per-scope ranks.
    pub fn corpus_size(&self) -> Result<(u64, u64)> {
        let chunks: i64 = self
            .conn
            .query_row("SELECT COUNT(*) FROM global_chunks", [], |row| row.get(0))?;
        let scopes: i64 = self
            .conn
            .query_row("SELECT COUNT(*) FROM global_scopes", [], |row| row.get(0))?;
        Ok((scopes as u64, chunks as u64))
    }
}

/// Rank candidates by their GLOBAL bm25, lowest (best) first.
///
/// Returns 1-based ranks keyed by `(scope_id, chunk_hash)`. A candidate the
/// global index does not know about gets no rank: the caller must treat that as
/// "no text term", never as rank 1, or a cache miss would promote a chunk
/// instead of merely failing to help it.
#[must_use]
pub fn global_text_ranks(scores: &[GlobalTextScore]) -> BTreeMap<(String, String), u64> {
    let mut ordered = scores.to_vec();
    ordered.sort_by(|a, b| {
        a.bm25
            .total_cmp(&b.bm25)
            .then_with(|| a.scope_id.cmp(&b.scope_id))
            .then_with(|| a.chunk_hash.cmp(&b.chunk_hash))
    });
    ordered
        .into_iter()
        .enumerate()
        .map(|(index, score)| ((score.scope_id, score.chunk_hash), index as u64 + 1))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn chunk(hash: &str, text: &str) -> GlobalChunk {
        GlobalChunk {
            chunk_hash: hash.to_owned(),
            text: text.to_owned(),
            heading_path: None,
        }
    }

    fn store() -> (tempfile::TempDir, GlobalTextIndex) {
        let dir = tempfile::tempdir().unwrap();
        let index = GlobalTextIndex::open(&dir.path().join("global-text.sqlite")).unwrap();
        (dir, index)
    }

    #[test]
    fn one_collection_scores_the_same_text_the_same_way_in_every_scope() {
        // The defect this cache exists to fix: identical content in a 2-chunk
        // scope and a 40-chunk scope must not score differently just because
        // their folders differ in size.
        let (_dir, mut index) = store();
        index
            .refresh_scope("tiny", "gen1", &[chunk("a", "rollback window minutes")], 1)
            .unwrap();
        let filler: Vec<GlobalChunk> = (0..40)
            .map(|i| chunk(&format!("f{i}"), "unrelated filler about invoices"))
            .collect();
        let mut big = vec![chunk("b", "rollback window minutes")];
        big.extend(filler);
        index.refresh_scope("big", "gen1", &big, 1).unwrap();

        let scores = index.scores("rollback", 100).unwrap();
        let a = scores.iter().find(|s| s.chunk_hash == "a").unwrap();
        let b = scores.iter().find(|s| s.chunk_hash == "b").unwrap();
        assert!(
            (a.bm25 - b.bm25).abs() < 1e-9,
            "same text, same corpus, same score: {} vs {}",
            a.bm25,
            b.bm25
        );
    }

    #[test]
    fn a_refresh_drops_the_chunks_the_scope_no_longer_has() {
        // Stale rows keep inflating document frequency, which quietly lowers
        // every other chunk's IDF for those terms.
        let (_dir, mut index) = store();
        index
            .refresh_scope("s", "gen1", &[chunk("a", "alpha"), chunk("b", "beta")], 1)
            .unwrap();
        assert_eq!(index.corpus_size().unwrap(), (1, 2));
        index.refresh_scope("s", "gen2", &[chunk("a", "alpha")], 2).unwrap();
        assert_eq!(index.corpus_size().unwrap(), (1, 1));
        assert!(
            index.scores("beta", 10).unwrap().is_empty(),
            "the dropped chunk must leave the FTS too, not just the content table"
        );
        assert_eq!(index.scope_generation("s").unwrap().as_deref(), Some("gen2"));
    }

    #[test]
    fn forgetting_a_scope_removes_it_from_the_collection() {
        let (_dir, mut index) = store();
        index.refresh_scope("gone", "gen1", &[chunk("a", "alpha")], 1).unwrap();
        index.forget_scope("gone").unwrap();
        assert_eq!(index.corpus_size().unwrap(), (0, 0));
        assert!(index.scope_generation("gone").unwrap().is_none());
        assert!(index.scores("alpha", 10).unwrap().is_empty());
    }

    #[test]
    fn ranks_are_dense_and_ordered_by_global_score() {
        let scores = vec![
            GlobalTextScore { scope_id: "s2".into(), chunk_hash: "y".into(), bm25: -5.0 },
            GlobalTextScore { scope_id: "s1".into(), chunk_hash: "x".into(), bm25: -9.0 },
            GlobalTextScore { scope_id: "s3".into(), chunk_hash: "z".into(), bm25: -1.0 },
        ];
        let ranks = global_text_ranks(&scores);
        // bm25 is negative-is-better, so -9 outranks -5 outranks -1.
        assert_eq!(ranks[&("s1".into(), "x".into())], 1);
        assert_eq!(ranks[&("s2".into(), "y".into())], 2);
        assert_eq!(ranks[&("s3".into(), "z".into())], 3);
    }
}
