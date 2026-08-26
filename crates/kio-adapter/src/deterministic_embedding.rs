//! Deterministic evaluator-only embedding adapter.
//!
//! This is deliberately a real [`EmbeddingAdapter`] implementation rather than
//! a database fixture: both indexing and query embedding traverse the same
//! adapter boundary as every other embedding backend.  It is selected only by
//! the exact evaluator activation handled by the catalog.

use serde_json::json;
use sha2::{Digest, Sha256};

use crate::Result;
use crate::identity::tool_profile_hash;
use crate::local_embedding::IMAGE_OBJECT_CAPABILITY;
use crate::traits::EmbeddingAdapter;
use crate::types::{
    AdapterKind, AdapterProfile, BillingDeclaration, EmbeddingRequest, EmbeddingResponse,
    EmbeddingVector, ExecutionMode, ProviderIdempotency, validate_cosine_vector,
};

pub const DETERMINISTIC_EVAL_EMBEDDING_ADAPTER_ID: &str = "kio_eval_deterministic_embedding";
pub const DETERMINISTIC_EVAL_EMBEDDING_PROFILE: &str = "scale-v3";
pub const DETERMINISTIC_EVAL_EMBEDDING_DIMENSIONS: u32 = 768;
const DETERMINISTIC_EVAL_EMBEDDING_MODEL_VERSION: &str =
    "scale-v3-token-hash4-first-hex12-anchor64-weight16-v1";
const REFERENCE_ANCHOR_DOMAIN: &[u8] = b"kio-eval-reference-anchor-v1\0";
const REFERENCE_ANCHOR_FEATURES: u32 = 64;
const REFERENCE_ANCHOR_WEIGHT: f32 = 16.0;

#[derive(Debug, Clone, Copy, Default)]
pub struct DeterministicEmbeddingAdapter;

/// Byte-stable feature hashing for the evaluator corpus.
///
/// A full-input pseudorandom vector is deterministic but cannot retrieve an
/// exact query term from the chunk containing it. Each lower-case ASCII
/// alphanumeric token instead contributes signed, deterministic features. The
/// first 12-digit hexadecimal reference token additionally receives one
/// domain-separated anchor: scale-v3 queries are that opaque token, and the
/// matching section contains it before its other references. Anchoring only
/// the first reference avoids diluting the signal across every reference in a
/// long chunk.
#[must_use]
pub fn deterministic_token_embedding(input: &str) -> Vec<f32> {
    let tokens = input
        .split(|byte: char| !byte.is_ascii_alphanumeric())
        .filter(|token| !token.is_empty())
        .map(str::to_ascii_lowercase)
        .collect::<Vec<_>>();
    let mut vector = vec![0.0_f32; DETERMINISTIC_EVAL_EMBEDDING_DIMENSIONS as usize];
    if tokens.is_empty() {
        add_token_features(&mut vector, input.as_bytes());
    } else {
        let anchor = tokens.iter().position(|token| is_reference_anchor(token));
        for (index, token) in tokens.into_iter().enumerate() {
            add_token_features(&mut vector, token.as_bytes());
            if anchor == Some(index) {
                add_reference_anchor_features(&mut vector, token.as_bytes());
            }
        }
    }
    normalize(&mut vector);
    vector
}

fn is_reference_anchor(token: &str) -> bool {
    token.len() == 12
        && token
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn add_reference_anchor_features(vector: &mut [f32], token: &[u8]) {
    for feature in 0..REFERENCE_ANCHOR_FEATURES {
        let mut hasher = Sha256::new();
        hasher.update(REFERENCE_ANCHOR_DOMAIN);
        hasher.update(token);
        hasher.update(feature.to_le_bytes());
        let digest = hasher.finalize();
        let bucket = u16::from_le_bytes([digest[0], digest[1]]) as usize % vector.len();
        let sign = if digest[2] & 1 == 0 { 1.0 } else { -1.0 };
        vector[bucket] += sign * REFERENCE_ANCHOR_WEIGHT;
    }
}

fn add_token_features(vector: &mut [f32], token: &[u8]) {
    // Four independent signed features per token retain an inspectable wire
    // contract while keeping collisions low in the bounded evaluator corpus.
    for feature in 0_u32..4 {
        let mut hasher = Sha256::new();
        hasher.update(token);
        hasher.update(feature.to_le_bytes());
        let digest = hasher.finalize();
        let bucket = u16::from_le_bytes([digest[0], digest[1]]) as usize % vector.len();
        let sign = if digest[2] & 1 == 0 { 1.0 } else { -1.0 };
        vector[bucket] += sign;
    }
}

fn normalize(vector: &mut [f32]) {
    let norm = vector.iter().map(|value| value * value).sum::<f32>().sqrt();
    debug_assert!(norm.is_finite() && norm > 0.0);
    for value in vector {
        *value /= norm;
    }
}

impl DeterministicEmbeddingAdapter {
    #[must_use]
    pub fn profile_value() -> serde_json::Value {
        json!({
            "adapter_kind": "embedding",
            "adapter_role": "text",
            "dimensions": DETERMINISTIC_EVAL_EMBEDDING_DIMENSIONS,
            "distance": "cosine",
            "input_construction": "chunk_filename_context_v1",
            "modality": "multimodal",
            "model_or_tool_family": "kio-eval-deterministic-embedding",
            "model_version_pin": DETERMINISTIC_EVAL_EMBEDDING_MODEL_VERSION,
            "runtime_kind": "deterministic_library",
            "spec_version": 1
        })
    }
}

impl EmbeddingAdapter for DeterministicEmbeddingAdapter {
    fn profile(&self) -> AdapterProfile {
        AdapterProfile {
            adapter_kind: AdapterKind::Embedding,
            adapter_id: DETERMINISTIC_EVAL_EMBEDDING_ADAPTER_ID.to_owned(),
            execution_mode: ExecutionMode::DeterministicLibrary,
            tool_profile_hash: tool_profile_hash(&Self::profile_value())
                .expect("deterministic evaluator embedding profile is valid"),
            version: env!("CARGO_PKG_VERSION").to_owned(),
            capability_flags: vec!["text".to_owned(), IMAGE_OBJECT_CAPABILITY.to_owned()],
            allow_network: false,
            billable_kinds: Vec::new(),
            reject_billing: Some(BillingDeclaration::Nonbillable),
            provider_idempotency: ProviderIdempotency::NotProvided,
        }
    }

    fn embed(&self, request: EmbeddingRequest) -> Result<EmbeddingResponse> {
        let vectors = request
            .items
            .iter()
            .map(|item| {
                let seed = item.text.as_deref().unwrap_or(item.id.as_str());
                let vector = deterministic_token_embedding(seed);
                validate_cosine_vector(&vector, DETERMINISTIC_EVAL_EMBEDDING_DIMENSIONS)?;
                Ok(EmbeddingVector {
                    id: item.id.clone(),
                    vector,
                })
            })
            .collect::<Result<Vec<_>>>()?;
        Ok(EmbeddingResponse {
            vectors,
            dimensions: DETERMINISTIC_EVAL_EMBEDDING_DIMENSIONS,
            distance: "cosine".to_owned(),
            modality: "multimodal".to_owned(),
            embedding_profile_hash: Some(self.profile().tool_profile_hash),
            usage: None,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::{EmbeddingInputType, EmbeddingItem};

    #[test]
    fn profile_is_non_network_non_billable_deterministic_library() {
        let profile = DeterministicEmbeddingAdapter.profile();
        assert_eq!(profile.execution_mode, ExecutionMode::DeterministicLibrary);
        assert!(!profile.allow_network);
        assert!(profile.billable_kinds.is_empty());
        assert_eq!(
            profile.reject_billing,
            Some(BillingDeclaration::Nonbillable)
        );
        assert_eq!(
            profile.tool_profile_hash,
            "sha256:2b5ed5b97d35496e611ccd22589c80fe6da7333bc2e7061b85eca910a1d5c497"
        );
    }

    #[test]
    fn embedding_is_stable_distinct_and_normalized() {
        let request = EmbeddingRequest {
            input_type: EmbeddingInputType::MarkdownChunk,
            items: vec![
                EmbeddingItem {
                    id: "a".to_owned(),
                    text: Some("alpha".to_owned()),
                    path: None,
                    mime: None,
                },
                EmbeddingItem {
                    id: "b".to_owned(),
                    text: Some("beta".to_owned()),
                    path: None,
                    mime: None,
                },
            ],
            idempotency_token: None,
        };
        let adapter = DeterministicEmbeddingAdapter;
        let first = adapter.embed(request.clone()).unwrap();
        let second = adapter.embed(request).unwrap();
        assert_eq!(first.vectors, second.vectors);
        assert_ne!(first.vectors[0].vector, first.vectors[1].vector);
        for vector in first.vectors {
            validate_cosine_vector(&vector.vector, DETERMINISTIC_EVAL_EMBEDDING_DIMENSIONS)
                .unwrap();
        }
    }

    #[test]
    fn exact_query_token_scores_above_unrelated_text() {
        let query = deterministic_token_embedding("needle");
        let containing = deterministic_token_embedding("ordinary context needle more context");
        let unrelated = deterministic_token_embedding("ordinary context haystack more context");
        let cosine = |left: &[f32], right: &[f32]| {
            left.iter()
                .zip(right)
                .map(|(left, right)| left * right)
                .sum::<f32>()
        };
        assert!(cosine(&query, &containing) > cosine(&query, &unrelated));
    }

    #[test]
    fn first_reference_anchor_ranks_first_across_full_candidate_count() {
        let wanted = "ffffffffffff";
        let query = deterministic_token_embedding(wanted);
        let common = (0..80)
            .map(|index| format!("ordinary context word{index}"))
            .collect::<Vec<_>>()
            .join(" ");
        let common = format!("document 0000 {common} aaaaaaaaaaaa bbbbbbbbbbbb");
        let target = deterministic_token_embedding(&format!("{wanted} {common}"));
        let cosine = |left: &[f32], right: &[f32]| {
            left.iter()
                .zip(right)
                .map(|(left, right)| left * right)
                .sum::<f32>()
        };
        let target_score = cosine(&query, &target);
        let mut common_vector = vec![0.0_f32; DETERMINISTIC_EVAL_EMBEDDING_DIMENSIONS as usize];
        for token in common
            .split(|byte: char| !byte.is_ascii_alphanumeric())
            .filter(|token| !token.is_empty())
        {
            add_token_features(&mut common_vector, token.as_bytes());
        }
        let mut best_unrelated = f32::NEG_INFINITY;
        for index in 0..120_000_u32 {
            let candidate = format!("{index:012x}");
            let mut embedding = common_vector.clone();
            add_token_features(&mut embedding, candidate.as_bytes());
            add_reference_anchor_features(&mut embedding, candidate.as_bytes());
            normalize(&mut embedding);
            best_unrelated = best_unrelated.max(cosine(&query, &embedding));
        }
        assert!(target_score > best_unrelated);
    }

    #[test]
    fn only_the_first_exact_reference_token_is_anchored() {
        assert!(is_reference_anchor("012345abcdef"));
        assert!(!is_reference_anchor("012345abcdeg"));
        assert!(!is_reference_anchor("012345abcdef0"));

        let first = deterministic_token_embedding("012345abcdef");
        let second = deterministic_token_embedding("fedcba543210");
        let both = deterministic_token_embedding("012345abcdef context fedcba543210");
        let cosine = |left: &[f32], right: &[f32]| {
            left.iter()
                .zip(right)
                .map(|(left, right)| left * right)
                .sum::<f32>()
        };
        assert!(cosine(&first, &both) > cosine(&second, &both));
    }
}
