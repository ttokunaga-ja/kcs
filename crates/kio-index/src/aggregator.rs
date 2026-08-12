//! Device-level read replica of every scope's committed chunks (`aggregator.sqlite`).
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
//! `kio_eligible_identity` and re-derive eligibility here.
//! That would put liveness logic in two places, and the two would drift. Instead
//! each refresh asks the scope's own code which chunks are live and stores that
//! ANSWER (03 §4 invariant 7). This file therefore contains no liveness rule.
//!
//! Every committed chunk is deliberately present exactly once in the one FTS
//! corpus.  `agg_bindings` supplies the selector/snapshot-specific eligible
//! set in the candidate query's `WHERE`, before its depth cut, without
//! duplicating aliases into the corpus or splitting live/history rankings.
//!
//! The replica also stores the complete Evidence Pointer metadata and image
//! citation relation required to materialize a selected candidate.  Once the
//! candidate query begins, no scope sqlite read is needed to finish a result.
//!
//! # What it is not allowed to decide
//!
//! It is a CACHE, never truth (03 §4). Deleting it costs a re-projection and
//! nothing else, which is why it lives under the cache root.

use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

use rusqlite::{params, params_from_iter, types::Value, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::embedding_store::{f32_from_le_bytes, f32_to_le_bytes, EmbeddingProfileSummary};
use crate::Result;

/// One committed chunk as the collection sees it.
///
/// The replica deliberately retains both live and historical rows in this one
/// table.  The resolved [`AggBinding`] relation decides which rows a particular
/// search may return; splitting live and historical rows into separate FTS
/// collections would put their BM25 ranks on incompatible scales.
#[derive(Debug, Clone, PartialEq)]
pub struct AggChunk {
    /// The scope's `chunks.chunk_id`. Paired with `scope_id` it addresses the
    /// row the way the cross-scope merge addresses a candidate.
    pub chunk_id: String,
    /// Evidence-pointer metadata.  Candidate materialization must not reopen a
    /// scope index after the replica selected a row.
    pub raw_hash: String,
    pub tool_profile_hash: String,
    pub gen: u64,
    pub text: String,
    pub heading_path: Option<String>,
    pub section_id: Option<String>,
    pub byte_start: u64,
    pub byte_end: u64,
    pub unit_key: String,
    pub created_at: String,
    /// The source index's committed-publication marker.
    pub first_seen_commit: String,
    /// `None` means the scope resolver currently considers this row live.  A
    /// non-null value records the refresh snapshot that observed it no longer
    /// current.  Exact historical eligibility is represented by
    /// [`AggBinding`], not re-derived from this scalar interval.
    pub invalidated_commit: Option<String>,
    /// `None` when this chunk has no vector (scope not enriched, or the vector
    /// lane never reached it). Such a chunk still belongs to the text
    /// collection and must keep counting toward `N` and `avgdl`.
    pub embedding: Option<Vec<f32>>,
}

/// A scope-side, already-resolved answer to a visibility question.
///
/// This is intentionally not a copy of `tree_entries`, config associations, or
/// publication rows.  The scope resolver has already applied those predicates;
/// the replica only joins this answer while selecting candidates.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AggBinding {
    /// `current`, `all_history`, `include_deleted`, or `at`.
    pub selector_kind: String,
    /// Snapshot for which the scope resolved this binding.
    pub snapshot_commit: String,
    pub chunk_id: String,
    pub raw_hash: String,
    pub tool_profile_hash: String,
    pub gen: u64,
    pub path_at_commit: String,
    pub pointer_commit: String,
    pub current_paths: Vec<String>,
    pub is_live: bool,
}

/// One image object's projected vector (04 §4.3's `image_vec`).
///
/// Unlike [`AggChunk`] the embedding is not optional: an image with no vector
/// has nothing to contribute to this replica at all — it carries no text, so it
/// would be a row that no lane can score and no statistic counts.
#[derive(Debug, Clone, PartialEq)]
pub struct AggImage {
    /// The `objects/image/` content hash, which is `image_vec`'s primary key.
    pub image_id: String,
    /// The chunk whose Evidence Pointer anchors this image result.
    pub chunk_id: String,
    /// The URI as written by the citing chunk, never reconstructed from the
    /// object hash.
    pub image_uri: String,
    pub embedding: Vec<f32>,
}

/// The source index state captured by a completed replica projection.
///
/// A missing [`AggScopeHeader`] means the replica has never seen the scope at
/// all.  That is deliberately distinct from [`AggIndexStatus::Ready`] with no
/// chunks: strict replica-only search must be able to tell "not projected"
/// apart from "projected and empty" without reopening the source SQLite file.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AggIndexStatus {
    /// The source index was readable and its projection completed.
    Ready,
    /// The source index was absent when its state was recorded.
    Missing,
    /// The source index could not be read as a valid index.
    Corrupt,
    /// The source is between its snapshot publication and index replacement.
    Rebuilding,
}

impl AggIndexStatus {
    fn as_str(self) -> &'static str {
        match self {
            Self::Ready => "ready",
            Self::Missing => "missing",
            Self::Corrupt => "corrupt",
            Self::Rebuilding => "rebuilding",
        }
    }

    fn parse(value: &str) -> Result<Self> {
        match value {
            "ready" => Ok(Self::Ready),
            "missing" => Ok(Self::Missing),
            "corrupt" => Ok(Self::Corrupt),
            "rebuilding" => Ok(Self::Rebuilding),
            _ => Err(crate::IndexError::Schema(format!(
                "unknown aggregator index status: {value}"
            ))),
        }
    }
}

/// Per-scope facts a replica-only search must not re-read from
/// `.kio/index/sqlite.db`.
///
/// The header is written atomically with the corpus rows and resolver output.
/// `current_snapshot_commit` and `current_chunking_config_hash` are absent
/// only when the source has no current snapshot or effective configuration to
/// report.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AggScopeHeader {
    /// The source's current HEAD at projection time. `None` means this scope
    /// had no current snapshot, not that the replica failed to record one.
    pub current_snapshot_commit: Option<String>,
    /// The effective current chunking config. It is absent only when the
    /// source has no configuration to report.
    pub current_chunking_config_hash: Option<String>,
    /// The source `index_metadata.index_generation` captured by this write.
    pub index_generation: String,
    /// The two append-only source boundaries captured by this projection.
    pub max_rowid: u64,
    pub max_association_rowid: u64,
    /// Whether the source exposed `image_vec` at projection time.
    pub has_image_vec: bool,
    /// The actual set of chunk embedding profiles present in the source. It
    /// lets a replica-only caller make the same cross-scope compatibility
    /// decision without probing every source index.
    pub embedding_profiles: Vec<EmbeddingProfileSummary>,
    /// The source-index availability state observed by the writer.
    pub index_status: AggIndexStatus,
}

/// Input marker for a selector/snapshot whose resolver projection completed.
///
/// It must be supplied even when the resolver returned no bindings. The
/// resulting stored marker is what distinguishes a valid empty answer from a
/// cache miss in strict replica-only search.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AggProjectionCompletion {
    pub selector: AggSelector,
    pub snapshot_commit: String,
    /// The config resolved for this selector/snapshot. It is absent only when
    /// that snapshot has no effective chunking configuration.
    pub chunking_config_hash: Option<String>,
    /// Number of shallow ancestors the scope resolver skipped while producing
    /// this answer. It is selector/snapshot-specific, not a scope-global fact.
    pub shallow_skipped: u64,
}

/// All source rows required to atomically replace one scope's replica
/// projection.
///
/// The references must describe a single coherent source-index observation.
/// [`Aggregator::refresh_scope_with_projection`] writes every field in this
/// request in one transaction, so callers must not combine rows captured from
/// different source generations.
pub struct AggProjectionRequest<'a> {
    pub scope_id: &'a str,
    pub header: &'a AggScopeHeader,
    pub chunks: &'a [AggChunk],
    pub images: &'a [AggImage],
    pub bindings: &'a [AggBinding],
    pub completions: &'a [AggProjectionCompletion],
    pub now_ms: i64,
}

/// A stored selector/snapshot completion marker.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AggProjectionMarker {
    pub selector: AggSelector,
    pub snapshot_commit: String,
    pub chunking_config_hash: Option<String>,
    pub shallow_skipped: u64,
    /// Number of resolver binding rows written for this exact selector and
    /// snapshot. Zero is a completed empty answer, not a missing projection.
    pub binding_count: u64,
    pub completed_at: i64,
}

/// The visibility relation a replica query should use.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AggSelector {
    Current,
    AllHistory,
    IncludeDeleted,
    At,
}

impl AggSelector {
    fn as_str(self) -> &'static str {
        match self {
            Self::Current => "current",
            Self::AllHistory => "all_history",
            Self::IncludeDeleted => "include_deleted",
            Self::At => "at",
        }
    }
}

/// A CAS-preflighted binding that a historical replica query may use.
///
/// The replica owns candidate selection, but it does not own the commit/tree
/// truth that determines whether a historical alias is still readable.  The
/// CLI builds these rows from its CAS-only history plan immediately before the
/// query.  They are deliberately more specific than a content identity: an
/// alias's path, evidence commit, liveness, and current-path presentation are
/// all part of the answer that must not survive a newly shallow tree.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AggBindingFilter {
    pub scope_id: String,
    pub raw_hash: String,
    pub tool_profile_hash: String,
    pub gen: u64,
    pub path_at_commit: String,
    pub pointer_commit: String,
    pub current_paths: Vec<String>,
    pub is_live: bool,
}

/// Inputs to the replica's only candidate-selection path.
pub struct AggSearchRequest<'a> {
    pub scopes: &'a BTreeSet<String>,
    /// One resolved snapshot per selected scope.  The keys are also used to
    /// restrict returned rows, while global FTS statistics remain device-wide.
    pub snapshots: &'a BTreeMap<String, String>,
    pub selector: AggSelector,
    /// `Some` means the caller has revalidated the exact historical binding
    /// relation against source CAS.  An empty slice is a verified empty answer,
    /// not an instruction to use every persisted binding.
    pub binding_filter: Option<&'a [AggBindingFilter]>,
    pub since_cutoff: Option<&'a str>,
    pub match_expr: Option<&'a str>,
    /// Equivalence-expanded forms for each pure-short query token.
    pub short_token_forms: &'a [Vec<String>],
    pub query_embedding: Option<&'a [f32]>,
    pub search_text: bool,
    pub search_vector: bool,
    pub candidate_depth: u64,
}

/// One materialized replica candidate.  It contains every field the CLI needs
/// to issue an Evidence Pointer and must therefore be sufficient without a
/// follow-up read of `.kio/index/sqlite.db`.
#[derive(Debug, Clone, PartialEq)]
pub struct AggCandidate {
    pub scope_id: String,
    /// The chunk cited by the result.  Image rows carry the citing chunk here.
    pub chunk_id: String,
    /// `None` for a chunk row; otherwise this is the image object's hash.
    pub image_id: Option<String>,
    pub image_uri: Option<String>,
    pub text_rank: Option<u64>,
    pub vector_rank: Option<u64>,
    pub raw_hash: String,
    pub tool_profile_hash: String,
    pub gen: u64,
    pub heading_path: Option<String>,
    pub section_id: Option<String>,
    pub byte_start: u64,
    pub byte_end: u64,
    pub text: String,
    pub unit_key: String,
    pub bindings: Vec<AggBinding>,
    pub embedding: Option<Vec<f32>>,
}

#[derive(Debug, Clone)]
struct CandidateSeed {
    scope_id: String,
    chunk_id: String,
    image_id: Option<String>,
    image_uri: Option<String>,
    text_rank: Option<u64>,
    vector_rank: Option<u64>,
    embedding: Option<Vec<f32>>,
}

impl CandidateSeed {
    /// The vector lane's own row identity.  An image is ranked by its object
    /// hash, while a chunk is ranked by its chunk id; the citing chunk is only
    /// an Evidence Pointer anchor for an image result.
    fn row_identity(&self) -> &str {
        self.image_id.as_deref().unwrap_or(self.chunk_id.as_str())
    }
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
    /// The scored row's own identity: a `chunk_id` from [`Aggregator::vector_scores`],
    /// an image object hash from [`Aggregator::image_vector_scores`].
    ///
    /// Not `chunk_id`, because the two sources are meant to be CONCATENATED
    /// before [`vector_ranks`] runs. 03 §7 fixes one multimodal space, so a
    /// chunk's cosine and an image's are the same quantity, and ranking them
    /// separately would hand each list its own rank 1 — the very scale mixture
    /// the replica exists to remove (05 §1.8), one level down.
    pub row_id: String,
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
/// replaces the scope's whole projection (`refresh_scope_with_projection`). A
/// delta that could also insert text would be a second, unexercised way to
/// populate a scope.
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

fn encode_embedding_profiles(profiles: &[EmbeddingProfileSummary]) -> Result<String> {
    let mut canonical = profiles.to_vec();
    canonical.sort();
    canonical.dedup();
    serde_json::to_string(&canonical)
        .map_err(|error| crate::IndexError::Schema(format!("aggregator profiles: {error}")))
}

pub struct Aggregator {
    conn: Connection,
}

impl Aggregator {
    /// Open (creating if absent) the replica.
    ///
    /// The FTS tokenizer and the `bm25()` column weights MUST match the
    /// per-scope FTS (`fts::ensure_schema`, `execute_fts_tier`): the scope
    /// planner and the replica share one normalized MATCH expression, so a
    /// tokenizer mismatch would make the projection and its candidate query
    /// disagree about what the user asked for.
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
                -- The source facts required to prepare a strict replica-only
                -- search. A missing row means "never projected"; nullable
                -- current fields describe a successfully recorded bare scope.
                current_snapshot_commit TEXT,
                current_chunking_config_hash TEXT,
                -- The scope's `index_metadata.index_generation` when its rows
                -- were written. Any index change rotates it, so an inequality
                -- is the whole staleness test.
                index_generation TEXT NOT NULL,
                -- Source append boundaries captured by this projection.  An
                -- association can advance without rotating the index stamp,
                -- so exact snapshot bindings must carry both bounds too.
                max_rowid INTEGER NOT NULL,
                max_association_rowid INTEGER NOT NULL,
                has_image_vec INTEGER NOT NULL,
                embedding_profiles_json TEXT NOT NULL,
                index_status TEXT NOT NULL,
                refreshed_at     INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS agg_chunks (
                rowid              INTEGER PRIMARY KEY,
                scope_id           TEXT NOT NULL,
                chunk_id           TEXT NOT NULL,
                raw_hash           TEXT NOT NULL,
                tool_profile_hash  TEXT NOT NULL,
                gen                INTEGER NOT NULL,
                text               TEXT NOT NULL,
                heading_path       TEXT,
                section_id         TEXT,
                byte_start         INTEGER NOT NULL,
                byte_end           INTEGER NOT NULL,
                unit_key           TEXT NOT NULL,
                created_at         TEXT NOT NULL,
                first_seen_commit  TEXT NOT NULL,
                invalidated_commit TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS agg_chunks_key
                ON agg_chunks(scope_id, chunk_id);
            CREATE INDEX IF NOT EXISTS agg_chunks_scope ON agg_chunks(scope_id);
            CREATE INDEX IF NOT EXISTS agg_chunks_identity
                ON agg_chunks(scope_id, raw_hash, tool_profile_hash, gen);
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
            -- Image object vectors (04 §4.3's `image_vec`, projected). No join
            -- to `agg_chunks` and no FTS row: an image contributes nothing to
            -- BM25 — its text-lane standing is INHERITED from the chunk that
            -- cites it (05 §1.7 / U5), and a duplicate document here would
            -- corrupt the very `N`/`df`/`avgdl` this replica exists to get
            -- right. What it needs from the collection is one thing: a global
            -- cosine rank on the same scale as `agg_embeddings`.
            CREATE TABLE IF NOT EXISTS agg_image_embeddings (
                scope_id   TEXT NOT NULL,
                image_id   TEXT NOT NULL,
                vector     BLOB NOT NULL,
                dimensions INTEGER NOT NULL,
                PRIMARY KEY (scope_id, image_id)
            );
            CREATE TABLE IF NOT EXISTS agg_image_refs (
                scope_id TEXT NOT NULL,
                image_id TEXT NOT NULL,
                chunk_id TEXT NOT NULL,
                image_uri TEXT NOT NULL,
                PRIMARY KEY (scope_id, image_id, chunk_id)
            );
            CREATE INDEX IF NOT EXISTS agg_image_refs_chunk
                ON agg_image_refs(scope_id, chunk_id);
            -- Resolver output, not copied source relations.  It is keyed by
            -- chunk so config/publication decisions made by the scope remain
            -- attached to the exact searchable row.
            CREATE TABLE IF NOT EXISTS agg_bindings (
                scope_id TEXT NOT NULL,
                selector_kind TEXT NOT NULL,
                snapshot_commit TEXT NOT NULL,
                chunk_id TEXT NOT NULL,
                raw_hash TEXT NOT NULL,
                tool_profile_hash TEXT NOT NULL,
                gen INTEGER NOT NULL,
                path_at_commit TEXT NOT NULL,
                pointer_commit TEXT NOT NULL,
                current_paths_json TEXT NOT NULL,
                is_live INTEGER NOT NULL,
                PRIMARY KEY (
                    scope_id, selector_kind, snapshot_commit, chunk_id,
                    path_at_commit, pointer_commit
                )
            );
            CREATE INDEX IF NOT EXISTS agg_bindings_lookup
                ON agg_bindings(
                    selector_kind, snapshot_commit, scope_id, chunk_id
                );
            -- A binding relation has no row for a valid empty answer. Keep a
            -- separate completion marker so direct search can distinguish it
            -- from an incomplete projection and fail closed without opening
            -- source SQLite.
            CREATE TABLE IF NOT EXISTS agg_projection_markers (
                scope_id TEXT NOT NULL,
                selector_kind TEXT NOT NULL,
                snapshot_commit TEXT NOT NULL,
                chunking_config_hash TEXT,
                shallow_skipped INTEGER NOT NULL,
                binding_count INTEGER NOT NULL,
                completed_at INTEGER NOT NULL,
                PRIMARY KEY(scope_id, selector_kind, snapshot_commit)
            );
            "#,
        )?;
        Ok(Self { conn })
    }

    /// One stamp for the whole collection: every scope this replica holds,
    /// paired with the generation and projection bounds it holds for that
    /// scope.
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
        let mut stmt = self.conn.prepare(
            "SELECT scope_id, current_snapshot_commit, current_chunking_config_hash,
                        index_generation, max_rowid, max_association_rowid, has_image_vec,
                        embedding_profiles_json, index_status
                 FROM agg_scopes ORDER BY scope_id",
        )?;
        let rows = stmt.query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, Option<String>>(1)?,
                row.get::<_, Option<String>>(2)?,
                row.get::<_, String>(3)?,
                row.get::<_, i64>(4)?,
                row.get::<_, i64>(5)?,
                row.get::<_, i64>(6)?,
                row.get::<_, String>(7)?,
                row.get::<_, String>(8)?,
            ))
        })?;
        let mut hasher = Sha256::new();
        for row in rows {
            let (
                scope_id,
                current_snapshot_commit,
                current_chunking_config_hash,
                generation,
                max_rowid,
                max_association_rowid,
                has_image_vec,
                embedding_profiles_json,
                index_status,
            ) = row?;
            hasher.update(scope_id.as_bytes());
            hasher.update(b"\t");
            hasher.update(
                current_snapshot_commit
                    .as_deref()
                    .unwrap_or_default()
                    .as_bytes(),
            );
            hasher.update(b"\t");
            hasher.update(
                current_chunking_config_hash
                    .as_deref()
                    .unwrap_or_default()
                    .as_bytes(),
            );
            hasher.update(b"\t");
            hasher.update(generation.as_bytes());
            hasher.update(b"\n");
            hasher.update(max_rowid.to_string().as_bytes());
            hasher.update(b"\t");
            hasher.update(max_association_rowid.to_string().as_bytes());
            hasher.update(b"\n");
            hasher.update(has_image_vec.to_string().as_bytes());
            hasher.update(b"\n");
            hasher.update(embedding_profiles_json.as_bytes());
            hasher.update(b"\t");
            hasher.update(index_status.as_bytes());
            hasher.update(b"\n");
        }
        Ok(format!("sha256:{}", lower_hex(&hasher.finalize())))
    }

    /// The generation this replica holds for `scope_id`, or `None` if it holds
    /// nothing for it. Writer-side delta application uses equality with its
    /// expected pre-change generation as its precondition.
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

    /// The source append boundaries captured by the last full projection for
    /// `scope_id`.  They supplement the generation stamp for mutations that
    /// add a config association without rotating that stamp.
    pub fn scope_projection_bounds(&self, scope_id: &str) -> Result<Option<(u64, u64)>> {
        self.conn
            .query_row(
                "SELECT max_rowid, max_association_rowid
                 FROM agg_scopes WHERE scope_id = ?1",
                params![scope_id],
                |row| Ok((row.get::<_, i64>(0)? as u64, row.get::<_, i64>(1)? as u64)),
            )
            .optional()
            .map_err(Into::into)
    }

    /// Whether `image_vec` existed in the source index when the current scope
    /// projection was made.  A legacy source may legitimately lack that table;
    /// its old image candidates must not survive in the replica after the
    /// source has been observed without it.
    pub fn scope_has_image_vec(&self, scope_id: &str) -> Result<Option<bool>> {
        self.conn
            .query_row(
                "SELECT has_image_vec FROM agg_scopes WHERE scope_id = ?1",
                params![scope_id],
                |row| Ok(row.get::<_, i64>(0)? != 0),
            )
            .optional()
            .map_err(Into::into)
    }

    /// The complete source header last committed with `scope_id`'s replica
    /// projection. `None` means this device has no completed projection for
    /// the scope, which is intentionally different from a `Ready` header with
    /// zero chunks or zero bindings.
    pub fn scope_header(&self, scope_id: &str) -> Result<Option<AggScopeHeader>> {
        let row = self
            .conn
            .query_row(
                "SELECT current_snapshot_commit, current_chunking_config_hash,
                        index_generation, max_rowid, max_association_rowid,
                        has_image_vec, embedding_profiles_json, index_status
                 FROM agg_scopes WHERE scope_id = ?1",
                params![scope_id],
                |row| {
                    Ok((
                        row.get::<_, Option<String>>(0)?,
                        row.get::<_, Option<String>>(1)?,
                        row.get::<_, String>(2)?,
                        row.get::<_, i64>(3)?,
                        row.get::<_, i64>(4)?,
                        row.get::<_, i64>(5)?,
                        row.get::<_, String>(6)?,
                        row.get::<_, String>(7)?,
                    ))
                },
            )
            .optional()?;
        let Some((
            current_snapshot_commit,
            current_chunking_config_hash,
            index_generation,
            max_rowid,
            max_association_rowid,
            has_image_vec,
            embedding_profiles_json,
            index_status,
        )) = row
        else {
            return Ok(None);
        };
        let embedding_profiles = serde_json::from_str(&embedding_profiles_json)
            .map_err(|error| crate::IndexError::Schema(format!("aggregator profiles: {error}")))?;
        Ok(Some(AggScopeHeader {
            current_snapshot_commit,
            current_chunking_config_hash,
            index_generation,
            max_rowid: max_rowid as u64,
            max_association_rowid: max_association_rowid as u64,
            has_image_vec: has_image_vec != 0,
            embedding_profiles,
            index_status: AggIndexStatus::parse(&index_status)?,
        }))
    }

    /// Update only a scope header, preserving every corpus row, binding, and
    /// completion marker already in the replica.
    ///
    /// A writer may use this to publish `Rebuilding` together with the new
    /// snapshot facts after HEAD advances but before a replacement source index
    /// is ready to project. A full refresh in that window would erase the last
    /// coherent candidate corpus. Returning `false` for an unknown scope keeps
    /// a cache miss distinct from an invented empty projection.
    pub fn update_scope_header(
        &mut self,
        scope_id: &str,
        header: &AggScopeHeader,
        now_ms: i64,
    ) -> Result<bool> {
        let embedding_profiles_json = encode_embedding_profiles(&header.embedding_profiles)?;
        Ok(self.conn.execute(
            "UPDATE agg_scopes
             SET current_snapshot_commit = ?2,
                 current_chunking_config_hash = ?3,
                 index_generation = ?4,
                 max_rowid = ?5,
                 max_association_rowid = ?6,
                 has_image_vec = ?7,
                 embedding_profiles_json = ?8,
                 index_status = ?9,
                 refreshed_at = ?10
             WHERE scope_id = ?1",
            params![
                scope_id,
                header.current_snapshot_commit,
                header.current_chunking_config_hash,
                header.index_generation,
                header.max_rowid as i64,
                header.max_association_rowid as i64,
                if header.has_image_vec { 1_i64 } else { 0_i64 },
                embedding_profiles_json,
                header.index_status.as_str(),
                now_ms,
            ],
        )? != 0)
    }

    /// Read the selector/snapshot completion marker, including zero-binding
    /// answers. A `None` result is a cache miss, not an empty search result.
    pub fn projection_marker(
        &self,
        scope_id: &str,
        selector: AggSelector,
        snapshot_commit: &str,
    ) -> Result<Option<AggProjectionMarker>> {
        self.conn
            .query_row(
                "SELECT chunking_config_hash, shallow_skipped, binding_count, completed_at
                 FROM agg_projection_markers
                 WHERE scope_id = ?1
                   AND selector_kind = ?2
                   AND snapshot_commit = ?3",
                params![scope_id, selector.as_str(), snapshot_commit],
                |row| {
                    Ok(AggProjectionMarker {
                        selector,
                        snapshot_commit: snapshot_commit.to_owned(),
                        chunking_config_hash: row.get(0)?,
                        shallow_skipped: row.get::<_, i64>(1)? as u64,
                        binding_count: row.get::<_, i64>(2)? as u64,
                        completed_at: row.get(3)?,
                    })
                },
            )
            .optional()
            .map_err(Into::into)
    }

    /// Whether a resolver completion marker exists for this selector and
    /// snapshot. Unlike [`Self::has_binding`], this returns `true` for a valid
    /// empty binding relation.
    pub fn has_completed_projection(
        &self,
        scope_id: &str,
        selector: AggSelector,
        snapshot_commit: &str,
    ) -> Result<bool> {
        Ok(self
            .projection_marker(scope_id, selector, snapshot_commit)?
            .is_some())
    }

    /// Whether this cache has at least one resolved row for an exact selector
    /// and snapshot. This only answers whether the relation is nonempty;
    /// strict readers use [`Self::has_completed_projection`] to distinguish a
    /// valid empty answer from a missing projection.
    pub fn has_binding(
        &self,
        scope_id: &str,
        selector: AggSelector,
        snapshot_commit: &str,
    ) -> Result<bool> {
        Ok(self.conn.query_row(
            "SELECT EXISTS(
                     SELECT 1 FROM agg_bindings
                     WHERE scope_id = ?1
                       AND selector_kind = ?2
                       AND snapshot_commit = ?3
                 )",
            params![scope_id, selector.as_str(), snapshot_commit],
            |row| row.get::<_, i64>(0),
        )? != 0)
    }

    /// The most recently projected snapshot that has bindings for this scope
    /// and selector.  A caller uses this only while a visible purge journal
    /// freezes a scope between its source mutation and the candidate-time
    /// read barrier; ordinary searches must continue to ask for their freshly
    /// resolved snapshot.
    pub fn latest_binding_snapshot(
        &self,
        scope_id: &str,
        selector: AggSelector,
    ) -> Result<Option<String>> {
        self.conn
            .query_row(
                "SELECT snapshot_commit
                 FROM agg_bindings
                 WHERE scope_id = ?1 AND selector_kind = ?2
                 ORDER BY rowid DESC
                 LIMIT 1",
                params![scope_id, selector.as_str()],
                |row| row.get::<_, String>(0),
            )
            .optional()
            .map_err(Into::into)
    }

    /// The latest completed resolver snapshot for a selector, including a
    /// completed empty binding relation. This is the marker-aware counterpart
    /// of [`Self::latest_binding_snapshot`].
    pub fn latest_completed_projection_snapshot(
        &self,
        scope_id: &str,
        selector: AggSelector,
    ) -> Result<Option<String>> {
        self.conn
            .query_row(
                "SELECT snapshot_commit
                 FROM agg_projection_markers
                 WHERE scope_id = ?1 AND selector_kind = ?2
                 ORDER BY completed_at DESC, rowid DESC
                 LIMIT 1",
                params![scope_id, selector.as_str()],
                |row| row.get::<_, String>(0),
            )
            .optional()
            .map_err(Into::into)
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
    /// The replace includes searchable rows, the source header, and completed
    /// selector/snapshot projections in one transaction.
    ///
    /// Writers must pass a complete source header and one completion marker for
    /// every resolver invocation, including a selector/snapshot that produced
    /// zero bindings. A strict replica-only search otherwise cannot distinguish
    /// that valid empty answer from a missing projection.
    pub fn refresh_scope_with_projection(
        &mut self,
        request: AggProjectionRequest<'_>,
    ) -> Result<()> {
        let AggProjectionRequest {
            scope_id,
            header,
            chunks,
            images,
            bindings,
            completions,
            now_ms,
        } = request;
        let embedding_profiles_json = encode_embedding_profiles(&header.embedding_profiles)?;
        let mut completion_details = BTreeMap::<(String, String), (Option<String>, u64)>::new();
        for completion in completions {
            let key = (
                completion.selector.as_str().to_owned(),
                completion.snapshot_commit.clone(),
            );
            if let Some((stored_config, stored_shallow_skipped)) = completion_details.get_mut(&key)
            {
                if *stored_shallow_skipped != completion.shallow_skipped {
                    return Err(crate::IndexError::Schema(format!(
                        "conflicting shallow projection markers for {}:{}",
                        key.0, key.1
                    )));
                }
                if let (Some(stored), Some(incoming)) = (
                    stored_config.as_deref(),
                    completion.chunking_config_hash.as_deref(),
                ) {
                    if stored != incoming {
                        return Err(crate::IndexError::Schema(format!(
                            "conflicting config projection markers for {}:{}",
                            key.0, key.1
                        )));
                    }
                }
                if stored_config.is_none() {
                    *stored_config = completion.chunking_config_hash.clone();
                }
            } else {
                completion_details.insert(
                    key,
                    (
                        completion.chunking_config_hash.clone(),
                        completion.shallow_skipped,
                    ),
                );
            }
        }
        for binding in bindings {
            let key = (
                binding.selector_kind.clone(),
                binding.snapshot_commit.clone(),
            );
            if !completion_details.contains_key(&key) {
                return Err(crate::IndexError::Schema(format!(
                    "binding has no completed projection marker for {}:{}",
                    key.0, key.1
                )));
            }
        }
        let tx = self.conn.transaction()?;
        delete_scope_rows(&tx, scope_id)?;
        {
            let mut ins = tx.prepare(
                "INSERT INTO agg_chunks(
                    scope_id, chunk_id, raw_hash, tool_profile_hash, gen,
                    text, heading_path, section_id, byte_start, byte_end,
                    unit_key, created_at, first_seen_commit, invalidated_commit
                 ) VALUES (
                    ?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14
                 )",
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
                    chunk.raw_hash,
                    chunk.tool_profile_hash,
                    chunk.gen as i64,
                    chunk.text,
                    chunk.heading_path,
                    chunk.section_id,
                    chunk.byte_start as i64,
                    chunk.byte_end as i64,
                    chunk.unit_key,
                    chunk.created_at,
                    chunk.first_seen_commit,
                    chunk.invalidated_commit,
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
        {
            // No rowid to join through, unlike `agg_embeddings`: an image is
            // addressed by its own content hash and has no `agg_chunks` row to
            // hang off (05 §1.7 / U5 — it carries no text).
            //
            // `OR REPLACE` rather than a plain insert because `images` is the
            // caller's list and a duplicate `image_id` in it must not abort a
            // projection: the same figure appearing twice is a fact about the
            // corpus, and the two rows carry the same vector by construction.
            let mut image_vecs = tx.prepare(
                "INSERT OR REPLACE INTO agg_image_embeddings(scope_id, image_id, vector, dimensions)
                 VALUES (?1, ?2, ?3, ?4)",
            )?;
            let mut image_refs = tx.prepare(
                "INSERT INTO agg_image_refs(scope_id, image_id, chunk_id, image_uri)
                 VALUES (?1, ?2, ?3, ?4)",
            )?;
            for image in images {
                image_vecs.execute(params![
                    scope_id,
                    image.image_id,
                    f32_to_le_bytes(&image.embedding),
                    image.embedding.len() as i64
                ])?;
                image_refs.execute(params![
                    scope_id,
                    image.image_id,
                    image.chunk_id,
                    image.image_uri,
                ])?;
            }
        }
        {
            let mut insert = tx.prepare(
                "INSERT INTO agg_bindings(
                    scope_id, selector_kind, snapshot_commit, chunk_id,
                    raw_hash, tool_profile_hash, gen, path_at_commit,
                    pointer_commit, current_paths_json, is_live
                 ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11)",
            )?;
            for binding in bindings {
                insert.execute(params![
                    scope_id,
                    binding.selector_kind,
                    binding.snapshot_commit,
                    binding.chunk_id,
                    binding.raw_hash,
                    binding.tool_profile_hash,
                    binding.gen as i64,
                    binding.path_at_commit,
                    binding.pointer_commit,
                    serde_json::to_string(&binding.current_paths)
                        .map_err(|error| crate::IndexError::Schema(error.to_string()))?,
                    if binding.is_live { 1_i64 } else { 0_i64 },
                ])?;
            }
        }
        {
            let mut insert = tx.prepare(
                "INSERT INTO agg_projection_markers(
                    scope_id, selector_kind, snapshot_commit, chunking_config_hash,
                    shallow_skipped, binding_count, completed_at
                 ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
            )?;
            for ((selector_kind, snapshot_commit), (chunking_config_hash, shallow_skipped)) in
                completion_details
            {
                let binding_count = bindings
                    .iter()
                    .filter(|binding| {
                        binding.selector_kind == selector_kind
                            && binding.snapshot_commit == snapshot_commit
                    })
                    .count();
                insert.execute(params![
                    scope_id,
                    selector_kind,
                    snapshot_commit,
                    chunking_config_hash,
                    shallow_skipped as i64,
                    binding_count as i64,
                    now_ms,
                ])?;
            }
        }
        // Written LAST, deliberately: the generation stamp is this projection's
        // commit marker. A failed writer leaves the prior coherent projection
        // intact and marks the scope unavailable; direct search then fails
        // closed until a writer publishes a complete replacement.
        tx.execute(
            "INSERT INTO agg_scopes(
                 scope_id, current_snapshot_commit, current_chunking_config_hash,
                 index_generation, max_rowid, max_association_rowid, has_image_vec,
                 embedding_profiles_json, index_status, refreshed_at
             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10)
             ON CONFLICT(scope_id) DO UPDATE SET
                 current_snapshot_commit = excluded.current_snapshot_commit,
                 current_chunking_config_hash = excluded.current_chunking_config_hash,
                 index_generation = excluded.index_generation,
                 max_rowid = excluded.max_rowid,
                 max_association_rowid = excluded.max_association_rowid,
                 has_image_vec = excluded.has_image_vec,
                 embedding_profiles_json = excluded.embedding_profiles_json,
                 index_status = excluded.index_status,
                 refreshed_at = excluded.refreshed_at",
            params![
                scope_id,
                header.current_snapshot_commit,
                header.current_chunking_config_hash,
                header.index_generation,
                header.max_rowid as i64,
                header.max_association_rowid as i64,
                if header.has_image_vec { 1_i64 } else { 0_i64 },
                embedding_profiles_json,
                header.index_status.as_str(),
                now_ms,
            ],
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
        // Stamped LAST, for the same atomic-projection reason as the full
        // `refresh_scope_with_projection` path.
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
    /// keeps the ordering identical to the former per-scope implementation.
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
        let mut scored = score_rows(rows, query)?;
        sort_and_truncate(&mut scored, limit);
        Ok(scored)
    }

    /// [`Self::vector_scores`]' image counterpart (04 §4.3's `image_vec`).
    ///
    /// Same scan, same skip-on-dimension-mismatch, same order — because these
    /// scores are meant to be CONCATENATED with the chunk ones before
    /// [`vector_ranks`] assigns a rank. 03 §7 fixes one multimodal space, so
    /// separate rank sequences would give each list its own rank 1 and let the
    /// nearest image tie the nearest chunk however far away it actually is.
    ///
    /// `limit` is applied to this list on its own, as a scan bound. The caller's
    /// concatenation is then re-cut by whatever depth it wants; taking the cut
    /// only after the merge would mean materializing both full lists.
    pub fn image_vector_scores(
        &self,
        query: &[f32],
        scopes: &BTreeSet<String>,
        limit: u64,
    ) -> Result<Vec<VectorScore>> {
        self.load_query_scopes(scopes)?;
        let mut stmt = self.conn.prepare(
            "SELECT i.scope_id, i.image_id, i.vector, i.dimensions
             FROM agg_image_embeddings i
             JOIN query_scopes q ON q.scope_id = i.scope_id",
        )?;
        let rows = stmt.query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, Vec<u8>>(2)?,
                row.get::<_, i64>(3)?,
            ))
        })?;
        let mut scored = score_rows(rows, query)?;
        sort_and_truncate(&mut scored, limit);
        Ok(scored)
    }

    /// Select and materialize candidates entirely from the device replica.
    ///
    /// The scope index is deliberately absent from this method's inputs. Writer
    /// paths may publish a projection before invoking it, but candidate ranking
    /// and Evidence Pointer materialization must not reopen a scope sqlite
    /// database after this point.
    pub fn search_candidates(&self, request: &AggSearchRequest<'_>) -> Result<Vec<AggCandidate>> {
        if request.candidate_depth == 0 || request.scopes.is_empty() {
            return Ok(Vec::new());
        }
        self.load_query_eligibility(request)?;

        let mut seeds = BTreeMap::<(String, String), CandidateSeed>::new();
        if request.search_text {
            let text_scores = if let Some(match_expr) = request.match_expr {
                self.replica_fts_scores(match_expr, request.since_cutoff, request.candidate_depth)?
            } else if !request.short_token_forms.is_empty() {
                self.replica_short_scores(
                    request.short_token_forms,
                    request.since_cutoff,
                    request.candidate_depth,
                )?
            } else {
                Vec::new()
            };
            for (rank, score) in text_scores.into_iter().enumerate() {
                let key = (score.scope_id.clone(), format!("chunk:{}", score.chunk_id));
                seeds.entry(key).or_insert(CandidateSeed {
                    scope_id: score.scope_id,
                    chunk_id: score.chunk_id,
                    image_id: None,
                    image_uri: None,
                    text_rank: Some(rank as u64 + 1),
                    vector_rank: None,
                    embedding: None,
                });
            }
        }

        if request.search_vector {
            if let Some(query) = request.query_embedding {
                let mut vectors = self.replica_vector_seeds(query)?;
                vectors.sort_by(|a, b| {
                    b.1.total_cmp(&a.1)
                        .then_with(|| a.0.scope_id.cmp(&b.0.scope_id))
                        // A shared vector lane has one deterministic
                        // `(scope_id, row identity)` tie-break. Comparing an
                        // `Option<image_id>` here would put every chunk ahead
                        // of every image on equal cosine, irrespective of
                        // their actual row identities.
                        .then_with(|| a.0.row_identity().cmp(b.0.row_identity()))
                        .then_with(|| a.0.chunk_id.cmp(&b.0.chunk_id))
                });
                vectors.truncate(request.candidate_depth as usize);
                for (rank, (mut seed, _)) in vectors.into_iter().enumerate() {
                    seed.vector_rank = Some(rank as u64 + 1);
                    if seed.image_id.is_some() {
                        let chunk_key = (seed.scope_id.clone(), format!("chunk:{}", seed.chunk_id));
                        if let Some(chunk) = seeds.get(&chunk_key) {
                            seed.text_rank = chunk.text_rank;
                        }
                    }
                    let row_key = match &seed.image_id {
                        Some(image_id) => format!("image:{image_id}"),
                        None => format!("chunk:{}", seed.chunk_id),
                    };
                    let key = (seed.scope_id.clone(), row_key);
                    match seeds.get_mut(&key) {
                        Some(existing) => {
                            existing.vector_rank = seed.vector_rank;
                            existing.embedding = seed.embedding;
                        }
                        None => {
                            seeds.insert(key, seed);
                        }
                    }
                }
            }
        }

        let mut candidates = Vec::new();
        for seed in seeds.into_values() {
            let Some(mut candidate) = self.materialize_seed(&seed, request.selector)? else {
                continue;
            };
            candidate.text_rank = seed.text_rank;
            candidate.vector_rank = seed.vector_rank;
            candidate.embedding = seed.embedding;
            candidates.push(candidate);
        }
        Ok(candidates)
    }

    fn load_query_eligibility(&self, request: &AggSearchRequest<'_>) -> Result<()> {
        self.conn.execute_batch(
            "CREATE TEMP TABLE IF NOT EXISTS query_snapshots (
                 scope_id TEXT PRIMARY KEY,
                 snapshot_commit TEXT NOT NULL
             );
             CREATE TEMP TABLE IF NOT EXISTS query_runtime_bindings (
                 scope_id TEXT NOT NULL,
                 raw_hash TEXT NOT NULL,
                 tool_profile_hash TEXT NOT NULL,
                 gen INTEGER NOT NULL,
                 path_at_commit TEXT NOT NULL,
                 pointer_commit TEXT NOT NULL,
                 current_paths_json TEXT NOT NULL,
                 is_live INTEGER NOT NULL,
                 PRIMARY KEY (
                     scope_id, raw_hash, tool_profile_hash, gen,
                     path_at_commit, pointer_commit, current_paths_json, is_live
                 )
             ) WITHOUT ROWID;
             CREATE TEMP TABLE IF NOT EXISTS query_eligible_bindings (
                 scope_id TEXT NOT NULL,
                 selector_kind TEXT NOT NULL,
                 snapshot_commit TEXT NOT NULL,
                 chunk_id TEXT NOT NULL,
                 path_at_commit TEXT NOT NULL,
                 pointer_commit TEXT NOT NULL,
                 PRIMARY KEY (
                     scope_id, selector_kind, snapshot_commit, chunk_id,
                     path_at_commit, pointer_commit
                 )
             ) WITHOUT ROWID;
             CREATE TEMP TABLE IF NOT EXISTS query_eligible_chunks (
                 scope_id TEXT NOT NULL,
                 chunk_id TEXT NOT NULL,
                 PRIMARY KEY(scope_id, chunk_id)
             );
             DELETE FROM query_snapshots;
             DELETE FROM query_runtime_bindings;
             DELETE FROM query_eligible_bindings;
             DELETE FROM query_eligible_chunks;",
        )?;
        {
            let mut insert = self.conn.prepare(
                "INSERT INTO query_snapshots(scope_id, snapshot_commit) VALUES (?1, ?2)",
            )?;
            for scope_id in request.scopes {
                if let Some(snapshot) = request.snapshots.get(scope_id) {
                    insert.execute(params![scope_id, snapshot])?;
                }
            }
        }
        if let Some(filters) = request.binding_filter {
            let mut insert = self.conn.prepare(
                "INSERT OR IGNORE INTO query_runtime_bindings(
                    scope_id, raw_hash, tool_profile_hash, gen,
                    path_at_commit, pointer_commit, current_paths_json, is_live
                 ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
            )?;
            for filter in filters {
                insert.execute(params![
                    filter.scope_id,
                    filter.raw_hash,
                    filter.tool_profile_hash,
                    filter.gen as i64,
                    filter.path_at_commit,
                    filter.pointer_commit,
                    serde_json::to_string(&filter.current_paths)
                        .map_err(|error| crate::IndexError::Schema(error.to_string()))?,
                    if filter.is_live { 1_i64 } else { 0_i64 },
                ])?;
            }
            self.conn.execute(
                "INSERT INTO query_eligible_bindings(
                    scope_id, selector_kind, snapshot_commit, chunk_id,
                    path_at_commit, pointer_commit
                 )
                 SELECT binding.scope_id, binding.selector_kind, binding.snapshot_commit,
                        binding.chunk_id, binding.path_at_commit, binding.pointer_commit
                 FROM agg_bindings binding
                 JOIN query_snapshots snapshot
                   ON snapshot.scope_id = binding.scope_id
                  AND snapshot.snapshot_commit = binding.snapshot_commit
                 JOIN query_runtime_bindings runtime
                   ON runtime.scope_id = binding.scope_id
                  AND runtime.raw_hash = binding.raw_hash
                  AND runtime.tool_profile_hash = binding.tool_profile_hash
                  AND runtime.gen = binding.gen
                  AND runtime.path_at_commit = binding.path_at_commit
                  AND runtime.pointer_commit = binding.pointer_commit
                  AND runtime.current_paths_json = binding.current_paths_json
                  AND runtime.is_live = binding.is_live
                 WHERE binding.selector_kind = ?1",
                params![request.selector.as_str()],
            )?;
        } else {
            self.conn.execute(
                "INSERT INTO query_eligible_bindings(
                    scope_id, selector_kind, snapshot_commit, chunk_id,
                    path_at_commit, pointer_commit
                 )
                 SELECT binding.scope_id, binding.selector_kind, binding.snapshot_commit,
                        binding.chunk_id, binding.path_at_commit, binding.pointer_commit
                 FROM agg_bindings binding
                 JOIN query_snapshots snapshot
                   ON snapshot.scope_id = binding.scope_id
                  AND snapshot.snapshot_commit = binding.snapshot_commit
                 WHERE binding.selector_kind = ?1",
                params![request.selector.as_str()],
            )?;
        }
        self.conn.execute_batch(
            "INSERT INTO query_eligible_chunks(scope_id, chunk_id)
             SELECT DISTINCT scope_id, chunk_id
             FROM query_eligible_bindings;",
        )?;
        Ok(())
    }

    fn replica_fts_scores(
        &self,
        match_expr: &str,
        since_cutoff: Option<&str>,
        limit: u64,
    ) -> Result<Vec<TextScore>> {
        // The resolved binding relation is inside the FTS query, before its
        // depth cut.  Ineligible historical rows must not consume a candidate
        // slot that an eligible lower-ranked row would otherwise receive.
        let sql = "SELECT c.scope_id, c.chunk_id, bm25(agg_fts, 1.0, 0.3) AS score
                   FROM agg_fts
                   JOIN agg_chunks c ON c.rowid = agg_fts.rowid
                   WHERE agg_fts MATCH ?1
                     AND EXISTS (
                       SELECT 1 FROM query_eligible_chunks eligible
                       WHERE eligible.scope_id = c.scope_id
                         AND eligible.chunk_id = c.chunk_id
                   )
                     AND (?2 IS NULL OR c.created_at >= ?2)
                   ORDER BY score, c.scope_id, c.chunk_id
                   LIMIT ?3";
        let mut stmt = self.conn.prepare(sql)?;
        let rows = stmt.query_map(params![match_expr, since_cutoff, limit as i64], |row| {
            Ok(TextScore {
                scope_id: row.get(0)?,
                chunk_id: row.get(1)?,
                bm25: row.get(2)?,
            })
        })?;
        rows.collect::<std::result::Result<Vec<_>, _>>()
            .map_err(Into::into)
    }

    fn replica_short_scores(
        &self,
        token_forms: &[Vec<String>],
        since_cutoff: Option<&str>,
        limit: u64,
    ) -> Result<Vec<TextScore>> {
        let mut clauses = Vec::new();
        let mut binds = Vec::<Value>::new();
        for forms in token_forms {
            if forms.is_empty() {
                return Ok(Vec::new());
            }
            let arms = forms
                .iter()
                .map(|_| "instr(c.text, ?) > 0")
                .collect::<Vec<_>>()
                .join(" OR ");
            clauses.push(format!("({arms})"));
            binds.extend(forms.iter().cloned().map(Value::Text));
        }
        let first_form = token_forms
            .first()
            .and_then(|forms| forms.first())
            .cloned()
            .unwrap_or_default();
        let sql = format!(
            "SELECT c.scope_id, c.chunk_id
             FROM agg_chunks c
             WHERE EXISTS (
                 SELECT 1 FROM query_eligible_chunks eligible
                 WHERE eligible.scope_id = c.scope_id
                   AND eligible.chunk_id = c.chunk_id
             )
               AND (? IS NULL OR c.created_at >= ?)
               AND {}
             ORDER BY instr(c.text, ?) ASC, c.scope_id, c.chunk_id
             LIMIT ?",
            clauses.join(" AND "),
        );
        let mut ordered = Vec::with_capacity(binds.len() + 4);
        ordered.push(match since_cutoff {
            Some(value) => Value::Text(value.to_owned()),
            None => Value::Null,
        });
        ordered.push(match since_cutoff {
            Some(value) => Value::Text(value.to_owned()),
            None => Value::Null,
        });
        ordered.append(&mut binds);
        ordered.push(Value::Text(first_form));
        ordered.push(Value::Integer(limit as i64));
        let mut stmt = self.conn.prepare(&sql)?;
        let rows = stmt.query_map(params_from_iter(ordered.iter()), |row| {
            Ok(TextScore {
                scope_id: row.get(0)?,
                chunk_id: row.get(1)?,
                bm25: 0.0,
            })
        })?;
        rows.collect::<std::result::Result<Vec<_>, _>>()
            .map_err(Into::into)
    }

    fn replica_vector_seeds(&self, query: &[f32]) -> Result<Vec<(CandidateSeed, f64)>> {
        let mut scored = Vec::new();
        let mut chunks = self.conn.prepare(
            "SELECT c.scope_id, c.chunk_id, e.vector, e.dimensions
             FROM agg_embeddings e
             JOIN agg_chunks c ON c.rowid = e.chunk_rowid
             WHERE EXISTS (
                 SELECT 1 FROM query_eligible_chunks eligible
                 WHERE eligible.scope_id = c.scope_id
                   AND eligible.chunk_id = c.chunk_id
             )",
        )?;
        let rows = chunks.query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, Vec<u8>>(2)?,
                row.get::<_, i64>(3)?,
            ))
        })?;
        for row in rows {
            let (scope_id, chunk_id, blob, dimensions) = row?;
            if dimensions as usize != query.len() {
                continue;
            }
            let embedding = f32_from_le_bytes(&blob);
            if embedding.len() != query.len() {
                continue;
            }
            let cosine = cosine_similarity(query, &embedding);
            if cosine.is_finite() {
                scored.push((
                    CandidateSeed {
                        scope_id,
                        chunk_id,
                        image_id: None,
                        image_uri: None,
                        text_rank: None,
                        vector_rank: None,
                        embedding: Some(embedding),
                    },
                    cosine,
                ));
            }
        }
        let mut images = self.conn.prepare(
            "SELECT image.scope_id, image.image_id, ref.chunk_id, ref.image_uri,
                    image.vector, image.dimensions
             FROM agg_image_embeddings image
             JOIN agg_image_refs ref
               ON ref.scope_id = image.scope_id AND ref.image_id = image.image_id
             WHERE EXISTS (
                 SELECT 1 FROM query_eligible_chunks eligible
                 WHERE eligible.scope_id = ref.scope_id
                   AND eligible.chunk_id = ref.chunk_id
             )
             ORDER BY image.scope_id, image.image_id, ref.chunk_id",
        )?;
        let rows = images.query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, String>(3)?,
                row.get::<_, Vec<u8>>(4)?,
                row.get::<_, i64>(5)?,
            ))
        })?;
        let mut seen_images = BTreeSet::new();
        for row in rows {
            let (scope_id, image_id, chunk_id, image_uri, blob, dimensions) = row?;
            if !seen_images.insert((scope_id.clone(), image_id.clone()))
                || dimensions as usize != query.len()
            {
                continue;
            }
            let embedding = f32_from_le_bytes(&blob);
            if embedding.len() != query.len() {
                continue;
            }
            let cosine = cosine_similarity(query, &embedding);
            if cosine.is_finite() {
                scored.push((
                    CandidateSeed {
                        scope_id,
                        chunk_id,
                        image_id: Some(image_id),
                        image_uri: Some(image_uri),
                        text_rank: None,
                        vector_rank: None,
                        embedding: Some(embedding),
                    },
                    cosine,
                ));
            }
        }
        Ok(scored)
    }

    fn materialize_seed(
        &self,
        seed: &CandidateSeed,
        selector: AggSelector,
    ) -> Result<Option<AggCandidate>> {
        let row = self
            .conn
            .query_row(
                "SELECT raw_hash, tool_profile_hash, gen, heading_path, section_id,
                        byte_start, byte_end, text, unit_key
                 FROM agg_chunks
                 WHERE scope_id = ?1 AND chunk_id = ?2",
                params![seed.scope_id, seed.chunk_id],
                |row| {
                    Ok((
                        row.get::<_, String>(0)?,
                        row.get::<_, String>(1)?,
                        row.get::<_, i64>(2)?,
                        row.get::<_, Option<String>>(3)?,
                        row.get::<_, Option<String>>(4)?,
                        row.get::<_, i64>(5)?,
                        row.get::<_, i64>(6)?,
                        row.get::<_, String>(7)?,
                        row.get::<_, String>(8)?,
                    ))
                },
            )
            .optional()?;
        let Some((
            raw_hash,
            tool_profile_hash,
            gen,
            heading_path,
            section_id,
            byte_start,
            byte_end,
            text,
            unit_key,
        )) = row
        else {
            return Ok(None);
        };
        let mut stmt = self.conn.prepare(
            "SELECT binding.snapshot_commit, binding.raw_hash, binding.tool_profile_hash,
                    binding.gen, binding.path_at_commit, binding.pointer_commit,
                    binding.current_paths_json, binding.is_live
             FROM agg_bindings binding
             JOIN query_eligible_bindings eligible
               ON eligible.scope_id = binding.scope_id
              AND eligible.selector_kind = binding.selector_kind
              AND eligible.snapshot_commit = binding.snapshot_commit
              AND eligible.chunk_id = binding.chunk_id
              AND eligible.path_at_commit = binding.path_at_commit
              AND eligible.pointer_commit = binding.pointer_commit
             WHERE binding.scope_id = ?1
               AND binding.chunk_id = ?2
               AND binding.selector_kind = ?3
             ORDER BY binding.path_at_commit, binding.pointer_commit",
        )?;
        let rows = stmt.query_map(
            params![seed.scope_id, seed.chunk_id, selector.as_str()],
            |row| {
                let current_paths = serde_json::from_str::<Vec<String>>(&row.get::<_, String>(6)?)
                    .map_err(|error| {
                        rusqlite::Error::FromSqlConversionFailure(
                            6,
                            rusqlite::types::Type::Text,
                            Box::new(error),
                        )
                    })?;
                Ok(AggBinding {
                    selector_kind: selector.as_str().to_owned(),
                    snapshot_commit: row.get(0)?,
                    chunk_id: seed.chunk_id.clone(),
                    raw_hash: row.get(1)?,
                    tool_profile_hash: row.get(2)?,
                    gen: row.get::<_, i64>(3)? as u64,
                    path_at_commit: row.get(4)?,
                    pointer_commit: row.get(5)?,
                    current_paths,
                    is_live: row.get::<_, i64>(7)? != 0,
                })
            },
        )?;
        let bindings = rows.collect::<std::result::Result<Vec<_>, _>>()?;
        if bindings.is_empty() {
            return Ok(None);
        }
        Ok(Some(AggCandidate {
            scope_id: seed.scope_id.clone(),
            chunk_id: seed.chunk_id.clone(),
            image_id: seed.image_id.clone(),
            image_uri: seed.image_uri.clone(),
            text_rank: seed.text_rank,
            vector_rank: seed.vector_rank,
            raw_hash,
            tool_profile_hash,
            gen: gen as u64,
            heading_path,
            section_id,
            byte_start: byte_start as u64,
            byte_end: byte_end as u64,
            text,
            unit_key,
            bindings,
            embedding: seed.embedding.clone(),
        }))
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
/// Turn one `(scope_id, row_id, blob, dimensions)` projection into scores.
///
/// Shared by both vector lanes so they cannot drift on the two rules that
/// matter: a row whose dimensionality differs from the query is SKIPPED rather
/// than scored (a profile mismatch must not silently yield a garbage cosine),
/// and a non-finite cosine is dropped rather than ranked.
fn score_rows(
    rows: impl Iterator<Item = rusqlite::Result<(String, String, Vec<u8>, i64)>>,
    query: &[f32],
) -> Result<Vec<VectorScore>> {
    let mut scored = Vec::new();
    for row in rows {
        let (scope_id, row_id, blob, dimensions) = row?;
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
                row_id,
                cosine,
            });
        }
    }
    Ok(scored)
}

/// Descending cosine, then the merge's own deterministic tie-break, so the rank
/// a candidate gets does not depend on scan order.
fn sort_and_truncate(scored: &mut Vec<VectorScore>, limit: u64) {
    scored.sort_by(|a, b| {
        b.cosine
            .total_cmp(&a.cosine)
            .then_with(|| a.scope_id.cmp(&b.scope_id))
            .then_with(|| a.row_id.cmp(&b.row_id))
    });
    scored.truncate(limit as usize);
}

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
        "DELETE FROM agg_image_embeddings WHERE scope_id = ?1",
        params![scope_id],
    )?;
    tx.execute(
        "DELETE FROM agg_image_refs WHERE scope_id = ?1",
        params![scope_id],
    )?;
    tx.execute(
        "DELETE FROM agg_bindings WHERE scope_id = ?1",
        params![scope_id],
    )?;
    tx.execute(
        "DELETE FROM agg_projection_markers WHERE scope_id = ?1",
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

/// Dense 1-based ranks by descending cosine, keyed by `(scope_id, row_id)`.
///
/// `vector_scores` already returns this order; re-sorting here keeps the
/// function total for callers that filtered or concatenated — and concatenating
/// the chunk and image lists is exactly how a caller gets ONE rank sequence
/// over the single multimodal space 03 §7 defines.
#[must_use]
pub fn vector_ranks(scores: &[VectorScore]) -> BTreeMap<(String, String), u64> {
    let mut ordered = scores.to_vec();
    ordered.sort_by(|a, b| {
        b.cosine
            .total_cmp(&a.cosine)
            .then_with(|| a.scope_id.cmp(&b.scope_id))
            .then_with(|| a.row_id.cmp(&b.row_id))
    });
    ordered
        .into_iter()
        .enumerate()
        .map(|(index, score)| ((score.scope_id, score.row_id), index as u64 + 1))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn chunk(id: &str, text: &str) -> AggChunk {
        AggChunk {
            chunk_id: id.to_owned(),
            raw_hash: format!("raw:{id}"),
            tool_profile_hash: "tool:test".to_owned(),
            gen: 0,
            text: text.to_owned(),
            heading_path: None,
            section_id: None,
            byte_start: 0,
            byte_end: text.len() as u64,
            unit_key: "unit:test".to_owned(),
            created_at: "2026-01-01T00:00:00Z".to_owned(),
            first_seen_commit: "commit:test".to_owned(),
            invalidated_commit: None,
            embedding: None,
        }
    }

    fn vectored(id: &str, text: &str, embedding: Vec<f32>) -> AggChunk {
        AggChunk {
            embedding: Some(embedding),
            ..chunk(id, text)
        }
    }

    fn binding(selector: &str, snapshot: &str, chunk_id: &str, path: &str) -> AggBinding {
        AggBinding {
            selector_kind: selector.to_owned(),
            snapshot_commit: snapshot.to_owned(),
            chunk_id: chunk_id.to_owned(),
            raw_hash: format!("raw:{chunk_id}"),
            tool_profile_hash: "tool:test".to_owned(),
            gen: 0,
            path_at_commit: path.to_owned(),
            pointer_commit: snapshot.to_owned(),
            current_paths: Vec::new(),
            is_live: selector == "current",
        }
    }

    fn header(generation: &str) -> AggScopeHeader {
        AggScopeHeader {
            current_snapshot_commit: Some("commit:head".to_owned()),
            current_chunking_config_hash: Some("config:current".to_owned()),
            index_generation: generation.to_owned(),
            max_rowid: 17,
            max_association_rowid: 23,
            has_image_vec: true,
            embedding_profiles: vec![EmbeddingProfileSummary {
                dimensions: 2,
                distance: "cosine".to_owned(),
                modality: "multimodal".to_owned(),
                profile_hash: "profile:one".to_owned(),
            }],
            index_status: AggIndexStatus::Ready,
        }
    }

    fn completion(selector: AggSelector, snapshot_commit: &str) -> AggProjectionCompletion {
        AggProjectionCompletion {
            selector,
            snapshot_commit: snapshot_commit.to_owned(),
            chunking_config_hash: Some(format!("config:{snapshot_commit}")),
            shallow_skipped: 0,
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
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "tiny",
                header: &header("gen1"),
                chunks: &[chunk("a", "rollback window minutes")],
                images: &[],
                bindings: &[],
                completions: &[completion(AggSelector::Current, "commit:head")],
                now_ms: 1,
            })
            .unwrap();
        let mut big = vec![chunk("b", "rollback window minutes")];
        big.extend((0..40).map(|i| chunk(&format!("f{i}"), "unrelated filler about invoices")));
        index
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "big",
                header: &header("gen1"),
                chunks: &big,
                images: &[],
                bindings: &[],
                completions: &[completion(AggSelector::Current, "commit:head")],
                now_ms: 1,
            })
            .unwrap();

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
    fn direct_candidates_use_resolved_bindings_without_duplicate_history_ranks() {
        let (_dir, mut index) = store();
        let chunks = [
            chunk("current", "needle xy current"),
            chunk("old", "needle xy historical"),
        ];
        let bindings = vec![
            binding("current", "head", "current", "live.md"),
            binding("all_history", "head", "current", "live.md"),
            binding("all_history", "head", "old", "old-name.md"),
            // Two aliases must expand after ranking, not duplicate the FTS row.
            binding("all_history", "head", "old", "renamed-old.md"),
        ];
        index
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "s",
                header: &header("g"),
                chunks: &chunks,
                images: &[],
                bindings: &bindings,
                completions: &[
                    completion(AggSelector::Current, "head"),
                    completion(AggSelector::AllHistory, "head"),
                ],
                now_ms: 1,
            })
            .unwrap();
        let scopes = only(&["s"]);
        let snapshots = BTreeMap::from([("s".to_owned(), "head".to_owned())]);
        let current = index
            .search_candidates(&AggSearchRequest {
                scopes: &scopes,
                snapshots: &snapshots,
                selector: AggSelector::Current,
                binding_filter: None,
                since_cutoff: None,
                match_expr: Some("needle"),
                short_token_forms: &[],
                query_embedding: None,
                search_text: true,
                search_vector: false,
                candidate_depth: 10,
            })
            .unwrap();
        assert_eq!(current.len(), 1);
        assert_eq!(current[0].chunk_id, "current");

        let historical = index
            .search_candidates(&AggSearchRequest {
                scopes: &scopes,
                snapshots: &snapshots,
                selector: AggSelector::AllHistory,
                binding_filter: None,
                since_cutoff: None,
                match_expr: Some("needle"),
                short_token_forms: &[],
                query_embedding: None,
                search_text: true,
                search_vector: false,
                candidate_depth: 10,
            })
            .unwrap();
        assert_eq!(historical.len(), 2, "aliases do not duplicate rank rows");
        let old = historical.iter().find(|row| row.chunk_id == "old").unwrap();
        assert_eq!(
            old.bindings.len(),
            2,
            "aliases remain available after ranking"
        );

        let forms = vec![vec!["xy".to_owned()]];
        let short = index
            .search_candidates(&AggSearchRequest {
                scopes: &scopes,
                snapshots: &snapshots,
                selector: AggSelector::Current,
                binding_filter: None,
                since_cutoff: None,
                match_expr: None,
                short_token_forms: &forms,
                query_embedding: None,
                search_text: true,
                search_vector: false,
                candidate_depth: 10,
            })
            .unwrap();
        assert_eq!(
            short
                .iter()
                .map(|row| row.chunk_id.as_str())
                .collect::<Vec<_>>(),
            ["current"]
        );
    }

    #[test]
    fn direct_candidates_apply_runtime_binding_filters_before_depth() {
        let (_dir, mut index) = store();
        let current_text = format!("needle {}", "filler ".repeat(128));
        let chunks = [
            chunk("stale", "needle needle needle needle"),
            chunk("current", &current_text),
        ];
        let bindings = [
            binding("all_history", "head", "stale", "discarded.md"),
            binding("all_history", "head", "current", "current.md"),
        ];
        index
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "s",
                header: &header("g"),
                chunks: &chunks,
                images: &[],
                bindings: &bindings,
                completions: &[completion(AggSelector::AllHistory, "head")],
                now_ms: 1,
            })
            .unwrap();
        let scopes = only(&["s"]);
        let snapshots = BTreeMap::from([("s".to_owned(), "head".to_owned())]);

        // The historical alias which would otherwise win the one-row FTS
        // window represents a tree that has since become shallow.
        let stale_first = index
            .search_candidates(&AggSearchRequest {
                scopes: &scopes,
                snapshots: &snapshots,
                selector: AggSelector::AllHistory,
                binding_filter: None,
                since_cutoff: None,
                match_expr: Some("needle"),
                short_token_forms: &[],
                query_embedding: None,
                search_text: true,
                search_vector: false,
                candidate_depth: 1,
            })
            .unwrap();
        assert_eq!(stale_first[0].chunk_id, "stale");

        let allowed = [AggBindingFilter {
            scope_id: "s".to_owned(),
            raw_hash: "raw:current".to_owned(),
            tool_profile_hash: "tool:test".to_owned(),
            gen: 0,
            path_at_commit: "current.md".to_owned(),
            pointer_commit: "head".to_owned(),
            current_paths: Vec::new(),
            is_live: false,
        }];
        let filtered = index
            .search_candidates(&AggSearchRequest {
                scopes: &scopes,
                snapshots: &snapshots,
                selector: AggSelector::AllHistory,
                binding_filter: Some(&allowed),
                since_cutoff: None,
                match_expr: Some("needle"),
                short_token_forms: &[],
                query_embedding: None,
                search_text: true,
                search_vector: false,
                candidate_depth: 1,
            })
            .unwrap();
        assert_eq!(filtered.len(), 1);
        assert_eq!(filtered[0].chunk_id, "current");
        assert_eq!(filtered[0].bindings.len(), 1);
        assert_eq!(filtered[0].bindings[0].path_at_commit, "current.md");

        // An empty preflight result must fail closed rather than reuse stale
        // durable bindings from the preceding request.
        let empty = Vec::<AggBindingFilter>::new();
        let empty_result = index
            .search_candidates(&AggSearchRequest {
                scopes: &scopes,
                snapshots: &snapshots,
                selector: AggSelector::AllHistory,
                binding_filter: Some(&empty),
                since_cutoff: None,
                match_expr: Some("needle"),
                short_token_forms: &[],
                query_embedding: None,
                search_text: true,
                search_vector: false,
                candidate_depth: 1,
            })
            .unwrap();
        assert!(empty_result.is_empty());
    }

    #[test]
    fn a_binding_requires_an_explicit_completion_marker() {
        let (_dir, mut index) = store();
        let error = index
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "s",
                header: &header("g"),
                chunks: &[chunk("a", "alpha")],
                images: &[],
                bindings: &[binding("current", "head", "a", "a.md")],
                completions: &[],
                now_ms: 1,
            })
            .unwrap_err();
        assert!(
            error
                .to_string()
                .contains("binding has no completed projection marker for current:head"),
            "{error}"
        );
        assert!(
            index.scope_header("s").unwrap().is_none(),
            "a rejected projection must not publish a partial header"
        );
    }

    #[test]
    fn direct_candidates_tie_break_chunk_and_image_vectors_by_row_identity() {
        let (_dir, mut index) = store();
        let chunks = [vectored("z-chunk", "caption", vec![1.0, 0.0])];
        let images = [AggImage {
            image_id: "a-image".to_owned(),
            chunk_id: "z-chunk".to_owned(),
            image_uri: "kio://scope/object/image/a-image".to_owned(),
            embedding: vec![1.0, 0.0],
        }];
        let bindings = [binding("current", "head", "z-chunk", "figure.md")];
        index
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "s",
                header: &header("g"),
                chunks: &chunks,
                images: &images,
                bindings: &bindings,
                completions: &[completion(AggSelector::Current, "head")],
                now_ms: 1,
            })
            .unwrap();
        let scopes = only(&["s"]);
        let snapshots = BTreeMap::from([("s".to_owned(), "head".to_owned())]);
        let candidates = index
            .search_candidates(&AggSearchRequest {
                scopes: &scopes,
                snapshots: &snapshots,
                selector: AggSelector::Current,
                binding_filter: None,
                since_cutoff: None,
                match_expr: None,
                short_token_forms: &[],
                query_embedding: Some(&[1.0, 0.0]),
                search_text: false,
                search_vector: true,
                candidate_depth: 10,
            })
            .unwrap();
        let image = candidates
            .iter()
            .find(|candidate| candidate.image_id.as_deref() == Some("a-image"))
            .unwrap();
        let chunk = candidates
            .iter()
            .find(|candidate| candidate.image_id.is_none())
            .unwrap();
        assert_eq!(image.vector_rank, Some(1));
        assert_eq!(chunk.vector_rank, Some(2));
    }

    #[test]
    fn scope_header_and_empty_projection_marker_are_replica_readable() {
        let (_dir, mut index) = store();
        let mut source_header = header("gen-1");
        // A write-through may report duplicate profile rows in an arbitrary
        // source order. The replica stores one deterministic actual set.
        source_header.embedding_profiles.insert(
            0,
            EmbeddingProfileSummary {
                dimensions: 2,
                distance: "cosine".to_owned(),
                modality: "multimodal".to_owned(),
                profile_hash: "profile:two".to_owned(),
            },
        );
        source_header
            .embedding_profiles
            .push(source_header.embedding_profiles[0].clone());
        index
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "empty",
                header: &source_header,
                chunks: &[],
                images: &[],
                bindings: &[],
                completions: &[AggProjectionCompletion {
                    selector: AggSelector::Current,
                    snapshot_commit: "commit:head".to_owned(),
                    chunking_config_hash: Some("config:at-head".to_owned()),
                    shallow_skipped: 2,
                }],
                now_ms: 456,
            })
            .unwrap();

        let stored = index.scope_header("empty").unwrap().unwrap();
        assert_eq!(
            stored.current_snapshot_commit.as_deref(),
            Some("commit:head")
        );
        assert_eq!(
            stored.current_chunking_config_hash.as_deref(),
            Some("config:current")
        );
        assert_eq!(stored.index_generation, "gen-1");
        assert_eq!((stored.max_rowid, stored.max_association_rowid), (17, 23));
        assert!(stored.has_image_vec);
        assert_eq!(stored.index_status, AggIndexStatus::Ready);
        assert_eq!(
            stored
                .embedding_profiles
                .iter()
                .map(|profile| profile.profile_hash.as_str())
                .collect::<Vec<_>>(),
            ["profile:one", "profile:two"],
            "profile summaries are a stable set, not source row order"
        );

        assert_eq!(
            index.scope_generation("empty").unwrap().as_deref(),
            Some("gen-1")
        );
        assert_eq!(
            index.scope_projection_bounds("empty").unwrap(),
            Some((17, 23))
        );
        assert_eq!(index.scope_has_image_vec("empty").unwrap(), Some(true));
        assert!(
            !index
                .has_binding("empty", AggSelector::Current, "commit:head")
                .unwrap(),
            "there are intentionally no binding rows"
        );
        let marker = index
            .projection_marker("empty", AggSelector::Current, "commit:head")
            .unwrap()
            .unwrap();
        assert_eq!(
            marker.chunking_config_hash.as_deref(),
            Some("config:at-head")
        );
        assert_eq!(marker.shallow_skipped, 2);
        assert_eq!(marker.binding_count, 0);
        assert_eq!(marker.completed_at, 456);
        assert!(index
            .has_completed_projection("empty", AggSelector::Current, "commit:head")
            .unwrap());
        assert_eq!(
            index
                .latest_completed_projection_snapshot("empty", AggSelector::Current)
                .unwrap()
                .as_deref(),
            Some("commit:head")
        );
        assert!(index
            .projection_marker("empty", AggSelector::At, "commit:head")
            .unwrap()
            .is_none());
    }

    #[test]
    fn header_update_preserves_rows_and_completion_markers() {
        let (_dir, mut index) = store();
        let first = header("gen-1");
        let completion = AggProjectionCompletion {
            selector: AggSelector::Current,
            snapshot_commit: "commit:head".to_owned(),
            chunking_config_hash: Some("config:head".to_owned()),
            shallow_skipped: 0,
        };
        index
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "scope",
                header: &first,
                chunks: &[chunk("chunk", "retained replica row")],
                images: &[],
                bindings: &[binding("current", "commit:head", "chunk", "doc.md")],
                completions: &[completion],
                now_ms: 1,
            })
            .unwrap();
        let before = index.collection_generation().unwrap();

        let mut rebuilding = first.clone();
        rebuilding.current_snapshot_commit = Some("commit:next".to_owned());
        rebuilding.current_chunking_config_hash = Some("config:next".to_owned());
        rebuilding.index_generation = "gen-2".to_owned();
        rebuilding.index_status = AggIndexStatus::Rebuilding;
        assert!(index.update_scope_header("scope", &rebuilding, 2).unwrap());
        assert!(
            !index
                .update_scope_header("never-projected", &rebuilding, 2)
                .unwrap(),
            "an update must not invent an empty scope"
        );

        assert_eq!(index.scope_header("scope").unwrap(), Some(rebuilding));
        assert_eq!(index.corpus_size().unwrap(), (1, 1, 0));
        let marker = index
            .projection_marker("scope", AggSelector::Current, "commit:head")
            .unwrap()
            .unwrap();
        assert_eq!(marker.chunking_config_hash.as_deref(), Some("config:head"));
        assert_eq!(marker.binding_count, 1);
        assert_ne!(
            index.collection_generation().unwrap(),
            before,
            "a cursor must observe a source state transition while old rows remain"
        );
    }

    #[test]
    fn collection_stamp_includes_replica_only_header_facts() {
        let (_dir, mut index) = store();
        let first = header("gen-1");
        index
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "s",
                header: &first,
                chunks: &[chunk("a", "alpha")],
                images: &[],
                bindings: &[binding("current", "commit:head", "a", "a.md")],
                completions: &[completion(AggSelector::Current, "commit:head")],
                now_ms: 1,
            })
            .unwrap();
        let before = index.collection_generation().unwrap();

        let mut changed = first.clone();
        changed.current_chunking_config_hash = Some("config:next".to_owned());
        changed.embedding_profiles.push(EmbeddingProfileSummary {
            dimensions: 2,
            distance: "cosine".to_owned(),
            modality: "multimodal".to_owned(),
            profile_hash: "profile:next".to_owned(),
        });
        index
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "s",
                header: &changed,
                chunks: &[chunk("a", "alpha")],
                images: &[],
                bindings: &[binding("current", "commit:head", "a", "a.md")],
                completions: &[completion(AggSelector::Current, "commit:head")],
                now_ms: 2,
            })
            .unwrap();
        assert_ne!(
            index.collection_generation().unwrap(),
            before,
            "cursor generation must cover header facts a strict replay reads"
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
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "s",
                header: &header("gen1"),
                chunks: &[chunk("a", "alpha"), chunk("b", "beta")],
                images: &[],
                bindings: &[],
                completions: &[completion(AggSelector::Current, "commit:head")],
                now_ms: 1,
            })
            .unwrap();
        assert_eq!(index.corpus_size().unwrap(), (1, 2, 0));

        let delta = ScopeDelta {
            vectors_added: vec![("a".to_owned(), vec![1.0, 0.0])],
        };
        assert!(index.apply_delta("s", "gen1", "gen1", &delta, 2).unwrap());
        assert_eq!(index.corpus_size().unwrap(), (1, 2, 1));

        let scored = index.vector_scores(&[1.0, 0.0], &only(&["s"]), 10).unwrap();
        assert_eq!(scored.len(), 1);
        assert_eq!(scored[0].row_id, "a");
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
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "s",
                header: &header("gen1"),
                chunks: &[
                    vectored("a", "alpha secret", vec![1.0, 0.0]),
                    chunk("b", "beta public"),
                ],
                images: &[],
                bindings: &[],
                completions: &[completion(AggSelector::Current, "commit:head")],
                now_ms: 1,
            })
            .unwrap();
        assert_eq!(index.corpus_size().unwrap(), (1, 2, 1));

        index
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "s",
                header: &header("gen2"),
                chunks: &[chunk("b", "beta public")],
                images: &[],
                bindings: &[],
                completions: &[completion(AggSelector::Current, "commit:head")],
                now_ms: 2,
            })
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
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "s",
                header: &header("gen1"),
                chunks: &[chunk("a", "alpha")],
                images: &[],
                bindings: &[],
                completions: &[completion(AggSelector::Current, "commit:head")],
                now_ms: 1,
            })
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
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "s",
                header: &header("gen1"),
                chunks: &[chunk("a", "alpha"), chunk("b", "beta")],
                images: &[],
                bindings: &[],
                completions: &[completion(AggSelector::Current, "commit:head")],
                now_ms: 1,
            })
            .unwrap();
        assert_eq!(index.corpus_size().unwrap(), (1, 2, 0));
        index
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "s",
                header: &header("gen2"),
                chunks: &[chunk("a", "alpha")],
                images: &[],
                bindings: &[],
                completions: &[completion(AggSelector::Current, "commit:head")],
                now_ms: 2,
            })
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
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "s",
                header: &header("gen1"),
                chunks: &[
                    vectored("a", "alpha", vec![1.0, 0.0]),
                    vectored("b", "beta", vec![0.0, 1.0]),
                ],
                images: &[],
                bindings: &[],
                completions: &[completion(AggSelector::Current, "commit:head")],
                now_ms: 1,
            })
            .unwrap();
        assert_eq!(index.corpus_size().unwrap(), (1, 2, 2));
        index
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "s",
                header: &header("gen2"),
                chunks: &[vectored("a", "alpha", vec![1.0, 0.0])],
                images: &[],
                bindings: &[],
                completions: &[completion(AggSelector::Current, "commit:head")],
                now_ms: 2,
            })
            .unwrap();
        assert_eq!(index.corpus_size().unwrap(), (1, 1, 1));
        let hits = index.vector_scores(&[0.0, 1.0], &only(&["s"]), 10).unwrap();
        assert!(
            hits.iter().all(|hit| hit.row_id != "b"),
            "a dropped chunk's vector must not survive the refresh: {hits:?}"
        );
    }

    #[test]
    fn retain_drops_scopes_the_registry_no_longer_lists() {
        // A scope deleted from disk must stop skewing corpus statistics on the
        // very next search, not at some later rebuild.
        let (_dir, mut index) = store();
        index
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "live",
                header: &header("g"),
                chunks: &[chunk("a", "alpha")],
                images: &[],
                bindings: &[],
                completions: &[completion(AggSelector::Current, "commit:head")],
                now_ms: 1,
            })
            .unwrap();
        index
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "dead",
                header: &header("g"),
                chunks: &[vectored("b", "alpha", vec![1.0, 0.0])],
                images: &[],
                bindings: &[],
                completions: &[completion(AggSelector::Current, "commit:head")],
                now_ms: 1,
            })
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
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "s1",
                header: &header("g"),
                chunks: &[vectored("near", "x", vec![1.0, 0.1])],
                images: &[],
                bindings: &[],
                completions: &[completion(AggSelector::Current, "commit:head")],
                now_ms: 1,
            })
            .unwrap();
        index
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "s2",
                header: &header("g"),
                chunks: &[vectored("far", "y", vec![0.0, 1.0])],
                images: &[],
                bindings: &[],
                completions: &[completion(AggSelector::Current, "commit:head")],
                now_ms: 1,
            })
            .unwrap();
        let scores = index
            .vector_scores(&[1.0, 0.0], &only(&["s1", "s2"]), 10)
            .unwrap();
        assert_eq!(scores[0].row_id, "near");
        assert_eq!(scores[1].row_id, "far");
        let ranks = vector_ranks(&scores);
        assert_eq!(ranks[&("s1".into(), "near".into())], 1);
        assert_eq!(ranks[&("s2".into(), "far".into())], 2);
    }

    fn image(id: &str, embedding: Vec<f32>) -> AggImage {
        AggImage {
            image_id: id.to_owned(),
            chunk_id: "image-citation".to_owned(),
            image_uri: format!("kio://scope/object/image/{id}"),
            embedding,
        }
    }

    /// 03 §7 fixes ONE multimodal space, so an image's cosine and a chunk's are
    /// the same quantity. Concatenating the two score lists before `vector_ranks`
    /// is what puts them on one rank sequence; ranking each separately would give
    /// the nearest image rank 1 alongside the nearest chunk however far away it
    /// actually is.
    #[test]
    fn image_and_chunk_vectors_rank_in_one_sequence() {
        let (_dir, mut index) = store();
        index
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "s",
                header: &header("g"),
                chunks: &[
                    vectored("near-chunk", "x", vec![1.0, 0.05]),
                    vectored("far-chunk", "y", vec![0.0, 1.0]),
                ],
                images: &[image("mid-image", vec![1.0, 0.5])],
                bindings: &[],
                completions: &[completion(AggSelector::Current, "commit:head")],
                now_ms: 1,
            })
            .unwrap();
        let mut scores = index.vector_scores(&[1.0, 0.0], &only(&["s"]), 10).unwrap();
        scores.extend(
            index
                .image_vector_scores(&[1.0, 0.0], &only(&["s"]), 10)
                .unwrap(),
        );
        let ranks = vector_ranks(&scores);
        assert_eq!(ranks[&("s".into(), "near-chunk".into())], 1);
        assert_eq!(
            ranks[&("s".into(), "mid-image".into())],
            2,
            "the image sits BETWEEN the two chunks, which is only possible on a \
             shared sequence"
        );
        assert_eq!(ranks[&("s".into(), "far-chunk".into())], 3);
    }

    /// An image is live exactly while some live chunk still cites it, so a
    /// re-projection that no longer carries it must take its vector out — the
    /// same rule `a_refresh_drops_the_vectors_the_scope_no_longer_has` pins for
    /// chunks.
    #[test]
    fn a_refresh_drops_the_images_the_scope_no_longer_has() {
        let (_dir, mut index) = store();
        index
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "s",
                header: &header("gen1"),
                chunks: &[chunk("a", "alpha")],
                images: &[image("fig", vec![1.0, 0.0])],
                bindings: &[],
                completions: &[completion(AggSelector::Current, "commit:head")],
                now_ms: 1,
            })
            .unwrap();
        assert_eq!(
            index
                .image_vector_scores(&[1.0, 0.0], &only(&["s"]), 10)
                .unwrap()
                .len(),
            1
        );
        index
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "s",
                header: &header("gen2"),
                chunks: &[chunk("a", "alpha")],
                images: &[],
                bindings: &[],
                completions: &[completion(AggSelector::Current, "commit:head")],
                now_ms: 2,
            })
            .unwrap();
        assert!(
            index
                .image_vector_scores(&[1.0, 0.0], &only(&["s"]), 10)
                .unwrap()
                .is_empty(),
            "an image no live chunk cites must stop being rankable"
        );
    }

    /// The replica's reason for existing is correct corpus statistics, so an
    /// image must not become a document in it. Its text-lane standing is
    /// inherited from the citing chunk (05 §1.7 / U5); a duplicate FTS row here
    /// would inflate `N` and `df` and quietly re-rank unrelated text hits.
    #[test]
    fn an_image_adds_nothing_to_the_text_collection() {
        let (_dir, mut index) = store();
        index
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "s",
                header: &header("gen1"),
                chunks: &[chunk("a", "alpha")],
                images: &[],
                bindings: &[],
                completions: &[completion(AggSelector::Current, "commit:head")],
                now_ms: 1,
            })
            .unwrap();
        let without = index.text_scores("alpha", &only(&["s"]), 10).unwrap();
        index
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "s",
                header: &header("gen2"),
                chunks: &[chunk("a", "alpha")],
                images: &[image("fig", vec![1.0, 0.0])],
                bindings: &[],
                completions: &[completion(AggSelector::Current, "commit:head")],
                now_ms: 2,
            })
            .unwrap();
        let with = index.text_scores("alpha", &only(&["s"]), 10).unwrap();
        assert_eq!(with, without, "adding a figure must not move a text score");
        assert_eq!(index.corpus_size().unwrap().1, 1);
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
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "s",
                header: &header("gen1"),
                chunks: &[chunk("a", "alpha")],
                images: &[],
                bindings: &[],
                completions: &[completion(AggSelector::Current, "commit:head")],
                now_ms: 1,
            })
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
            "and must leave the stamp behind so a writer can detect the mismatch"
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
        index
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "big",
                header: &header("g"),
                chunks: &big,
                images: &[],
                bindings: &[],
                completions: &[completion(AggSelector::Current, "commit:head")],
                now_ms: 1,
            })
            .unwrap();
        index
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "small",
                header: &header("g"),
                chunks: &[chunk(
                    "s0",
                    "rollback happened once in a much longer document",
                )],
                images: &[],
                bindings: &[],
                completions: &[completion(AggSelector::Current, "commit:head")],
                now_ms: 1,
            })
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
        index
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "big",
                header: &header("g"),
                chunks: &big,
                images: &[],
                bindings: &[],
                completions: &[completion(AggSelector::Current, "commit:head")],
                now_ms: 1,
            })
            .unwrap();
        index
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "small",
                header: &header("g"),
                chunks: &[chunk("s0", "rollback once")],
                images: &[],
                bindings: &[],
                completions: &[completion(AggSelector::Current, "commit:head")],
                now_ms: 1,
            })
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
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "a",
                header: &header("gen1"),
                chunks: &[chunk("x", "alpha")],
                images: &[],
                bindings: &[],
                completions: &[completion(AggSelector::Current, "commit:head")],
                now_ms: 1,
            })
            .unwrap();
        let before = index.collection_generation().unwrap();

        index
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "a",
                header: &header("gen1"),
                chunks: &[chunk("x", "alpha")],
                images: &[],
                bindings: &[],
                completions: &[completion(AggSelector::Current, "commit:head")],
                now_ms: 2,
            })
            .unwrap();
        assert_eq!(
            index.collection_generation().unwrap(),
            before,
            "re-projecting the same generation is not a change"
        );

        index
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "unsearched",
                header: &header("gen1"),
                chunks: &[chunk("y", "beta")],
                images: &[],
                bindings: &[],
                completions: &[completion(AggSelector::Current, "commit:head")],
                now_ms: 3,
            })
            .unwrap();
        let after_new_scope = index.collection_generation().unwrap();
        assert_ne!(
            after_new_scope, before,
            "a new scope changes the collection"
        );

        index
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "a",
                header: &header("gen2"),
                chunks: &[chunk("x", "alpha")],
                images: &[],
                bindings: &[],
                completions: &[completion(AggSelector::Current, "commit:head")],
                now_ms: 4,
            })
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
            .refresh_scope_with_projection(AggProjectionRequest {
                scope_id: "s",
                header: &header("g"),
                chunks: &[vectored("wrong", "x", vec![1.0, 0.0, 0.0])],
                images: &[],
                bindings: &[],
                completions: &[completion(AggSelector::Current, "commit:head")],
                now_ms: 1,
            })
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
