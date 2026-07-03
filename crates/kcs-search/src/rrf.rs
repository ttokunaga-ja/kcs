//! Reciprocal Rank Fusion contracts.

use serde::{Deserialize, Serialize};

use crate::Result;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
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

pub trait RrfScorer {
    fn fuse(
        &self,
        text_ranks: &[BackendRank],
        vector_ranks: &[BackendRank],
        config: RrfConfig,
    ) -> Result<Vec<FusedCandidate>>;
}

pub fn fuse_rrf(
    _text_ranks: &[BackendRank],
    _vector_ranks: &[BackendRank],
    _config: RrfConfig,
) -> Result<Vec<FusedCandidate>> {
    todo!("Step 3c will implement RRF scoring")
}
