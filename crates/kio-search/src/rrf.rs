//! Reciprocal Rank Fusion contracts.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use crate::Result;

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct RrfConfig {
    pub k: u64,
    pub w_text: f64,
    pub w_vector: f64,
    pub candidate_depth: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct BackendRank {
    pub chunk_hash: String,
    pub rank: u64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct FusedCandidate {
    pub chunk_hash: String,
    pub rrf_score: f64,
    pub text_rank: Option<u64>,
    pub vector_rank: Option<u64>,
}

pub fn fuse_rrf(
    text_ranks: &[BackendRank],
    vector_ranks: &[BackendRank],
    config: RrfConfig,
) -> Result<Vec<FusedCandidate>> {
    let mut by_chunk = BTreeMap::<String, FusedCandidate>::new();
    for rank in text_ranks.iter().take(config.candidate_depth as usize) {
        let entry = by_chunk
            .entry(rank.chunk_hash.clone())
            .or_insert_with(|| FusedCandidate {
                chunk_hash: rank.chunk_hash.clone(),
                rrf_score: 0.0,
                text_rank: None,
                vector_rank: None,
            });
        entry.text_rank = Some(rank.rank);
    }
    for rank in vector_ranks.iter().take(config.candidate_depth as usize) {
        let entry = by_chunk
            .entry(rank.chunk_hash.clone())
            .or_insert_with(|| FusedCandidate {
                chunk_hash: rank.chunk_hash.clone(),
                rrf_score: 0.0,
                text_rank: None,
                vector_rank: None,
            });
        entry.vector_rank = Some(rank.rank);
    }
    let mut fused = by_chunk.into_values().collect::<Vec<_>>();
    for candidate in &mut fused {
        candidate.rrf_score = candidate
            .text_rank
            .map(|rank| config.w_text / (config.k + rank) as f64)
            .unwrap_or(0.0)
            + candidate
                .vector_rank
                .map(|rank| config.w_vector / (config.k + rank) as f64)
                .unwrap_or(0.0);
    }
    fused.sort_by(|a, b| {
        b.rrf_score
            .total_cmp(&a.rrf_score)
            .then_with(|| a.chunk_hash.cmp(&b.chunk_hash))
    });
    Ok(fused)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ct3_hybrid_004_rrf_score_and_rank_vector() {
        let text = ["c1", "c2", "c3", "c4"]
            .into_iter()
            .enumerate()
            .map(|(i, chunk)| BackendRank {
                chunk_hash: chunk.to_owned(),
                rank: i as u64 + 1,
            })
            .collect::<Vec<_>>();
        let vector = ["c2", "c3", "c1", "c5"]
            .into_iter()
            .enumerate()
            .map(|(i, chunk)| BackendRank {
                chunk_hash: chunk.to_owned(),
                rank: i as u64 + 1,
            })
            .collect::<Vec<_>>();
        let fused = fuse_rrf(
            &text,
            &vector,
            RrfConfig {
                k: 60,
                w_text: 1.0,
                w_vector: 1.0,
                candidate_depth: 200,
            },
        )
        .unwrap();
        assert_eq!(
            fused
                .iter()
                .map(|c| c.chunk_hash.as_str())
                .collect::<Vec<_>>(),
            vec!["c2", "c1", "c3", "c4", "c5"]
        );
        assert!((fused[0].rrf_score - 123.0 / 3782.0).abs() < 1e-12);
    }

    #[test]
    fn r12_1_rrf_weights_change_order() {
        // Same inputs as ct3_hybrid_004, but weighting the vector backend only
        // (w_text=0) yields the vector order, not the balanced fusion order — proof
        // the `[search.rrf]` weights are honored (were hardcoded before R12-1).
        let text = ["c1", "c2", "c3", "c4"]
            .into_iter()
            .enumerate()
            .map(|(i, chunk)| BackendRank {
                chunk_hash: chunk.to_owned(),
                rank: i as u64 + 1,
            })
            .collect::<Vec<_>>();
        let vector = ["c2", "c3", "c1", "c5"]
            .into_iter()
            .enumerate()
            .map(|(i, chunk)| BackendRank {
                chunk_hash: chunk.to_owned(),
                rank: i as u64 + 1,
            })
            .collect::<Vec<_>>();
        let fused = fuse_rrf(
            &text,
            &vector,
            RrfConfig {
                k: 60,
                w_text: 0.0,
                w_vector: 1.0,
                candidate_depth: 200,
            },
        )
        .unwrap();
        assert_eq!(
            fused
                .iter()
                .map(|c| c.chunk_hash.as_str())
                .collect::<Vec<_>>(),
            vec!["c2", "c3", "c1", "c5", "c4"]
        );
    }

    #[test]
    fn ct3_hybrid_005_rrf_tie_breaks_by_chunk_id() {
        let fused = fuse_rrf(
            &[BackendRank {
                chunk_hash: "c5".to_owned(),
                rank: 1,
            }],
            &[BackendRank {
                chunk_hash: "c4".to_owned(),
                rank: 1,
            }],
            RrfConfig {
                k: 60,
                w_text: 1.0,
                w_vector: 1.0,
                candidate_depth: 200,
            },
        )
        .unwrap();
        assert_eq!(fused[0].chunk_hash, "c4");
    }
}
