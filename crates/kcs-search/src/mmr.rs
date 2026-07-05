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
    /// RRF スコア。MMR 適用時に候補プール内 min-max 正規化する (05 §1.4)
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
    candidates: &[MmrCandidate],
    config: MmrConfig,
) -> Result<Vec<DiversifiedCandidate>> {
    let ordered = match config.strategy {
        // R12-1: "off" disables diversification ENTIRELY — no MMR reorder AND no
        // `max_per_raw_hash` dedup. It must be a true no-op so the documented escape
        // hatch (05 §1.4) lets every candidate through; the diversify summary already
        // reports "off", so deduping here contradicted the report. "group_by_raw_hash"
        // and "mmr" are the two strategies that apply the dedup cap.
        DiversifyStrategy::Off => {
            return Ok(candidates
                .iter()
                .enumerate()
                .map(|(index, candidate)| DiversifiedCandidate {
                    chunk_hash: candidate.chunk_hash.clone(),
                    final_rank: index as u64 + 1,
                })
                .collect());
        }
        DiversifyStrategy::GroupByRawHash => candidates.iter().collect::<Vec<_>>(),
        DiversifyStrategy::Mmr => {
            if candidates
                .iter()
                .any(|candidate| candidate.embedding.is_none())
            {
                candidates.iter().collect::<Vec<_>>()
            } else {
                mmr_order(candidates, config.mmr_lambda, config.mmr_depth as usize)
            }
        }
    };
    Ok(apply_max_per_raw_hash(&ordered, config.max_per_raw_hash))
}

fn mmr_order(candidates: &[MmrCandidate], lambda: f64, mmr_depth: usize) -> Vec<&MmrCandidate> {
    let depth = mmr_depth.min(candidates.len());
    let (pool, tail) = candidates.split_at(depth);
    if pool.is_empty() {
        return Vec::new();
    }
    let min = pool
        .iter()
        .map(|candidate| candidate.relevance)
        .fold(f64::INFINITY, f64::min);
    let max = pool
        .iter()
        .map(|candidate| candidate.relevance)
        .fold(f64::NEG_INFINITY, f64::max);
    let range = max - min;
    let relevance = pool
        .iter()
        .map(|candidate| {
            if range.abs() < f64::EPSILON {
                1.0
            } else {
                (candidate.relevance - min) / range
            }
        })
        .collect::<Vec<_>>();

    let mut selected = Vec::<usize>::new();
    let mut remaining = (0..pool.len()).collect::<Vec<_>>();
    while !remaining.is_empty() {
        let mut best = remaining[0];
        let mut best_score = f64::NEG_INFINITY;
        for &index in &remaining {
            let diversity_penalty = selected
                .iter()
                .map(|&selected_index| {
                    cosine(
                        pool[index].embedding.as_ref().unwrap(),
                        pool[selected_index].embedding.as_ref().unwrap(),
                    )
                })
                .fold(0.0, f64::max);
            let score = lambda * relevance[index] - (1.0 - lambda) * diversity_penalty;
            let better = score > best_score
                || ((score - best_score).abs() < 1e-12
                    && (index < best
                        || (index == best && pool[index].chunk_hash < pool[best].chunk_hash)));
            if better {
                best = index;
                best_score = score;
            }
        }
        selected.push(best);
        remaining.retain(|index| *index != best);
    }

    let mut ordered = selected
        .into_iter()
        .map(|index| &pool[index])
        .collect::<Vec<_>>();
    ordered.extend(tail.iter());
    ordered
}

fn apply_max_per_raw_hash(
    ordered: &[&MmrCandidate],
    max_per_raw_hash: u64,
) -> Vec<DiversifiedCandidate> {
    let limit = if max_per_raw_hash == 0 {
        u64::MAX
    } else {
        max_per_raw_hash
    };
    let mut counts = std::collections::BTreeMap::<&str, u64>::new();
    let mut out = Vec::new();
    for candidate in ordered {
        let count = counts.entry(candidate.raw_hash.as_str()).or_insert(0);
        if *count >= limit {
            continue;
        }
        *count += 1;
        out.push(DiversifiedCandidate {
            chunk_hash: candidate.chunk_hash.clone(),
            final_rank: out.len() as u64 + 1,
        });
    }
    out
}

fn cosine(a: &[f32], b: &[f32]) -> f64 {
    let mut dot = 0.0f64;
    let mut norm_a = 0.0f64;
    let mut norm_b = 0.0f64;
    for (left, right) in a.iter().zip(b.iter()) {
        let left = *left as f64;
        let right = *right as f64;
        dot += left * right;
        norm_a += left * left;
        norm_b += right * right;
    }
    if norm_a == 0.0 || norm_b == 0.0 {
        0.0
    } else {
        dot / (norm_a.sqrt() * norm_b.sqrt())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn candidate(id: &str, raw: &str, score: f64, embedding: Vec<f32>) -> MmrCandidate {
        MmrCandidate {
            chunk_hash: id.to_owned(),
            raw_hash: raw.to_owned(),
            relevance: score,
            embedding: Some(embedding),
            heading_path: None,
            section_id: None,
        }
    }

    #[test]
    fn ct3_mmr_001_mmr_selection_vector() {
        // Vectors chosen so their cosine similarities match the A.5 matrix closely
        // enough to force the same deterministic order.
        let candidates = vec![
            candidate("c1", "r1", 0.03, vec![1.0, 0.0, 0.0]),
            candidate("c2", "r2", 2.0 / 75.0, vec![0.95, 0.3122499, 0.0]),
            candidate("c3", "r3", 13.0 / 500.0, vec![0.30, -0.112134, 0.9472136]),
            candidate("c4", "r4", 0.02, vec![0.20, 0.0, 0.9797959]),
        ];
        let out = diversify_candidates(
            &candidates,
            MmrConfig {
                strategy: DiversifyStrategy::Mmr,
                mmr_lambda: 0.7,
                max_per_raw_hash: 10,
                mmr_depth: 100,
            },
        )
        .unwrap();
        assert_eq!(
            out.iter()
                .map(|c| c.chunk_hash.as_str())
                .collect::<Vec<_>>(),
            vec!["c1", "c3", "c2", "c4"]
        );
    }

    #[test]
    fn ct3_mmr_002_mmr_is_deterministic() {
        let candidates = vec![
            candidate("c1", "r", 1.0, vec![1.0, 0.0]),
            candidate("c2", "r", 1.0, vec![0.0, 1.0]),
        ];
        let config = MmrConfig {
            strategy: DiversifyStrategy::Mmr,
            mmr_lambda: 0.7,
            max_per_raw_hash: 10,
            mmr_depth: 100,
        };
        assert_eq!(
            diversify_candidates(&candidates, config.clone()).unwrap(),
            diversify_candidates(&candidates, config).unwrap()
        );
    }

    #[test]
    fn ct3_mmr_003_mmr_depth_only_diversifies_prefix() {
        let candidates = vec![
            candidate("c1", "r1", 4.0, vec![1.0, 0.0]),
            candidate("c2", "r2", 3.0, vec![1.0, 0.0]),
            candidate("c3", "r3", 2.0, vec![0.0, 1.0]),
        ];
        let out = diversify_candidates(
            &candidates,
            MmrConfig {
                strategy: DiversifyStrategy::Mmr,
                mmr_lambda: 0.7,
                max_per_raw_hash: 10,
                mmr_depth: 2,
            },
        )
        .unwrap();
        assert_eq!(out.last().unwrap().chunk_hash, "c3");
    }

    #[test]
    fn ct3_mmr_004_max_per_raw_hash_applies_to_stream() {
        // R12-1: max_per_raw_hash is the `group_by_raw_hash` dedup cap (and applies
        // under `mmr` too). This asserts the stream-wide cap; it must NOT use `off`
        // — `off` is now a true no-op that applies no dedup at all (see
        // `off_is_a_true_no_op_no_dedup`).
        let candidates = (0..5)
            .map(|i| candidate(&format!("c{i}"), "same", 10.0 - i as f64, vec![1.0, 0.0]))
            .collect::<Vec<_>>();
        let out = diversify_candidates(
            &candidates,
            MmrConfig {
                strategy: DiversifyStrategy::GroupByRawHash,
                mmr_lambda: 0.7,
                max_per_raw_hash: 3,
                mmr_depth: 100,
            },
        )
        .unwrap();
        assert_eq!(out.len(), 3);
    }

    #[test]
    fn off_is_a_true_no_op_no_dedup() {
        // R12-1: `strategy = "off"` returns every candidate in RRF order regardless
        // of max_per_raw_hash — the documented escape hatch is a real no-op.
        let candidates = (0..5)
            .map(|i| candidate(&format!("c{i}"), "same", 10.0 - i as f64, vec![1.0, 0.0]))
            .collect::<Vec<_>>();
        let out = diversify_candidates(
            &candidates,
            MmrConfig {
                strategy: DiversifyStrategy::Off,
                mmr_lambda: 0.7,
                max_per_raw_hash: 3,
                mmr_depth: 100,
            },
        )
        .unwrap();
        assert_eq!(out.len(), 5);
        assert_eq!(
            out.iter()
                .map(|c| c.chunk_hash.as_str())
                .collect::<Vec<_>>(),
            vec!["c0", "c1", "c2", "c3", "c4"]
        );
    }

    #[test]
    fn ct3_mmr_005_text_only_keeps_rrf_order() {
        let mut candidates = vec![
            candidate("c1", "r1", 1.0, vec![1.0]),
            candidate("c2", "r2", 0.9, vec![1.0]),
        ];
        candidates[0].embedding = None;
        let out = diversify_candidates(
            &candidates,
            MmrConfig {
                strategy: DiversifyStrategy::Mmr,
                mmr_lambda: 0.7,
                max_per_raw_hash: 10,
                mmr_depth: 100,
            },
        )
        .unwrap();
        assert_eq!(out[0].chunk_hash, "c1");
    }
}
