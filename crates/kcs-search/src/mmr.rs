//! MMR and dedup diversification contracts.

use serde::{Deserialize, Serialize};

use crate::query::DiversifyStrategy;
use crate::Result;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct MmrConfig {
    pub strategy: DiversifyStrategy,
    pub mmr_lambda: f64,
    pub max_per_raw_hash: u64,
    pub mmr_depth: u64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct MmrCandidate {
    pub chunk_hash: String,
    pub raw_hash: String,
    /// RRF スコアの候補プール内 min-max 正規化値 (05 §1.4)
    pub relevance: f64,
    /// similarity は embedding の cosine のみ (05 §1.4)。None (text-only) の候補が
    /// 含まれる場合、呼び出し側は MMR を適用しない
    pub embedding: Option<Vec<f32>>,
    pub heading_path: Option<Vec<String>>,
    pub section_id: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DiversifiedCandidate {
    pub chunk_hash: String,
    pub final_rank: u64,
}

pub trait Diversifier {
    fn diversify(
        &self,
        candidates: &[MmrCandidate],
        config: MmrConfig,
    ) -> Result<Vec<DiversifiedCandidate>>;
}

pub fn diversify_candidates(
    _candidates: &[MmrCandidate],
    _config: MmrConfig,
) -> Result<Vec<DiversifiedCandidate>> {
    todo!("Step 3c will implement MMR and raw-hash dedup")
}
