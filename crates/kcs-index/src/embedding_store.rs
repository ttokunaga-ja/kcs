//! Embedding metadata and chunk_vec store contracts.

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

use crate::{
    EmbeddingDistance, EmbeddingModality, EmbeddingRow, EmbeddingTargetType, IndexError, Result,
};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct EmbeddingLookup {
    pub target_type: EmbeddingTargetType,
    pub target_id: String,
    pub profile_hash: String,
}

pub trait EmbeddingStore {
    fn upsert_embedding(&mut self, row: EmbeddingRow) -> Result<()>;

    fn get_embedding(&self, lookup: EmbeddingLookup) -> Result<Option<EmbeddingRow>>;

    fn rebuild_chunk_vec(&mut self) -> Result<()>;
}

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

pub fn rebuild_chunk_vec_from_embeddings(store: &mut dyn EmbeddingStore) -> Result<()> {
    store.rebuild_chunk_vec()
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
}
