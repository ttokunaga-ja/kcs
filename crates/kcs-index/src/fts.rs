//! FTS5 external-content index contracts.

use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};

use crate::{ChunkRow, Result};

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

pub trait FtsIndex {
    fn ensure_schema(&mut self, config: FtsSchemaConfig) -> Result<()>;

    fn index_chunk(&mut self, row: &ChunkRow) -> Result<()>;

    fn delete_chunk(&mut self, chunk_id: &str) -> Result<()>;

    fn search(&self, query: &str, limit: u64) -> Result<Vec<FtsMatch>>;
}

pub struct SqliteFtsIndex {
    conn: Connection,
}

impl SqliteFtsIndex {
    pub fn open(path: impl AsRef<std::path::Path>, config: FtsSchemaConfig) -> Result<Self> {
        let conn = Connection::open(path)?;
        ensure_schema_on_connection(&conn, config)?;
        Ok(Self { conn })
    }

    pub fn in_memory(config: FtsSchemaConfig) -> Result<Self> {
        let conn = Connection::open_in_memory()?;
        ensure_schema_on_connection(&conn, config)?;
        Ok(Self { conn })
    }

    #[must_use]
    pub fn connection(&self) -> &Connection {
        &self.conn
    }
}

impl FtsIndex for SqliteFtsIndex {
    fn ensure_schema(&mut self, config: FtsSchemaConfig) -> Result<()> {
        ensure_schema_on_connection(&self.conn, config)
    }

    fn index_chunk(&mut self, row: &ChunkRow) -> Result<()> {
        self.conn.execute(
            "INSERT OR IGNORE INTO chunks(
                chunk_id, raw_hash, tool_profile_hash, gen, unit_key,
                chunking_config_hash, raw_path, heading_path, section_id,
                char_start, char_end, text_hash, text, first_seen_commit, created_at
            ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15)",
            params![
                row.chunk_id,
                row.raw_hash,
                row.tool_profile_hash,
                row.gen,
                row.unit_key,
                row.chunking_config_hash,
                row.raw_path,
                serde_json::to_string(&row.heading_path.clone().unwrap_or_default())?,
                row.section_id,
                row.char_start,
                row.char_end,
                row.text_hash,
                row.text,
                row.first_seen_commit,
                row.created_at,
            ],
        )?;
        Ok(())
    }

    fn delete_chunk(&mut self, chunk_id: &str) -> Result<()> {
        self.conn
            .execute("DELETE FROM chunks WHERE chunk_id = ?1", params![chunk_id])?;
        Ok(())
    }

    fn search(&self, query: &str, limit: u64) -> Result<Vec<FtsMatch>> {
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

pub fn ensure_fts_external_content_schema(config: FtsSchemaConfig) -> Result<()> {
    let conn = Connection::open_in_memory()?;
    ensure_schema_on_connection(&conn, config)
}

pub fn ensure_schema_on_connection(conn: &Connection, config: FtsSchemaConfig) -> Result<()> {
    conn.execute_batch(
        r#"
        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id TEXT PRIMARY KEY,
            raw_hash TEXT NOT NULL,
            tool_profile_hash TEXT NOT NULL,
            gen INTEGER NOT NULL,
            unit_key TEXT NOT NULL,
            chunking_config_hash TEXT NOT NULL,
            raw_path TEXT NOT NULL,
            heading_path TEXT NOT NULL,
            section_id TEXT,
            char_start INTEGER,
            char_end INTEGER,
            text_hash TEXT NOT NULL,
            text TEXT NOT NULL,
            first_seen_commit TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS embeddings (
            id TEXT PRIMARY KEY,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            modality TEXT NOT NULL,
            vector BLOB NOT NULL,
            dimensions INTEGER NOT NULL,
            distance TEXT NOT NULL,
            profile_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS chunk_vec (
            embedding_id TEXT PRIMARY KEY,
            chunk_id TEXT NOT NULL,
            vector BLOB NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tree_entries (
            commit_hash TEXT NOT NULL,
            path TEXT NOT NULL,
            raw_hash TEXT NOT NULL,
            tool_profile_hash TEXT,
            gen INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (commit_hash, path)
        );
        "#,
    )?;

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
    Ok(())
}

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
            char_start: Some(0),
            char_end: Some(text.chars().count() as u64),
            text_hash: "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
                .to_owned(),
            text: text.to_owned(),
            first_seen_commit: None,
            created_at: "2026-07-03T00:00:00Z".to_owned(),
        }
    }

    #[test]
    fn ct3_fts_001_external_content_triggers_sync_insert_delete() {
        let mut fts = SqliteFtsIndex::in_memory(FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        })
        .unwrap();
        fts.index_chunk(&row("c1", "認証仕様の更新")).unwrap();
        assert_eq!(fts.search("認証仕様", 10).unwrap()[0].chunk_id, "c1");
        fts.delete_chunk("c1").unwrap();
        assert!(fts.search("認証仕様", 10).unwrap().is_empty());
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
        ensure_fts_external_content_schema(FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        })
        .unwrap();
    }
}
