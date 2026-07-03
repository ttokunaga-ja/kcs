//! Embedding metadata and chunk_vec store contracts.

use rusqlite::{params, Connection};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

use crate::fts::CHUNK_VEC_DIMENSIONS;
use crate::{EmbeddingDistance, EmbeddingModality, EmbeddingTargetType, IndexError, Result};

pub fn adopted_embedding_profile_value() -> Value {
    json!({
        "adapter_kind": "embedding",
        "adapter_role": "multimodal",
        "dimensions": 768,
        "distance": "cosine",
        "modality": "multimodal",
        "model_or_tool_family": "gemini-embedding",
        "model_version_pin": "gemini-embedding-2",
        "runtime_kind": "cloud",
        "spec_version": 1
    })
}

pub fn adopted_embedding_profile_hash() -> Result<String> {
    hash_jcs(&adopted_embedding_profile_value())
}

pub fn embedding_hash(
    target_type: EmbeddingTargetType,
    target_hash: &str,
    dimensions: u64,
    distance: EmbeddingDistance,
    modality: EmbeddingModality,
    profile_hash: &str,
) -> Result<String> {
    let value = json!({
        "dimensions": dimensions,
        "distance": distance_name(distance),
        "modality": modality_name(modality),
        "profile_hash": profile_hash,
        "spec_version": 1,
        "target_hash": target_hash,
        "target_type": target_type_name(target_type),
    });
    hash_jcs(&value)
}

pub fn validate_embedding_profile(
    dimensions: u64,
    distance: EmbeddingDistance,
    modality: EmbeddingModality,
    profile_hash: &str,
) -> Result<()> {
    if modality != EmbeddingModality::Multimodal {
        return Err(IndexError::Contract(
            "KCS-E-EMBED-MODALITY-001: embedding modality must be multimodal".to_owned(),
        ));
    }
    if dimensions != 768
        || distance != EmbeddingDistance::Cosine
        || profile_hash != adopted_embedding_profile_hash()?
    {
        return Err(IndexError::Contract(
            "KCS-E-SEARCH-VEC-INCOMPAT-001: embedding profile incompatible".to_owned(),
        ));
    }
    Ok(())
}

/// A distinct embedding profile observed in the `embeddings` table (compat check
/// input, 03 §7).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EmbeddingProfileSummary {
    pub dimensions: u64,
    pub distance: String,
    pub modality: String,
    pub profile_hash: String,
}

impl EmbeddingProfileSummary {
    /// Whether this stored profile is compatible with the adopted query profile
    /// (03 §7: dimensions / distance / modality / profile_hash all match).
    pub fn matches_adopted(&self) -> Result<bool> {
        Ok(self.dimensions == CHUNK_VEC_DIMENSIONS as u64
            && self.distance == "cosine"
            && self.modality == "multimodal"
            && self.profile_hash == adopted_embedding_profile_hash()?)
    }
}

/// The chunk-embedding profiles present in a scope's `sqlite.db` (03 §7 compat).
/// Empty means the scope has no chunk embeddings (vector search unavailable).
pub fn chunk_embedding_profiles(conn: &Connection) -> Result<Vec<EmbeddingProfileSummary>> {
    let mut stmt = conn.prepare(
        "SELECT DISTINCT dimensions, distance, modality, profile_hash
         FROM embeddings WHERE target_type = 'chunk'",
    )?;
    let rows = stmt.query_map([], |row| {
        Ok(EmbeddingProfileSummary {
            dimensions: row.get::<_, i64>(0)? as u64,
            distance: row.get(1)?,
            modality: row.get(2)?,
            profile_hash: row.get(3)?,
        })
    })?;
    let mut out = Vec::new();
    for row in rows {
        out.push(row?);
    }
    Ok(out)
}

/// Look up the stored vector BLOB for a content identity (`embedding_hash`) so an
/// unchanged chunk can reuse it without re-calling the Embedding Adapter
/// (CT3-EMBED-006, 04 §5.5). Returns the raw f32 LE bytes.
pub fn content_vector(conn: &Connection, embedding_hash: &str) -> Result<Option<Vec<u8>>> {
    let mut stmt = conn.prepare("SELECT vector FROM embeddings WHERE id = ?1")?;
    let mut rows = stmt.query(params![embedding_hash])?;
    match rows.next()? {
        Some(row) => Ok(Some(row.get(0)?)),
        None => Ok(None),
    }
}

/// Write one chunk embedding: upsert the content-addressed `embeddings` row
/// (`id = embedding_hash`, `target_id = text_hash`; idempotent so shared content
/// is stored once) and map this `chunk_id` into `chunk_vec` (04 §4.3). The
/// `embeddings` table is the source of truth; `chunk_vec` is its derived KNN copy.
#[allow(clippy::too_many_arguments)]
pub fn write_chunk_embedding(
    conn: &Connection,
    embedding_hash: &str,
    text_hash: &str,
    chunk_id: &str,
    vector: &[u8],
    dimensions: u64,
    distance: &str,
    modality: &str,
    profile_hash: &str,
) -> Result<()> {
    conn.execute(
        "INSERT INTO embeddings(id, target_type, target_id, modality, vector, dimensions, distance, profile_hash)
         VALUES (?1, 'chunk', ?2, ?3, ?4, ?5, ?6, ?7)
         ON CONFLICT(id) DO NOTHING",
        params![
            embedding_hash,
            text_hash,
            modality,
            vector,
            dimensions as i64,
            distance,
            profile_hash
        ],
    )?;
    link_chunk_vec(conn, chunk_id, vector, dimensions)?;
    Ok(())
}

/// Map a `chunk_id` to a vector in `chunk_vec` (idempotent). No-op if the vector
/// width is not the adopted `chunk_vec` dimension (incompatible-width embeddings
/// never enter the KNN table).
pub fn link_chunk_vec(
    conn: &Connection,
    chunk_id: &str,
    vector: &[u8],
    dimensions: u64,
) -> Result<()> {
    if dimensions as usize != CHUNK_VEC_DIMENSIONS || vector.len() != CHUNK_VEC_DIMENSIONS * 4 {
        return Ok(());
    }
    // vec0 virtual tables do not support UPSERT; delete-then-insert is idempotent.
    conn.execute(
        "DELETE FROM chunk_vec WHERE chunk_id = ?1",
        params![chunk_id],
    )?;
    conn.execute(
        "INSERT INTO chunk_vec(chunk_id, embedding) VALUES (?1, ?2)",
        params![chunk_id, vector],
    )?;
    Ok(())
}

/// Rebuild `chunk_vec` from `embeddings` joined to `chunks` on `text_hash`
/// (04 §4.3 rebuild order objects → embeddings → chunk_vec; `embeddings` is the
/// source of truth). Only adopted-width chunk embeddings are re-linked.
pub fn rebuild_chunk_vec(conn: &Connection) -> Result<()> {
    conn.execute_batch("DELETE FROM chunk_vec;")?;
    let mut stmt = conn.prepare(
        "SELECT c.chunk_id, e.vector, e.dimensions
         FROM chunks c
         JOIN embeddings e ON e.target_type = 'chunk' AND e.target_id = c.text_hash",
    )?;
    let rows = stmt
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, Vec<u8>>(1)?,
                row.get::<_, i64>(2)? as u64,
            ))
        })?
        .collect::<std::result::Result<Vec<_>, _>>()?;
    for (chunk_id, vector, dimensions) in rows {
        link_chunk_vec(conn, &chunk_id, &vector, dimensions)?;
    }
    Ok(())
}

/// Snapshot every chunk embedding row (content + all mapped chunk_ids) so the
/// acceleration DB can be dropped and rebuilt without losing vectors (they live
/// only in SQLite; objects/ holds no embedding objects in the MVP). Returns one
/// entry per `(chunk_id, embedding)` so `chunk_vec` reconstructs exactly.
pub struct ChunkEmbeddingSnapshotRow {
    pub embedding_hash: String,
    pub text_hash: String,
    pub chunk_id: String,
    pub vector: Vec<u8>,
    pub dimensions: u64,
    pub distance: String,
    pub modality: String,
    pub profile_hash: String,
}

pub fn snapshot_chunk_embeddings(conn: &Connection) -> Result<Vec<ChunkEmbeddingSnapshotRow>> {
    // The `chunks` table may not exist on a corrupt DB; tolerate its absence.
    let has_chunks: bool = conn
        .query_row(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='chunks'",
            [],
            |row| row.get::<_, i64>(0),
        )
        .map(|count| count > 0)
        .unwrap_or(false);
    if !has_chunks {
        return Ok(Vec::new());
    }
    let mut stmt = conn.prepare(
        "SELECT e.id, e.target_id, c.chunk_id, e.vector, e.dimensions, e.distance, e.modality, e.profile_hash
         FROM embeddings e
         JOIN chunks c ON e.target_type = 'chunk' AND c.text_hash = e.target_id",
    )?;
    let rows = stmt.query_map([], |row| {
        Ok(ChunkEmbeddingSnapshotRow {
            embedding_hash: row.get(0)?,
            text_hash: row.get(1)?,
            chunk_id: row.get(2)?,
            vector: row.get(3)?,
            dimensions: row.get::<_, i64>(4)? as u64,
            distance: row.get(5)?,
            modality: row.get(6)?,
            profile_hash: row.get(7)?,
        })
    })?;
    let mut out = Vec::new();
    for row in rows {
        out.push(row?);
    }
    Ok(out)
}

/// KNN over `chunk_vec`: the nearest `k` chunk_ids to `query_vector` ordered by
/// cosine distance (04 §4.3). Ties are re-broken by `chunk_id` ascending by the
/// caller. `query_vector` is raw f32 LE bytes of the adopted dimension.
pub fn knn_chunk_distances(
    conn: &Connection,
    query_vector: &[u8],
    k: u64,
) -> Result<Vec<(String, f64)>> {
    if query_vector.len() != CHUNK_VEC_DIMENSIONS * 4 {
        return Err(IndexError::Contract(
            "KCS-E-SEARCH-VEC-INCOMPAT-001: query vector width mismatch".to_owned(),
        ));
    }
    let mut stmt = conn.prepare(
        "SELECT chunk_id, distance FROM chunk_vec
         WHERE embedding MATCH ?1 ORDER BY distance LIMIT ?2",
    )?;
    let rows = stmt.query_map(params![query_vector, k as i64], |row| {
        Ok((row.get::<_, String>(0)?, row.get::<_, f64>(1)?))
    })?;
    let mut out = Vec::new();
    for row in rows {
        out.push(row?);
    }
    Ok(out)
}

/// Number of `chunk_vec` rows (used to size the KNN over-fetch, and as vector
/// coverage evidence).
pub fn chunk_vec_count(conn: &Connection) -> Result<u64> {
    Ok(conn.query_row("SELECT COUNT(*) FROM chunk_vec", [], |row| {
        row.get::<_, i64>(0)
    })? as u64)
}

/// Read one chunk's stored vector as f32 for the MMR cosine similarity (05 §1.4).
pub fn read_chunk_vector(conn: &Connection, chunk_id: &str) -> Result<Option<Vec<f32>>> {
    let mut stmt = conn.prepare("SELECT embedding FROM chunk_vec WHERE chunk_id = ?1")?;
    let mut rows = stmt.query(params![chunk_id])?;
    match rows.next()? {
        Some(row) => {
            let bytes: Vec<u8> = row.get(0)?;
            Ok(Some(f32_from_le_bytes(&bytes)))
        }
        None => Ok(None),
    }
}

/// Decode a raw little-endian f32 BLOB into a vector.
pub fn f32_from_le_bytes(bytes: &[u8]) -> Vec<f32> {
    bytes
        .chunks_exact(4)
        .map(|chunk| f32::from_le_bytes([chunk[0], chunk[1], chunk[2], chunk[3]]))
        .collect()
}

/// Encode an f32 vector to a raw little-endian BLOB for `embeddings.vector` /
/// `chunk_vec.embedding`.
pub fn f32_to_le_bytes(vector: &[f32]) -> Vec<u8> {
    vector
        .iter()
        .flat_map(|value| value.to_le_bytes())
        .collect()
}

fn target_type_name(value: EmbeddingTargetType) -> &'static str {
    match value {
        EmbeddingTargetType::Chunk => "chunk",
        EmbeddingTargetType::Image => "image",
        EmbeddingTargetType::Node => "node",
        EmbeddingTargetType::QueryCache => "query_cache",
    }
}

fn distance_name(value: EmbeddingDistance) -> &'static str {
    match value {
        EmbeddingDistance::Cosine => "cosine",
        EmbeddingDistance::L2 => "l2",
        EmbeddingDistance::InnerProduct => "inner_product",
    }
}

fn modality_name(value: EmbeddingModality) -> &'static str {
    match value {
        EmbeddingModality::Text => "text",
        EmbeddingModality::Image => "image",
        EmbeddingModality::Multimodal => "multimodal",
    }
}

fn hash_jcs(value: &Value) -> Result<String> {
    serde_jcs::to_vec(value)
        .map(|bytes| hash_bytes(&bytes))
        .map_err(|err| IndexError::Schema(err.to_string()))
}

fn hash_bytes(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    format!("sha256:{}", lower_hex(&digest))
}

fn lower_hex(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        out.push(HEX[(byte >> 4) as usize] as char);
        out.push(HEX[(byte & 0x0f) as usize] as char);
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ct3_embed_001_embedding_profile_and_hash_vector() {
        let profile_hash = adopted_embedding_profile_hash().unwrap();
        assert_eq!(
            profile_hash,
            "sha256:66aff638f38a099ff989ca97675ebd3c573a40ee53cc1cdfe05fb06102d2bb09"
        );
        assert_eq!(
            embedding_hash(
                EmbeddingTargetType::Chunk,
                "sha256:c5e31f10da04b722769bdbbd60a55b94c177b5f3bf9c64e5341be7281d115c3d",
                768,
                EmbeddingDistance::Cosine,
                EmbeddingModality::Multimodal,
                &profile_hash,
            )
            .unwrap(),
            "sha256:7bd32d26ad2b721e32c99536513abf58c6aeee626d1edc65e30069abce01a975"
        );
    }

    #[test]
    fn ct3_embed_004_adopted_profile_is_multimodal_768_cosine() {
        let profile_hash = adopted_embedding_profile_hash().unwrap();
        validate_embedding_profile(
            768,
            EmbeddingDistance::Cosine,
            EmbeddingModality::Multimodal,
            &profile_hash,
        )
        .unwrap();
    }

    #[test]
    fn ct3_embed_008_non_multimodal_profile_is_rejected() {
        let err = validate_embedding_profile(
            768,
            EmbeddingDistance::Cosine,
            EmbeddingModality::Text,
            "sha256:66aff638f38a099ff989ca97675ebd3c573a40ee53cc1cdfe05fb06102d2bb09",
        )
        .unwrap_err();
        assert!(err.to_string().contains("KCS-E-EMBED-MODALITY-001"));
    }

    use crate::fts::{
        FtsIndex, FtsSchemaConfig, FtsTokenizer, SqliteFtsIndex, CHUNK_VEC_DIMENSIONS,
    };
    use crate::ChunkRow;
    use rusqlite::Connection;

    fn schema_conn() -> SqliteFtsIndex {
        SqliteFtsIndex::in_memory(FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        })
        .unwrap()
    }

    fn chunk_row(chunk_id: &str, text_hash: &str) -> ChunkRow {
        ChunkRow {
            chunk_id: chunk_id.to_owned(),
            raw_hash: "sha256:raw".to_owned(),
            tool_profile_hash: "sha256:tool".to_owned(),
            gen: 0,
            unit_key: "page:1".to_owned(),
            chunking_config_hash: "sha256:cfg".to_owned(),
            raw_path: "a.md".to_owned(),
            heading_path: None,
            section_id: None,
            char_start: None,
            char_end: None,
            text_hash: text_hash.to_owned(),
            text: "body".to_owned(),
            first_seen_commit: None,
            created_at: "2026-07-04T00:00:00Z".to_owned(),
        }
    }

    /// Basis vector e_i as a 768-dim L2-normalized f32 BLOB.
    fn basis_vector(axis: usize) -> Vec<u8> {
        let mut v = vec![0f32; CHUNK_VEC_DIMENSIONS];
        v[axis] = 1.0;
        f32_to_le_bytes(&v)
    }

    fn write_basis(conn: &Connection, chunk_id: &str, text_hash: &str, axis: usize) {
        write_chunk_embedding(
            conn,
            &format!("sha256:emb-{text_hash}"),
            text_hash,
            chunk_id,
            &basis_vector(axis),
            CHUNK_VEC_DIMENSIONS as u64,
            "cosine",
            "multimodal",
            &adopted_embedding_profile_hash().unwrap(),
        )
        .unwrap();
    }

    #[test]
    fn write_read_and_knn_orders_by_distance() {
        let store = schema_conn();
        let conn = store.connection();
        write_basis(conn, "c-axis0", "sha256:t0", 0);
        write_basis(conn, "c-axis1", "sha256:t1", 1);
        assert_eq!(chunk_vec_count(conn).unwrap(), 2);

        // Query along axis 0: c-axis0 is nearest.
        let knn = knn_chunk_distances(conn, &basis_vector(0), 10).unwrap();
        assert_eq!(knn[0].0, "c-axis0");
        assert!(knn[0].1 <= knn[1].1);

        // MMR read round-trips the stored vector.
        let read = read_chunk_vector(conn, "c-axis0").unwrap().unwrap();
        assert_eq!(read.len(), CHUNK_VEC_DIMENSIONS);
        assert_eq!(read[0], 1.0);
    }

    #[test]
    fn knn_tie_break_is_chunk_id_ascending() {
        // Two chunks with the identical vector produce identical distance; the KNN
        // caller re-breaks ties by chunk_id ascending, so the raw rows just need to
        // both be returned (order among equal distances is then deterministic once
        // re-sorted by (distance, chunk_id)).
        let store = schema_conn();
        let conn = store.connection();
        write_basis(conn, "c-zzz", "sha256:tz", 0);
        write_basis(conn, "c-aaa", "sha256:ta", 0);
        let mut knn = knn_chunk_distances(conn, &basis_vector(0), 10).unwrap();
        knn.sort_by(|a, b| a.1.total_cmp(&b.1).then_with(|| a.0.cmp(&b.0)));
        assert_eq!(knn[0].0, "c-aaa");
        assert_eq!(knn[1].0, "c-zzz");
        assert!((knn[0].1 - knn[1].1).abs() < 1e-9);
    }

    #[test]
    fn ct3_embed_005_rebuild_chunk_vec_from_embeddings() {
        let mut store = schema_conn();
        // chunks feed chunk_vec on rebuild via the text_hash join.
        store.index_chunk(&chunk_row("c1", "sha256:t0")).unwrap();
        store.index_chunk(&chunk_row("c2", "sha256:t1")).unwrap();
        let conn = store.connection();
        write_basis(conn, "c1", "sha256:t0", 0);
        write_basis(conn, "c2", "sha256:t1", 1);

        // Drop the derived table, then rebuild it from embeddings (source of truth).
        conn.execute_batch("DELETE FROM chunk_vec;").unwrap();
        assert_eq!(chunk_vec_count(conn).unwrap(), 0);
        rebuild_chunk_vec(conn).unwrap();
        assert_eq!(chunk_vec_count(conn).unwrap(), 2);
        let knn = knn_chunk_distances(conn, &basis_vector(1), 10).unwrap();
        assert_eq!(knn[0].0, "c2");
    }
}
