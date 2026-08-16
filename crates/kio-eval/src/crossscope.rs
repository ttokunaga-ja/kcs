//! Cross-scope supplement evaluator.
//!
//! This deliberately does not use the full-suite history-count or coverage
//! gates: this frozen supplement measures rank merging, not history coverage.

use std::{
    collections::{BTreeMap, HashSet},
    path::PathBuf,
    process::Command,
};

use serde::Serialize;
use thiserror::Error;

use crate::{
    RecallResult, ResultKey,
    artifact::CreateOnlyArtifact,
    attestation::{MAX_POINTER_ATTESTATIONS_PER_QUERY, PointerAttestor},
    boundary::BoundCorpus,
    manifest::{Scenario, load_corpus_manifest, load_golden_queries, load_history_manifest},
    recall_at_k,
    resolver::{CorpusModel, Resolver, validate_query},
    runner::{
        BoundedProcessOptions, ClassifiedOutcome, SearchOutcome, classify_outcome,
        latency_target_ms, run_bounded_command,
    },
};

const RECALL_TARGET: f64 = 0.8;
const RANK_LIMIT: usize = 50;
const MAX_CROSSSCOPE_REPORT_BYTES: usize = 16 * 1024 * 1024;

#[derive(Debug, Clone)]
pub struct CrossscopeOptions {
    pub golden: PathBuf,
    pub corpus: PathBuf,
    pub bin: PathBuf,
    pub out: PathBuf,
    pub dry_run: bool,
}

#[derive(Debug, Error)]
pub enum CrossscopeError {
    #[error("{0}")]
    Input(String),
    #[error(transparent)]
    Manifest(#[from] crate::manifest::ManifestError),
    #[error(transparent)]
    Runner(#[from] crate::runner::RunnerError),
    #[error("could not serialize cross-scope evaluation artifact: {0}")]
    Serialize(#[from] serde_json::Error),
}

#[derive(Debug, Serialize)]
struct CrossscopeResults {
    target_recall_at_10: f64,
    scenarios: BTreeMap<String, ScenarioSummary>,
    queries: Vec<QueryRow>,
    counts: Counts,
}

#[derive(Debug, Serialize)]
struct ScenarioSummary {
    n_queries: usize,
    recall_at_10: Option<f64>,
    p95_ms: Option<f64>,
    latency_target_ms: f64,
    passes_target: bool,
    passes_latency: bool,
}

#[derive(Debug, Serialize)]
struct QueryRow {
    scenario: String,
    query: String,
    status: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    recall_at_10: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error_code: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    detail: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    duration_ms: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    scopes: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    worst_expected_rank: Option<usize>,
}

#[derive(Debug, Serialize)]
struct Counts {
    n_queries: usize,
    n_failed: usize,
    worst_expected_rank_mean: Option<f64>,
    worst_expected_rank_max: Option<usize>,
}

fn expected_scopes(query: &crate::manifest::GoldenQuery) -> Vec<String> {
    let mut scopes = query
        .expected
        .iter()
        .map(|value| value.scope.clone())
        .collect::<Vec<_>>();
    scopes.sort();
    scopes.dedup();
    scopes
}

fn validate_crossscope_queries(
    queries: &[crate::manifest::GoldenQuery],
) -> Result<(), CrossscopeError> {
    let single_scope = queries
        .iter()
        .filter(|query| expected_scopes(query).len() < 2)
        .map(|query| query.query.clone())
        .collect::<Vec<_>>();
    if single_scope.is_empty() {
        Ok(())
    } else {
        Err(CrossscopeError::Input(format!(
            "cross-scope query expected must span at least two scopes: {}",
            single_scope.join(", ")
        )))
    }
}

fn result_key(hit: &crate::runner::SearchHit) -> ResultKey {
    RecallResult {
        raw_hash: hit.pointer.raw_hash.clone(),
        section_id: hit.pointer.section_id.clone(),
        heading_path: hit.pointer.heading_path.clone(),
        path_at_commit: hit.pointer.path_at_commit.clone(),
    }
    .key()
}

/// Returns the one-based rank of the lowest expected result, if every expected
/// identity appeared in the bounded diagnostic window.
pub fn worst_expected_rank(
    results: &[crate::runner::SearchHit],
    expected: &HashSet<ResultKey>,
) -> Option<usize> {
    if expected.is_empty() {
        return None;
    }
    let mut seen = HashSet::new();
    for (index, hit) in results.iter().take(RANK_LIMIT).enumerate() {
        let key = result_key(hit);
        if expected.contains(&key) {
            seen.insert(key);
        }
        if seen == *expected {
            return Some(index + 1);
        }
    }
    None
}

fn p95(values: &[f64]) -> Option<f64> {
    if values.is_empty()
        || values
            .iter()
            .any(|value| !value.is_finite() || *value < 0.0)
    {
        return None;
    }
    let mut values = values.to_vec();
    values.sort_by(f64::total_cmp);
    values
        .get((0.95 * values.len() as f64).ceil().max(1.0) as usize - 1)
        .copied()
}

pub fn run(options: CrossscopeOptions) -> Result<kio_core::ExitCode, CrossscopeError> {
    let queries = load_golden_queries(&options.golden)?;
    validate_crossscope_queries(&queries)?;
    let corpus_manifest = options.corpus.join("corpus-manifest.json");
    let history_manifest = options.corpus.join("history-manifest.json");
    let corpus = load_corpus_manifest(&corpus_manifest)?;
    let _history = load_history_manifest(&history_manifest, &corpus)?;
    let model = CorpusModel::new(&corpus);
    let resolver = Resolver::new(&corpus);
    let problems = queries
        .iter()
        .flat_map(|query| validate_query(query, &model, &resolver))
        .collect::<Vec<_>>();
    if options.dry_run {
        return Ok(if problems.is_empty() {
            kio_core::ExitCode::Success
        } else {
            kio_core::ExitCode::Failure
        });
    }
    if !problems.is_empty() {
        return Err(CrossscopeError::Input(problems.join("; ")));
    }
    let destination = CreateOnlyArtifact::bind(
        &options.out,
        &options.corpus,
        "cross-scope evaluation artifact",
    )
    .map_err(|error| CrossscopeError::Input(error.to_string()))?;
    let corpus_dir = options
        .corpus
        .canonicalize()
        .map_err(|e| CrossscopeError::Input(format!("cannot open corpus: {e}")))?;
    let bound = BoundCorpus::bind(&corpus_dir, &corpus.scopes)
        .map_err(|e| CrossscopeError::Input(e.to_string()))?;
    let bin = options.bin.canonicalize().map_err(|_| {
        CrossscopeError::Input(format!("kio binary unavailable: {}", options.bin.display()))
    })?;
    if !bin.is_file() {
        return Err(CrossscopeError::Input(format!(
            "kio binary unavailable: {}",
            bin.display()
        )));
    }
    let environment = bound.device().hermetic_environment();
    let mut attestor = queries
        .iter()
        .any(|query| query.scenario == Scenario::M3_2)
        .then(|| PointerAttestor::from_bound_corpus(&bound))
        .transpose()
        .map_err(|e| CrossscopeError::Input(e.to_string()))?;
    let mut rows = Vec::new();
    let mut scores: BTreeMap<String, Vec<f64>> = BTreeMap::new();
    let mut latency: BTreeMap<String, Vec<f64>> = BTreeMap::new();
    let mut failed = 0;
    for query in &queries {
        let scenario = query.scenario.as_str().to_owned();
        let scopes = expected_scopes(query);
        let (expected, errors) = resolver.resolve_expected(&query.expected);
        if !errors.is_empty() {
            failed += 1;
            scores.entry(scenario.clone()).or_default().push(0.0);
            rows.push(QueryRow {
                scenario,
                query: query.query.clone(),
                status: "failed".into(),
                recall_at_10: Some(0.0),
                error_code: None,
                detail: Some(
                    errors
                        .iter()
                        .map(ToString::to_string)
                        .collect::<Vec<_>>()
                        .join("; "),
                ),
                duration_ms: None,
                scopes: None,
                worst_expected_rank: None,
            });
            continue;
        }
        let mut command = Command::new(&bin);
        command
            .arg("--json")
            .arg("search")
            .arg(&query.query)
            .arg("--all-scopes");
        for flag in &query.flags {
            command.arg(flag);
        }
        if let Some(flag) = query.scenario.required_flag()
            && !query.flags.iter().any(|value| value == flag)
        {
            command.arg(flag);
        }
        command.env_clear().envs(environment.iter().cloned());
        let research = bound
            .scope("research")
            .ok_or_else(|| CrossscopeError::Input("research scope is unavailable".into()))?;
        research
            .configure_command_cwd(&mut command)
            .map_err(|e| CrossscopeError::Input(e.to_string()))?;
        let output = run_bounded_command(&mut command, BoundedProcessOptions::default())
            .map_err(crate::runner::RunnerError::from)?;
        let outcome = SearchOutcome {
            returncode: output.status.code().unwrap_or(-1),
            stdout: output.stdout,
            stderr: output.stderr,
            duration_ms: output.duration.as_secs_f64() * 1000.0,
        };
        let duration_ms = outcome.duration_ms;
        latency
            .entry(scenario.clone())
            .or_default()
            .push(duration_ms);
        match classify_outcome(&outcome) {
            ClassifiedOutcome::Scored {
                response, detail, ..
            } => {
                let validation = if query.scenario == Scenario::M3_2 {
                    let attestor = attestor.as_mut().expect("M3-2 requires attestor");
                    response
                        .results
                        .iter()
                        .take(MAX_POINTER_ATTESTATIONS_PER_QUERY)
                        .enumerate()
                        .map(|(index, hit)| {
                            attestor.attest(&hit.pointer_value).map_err(|error| {
                                format!("result[{index}] pointer attestation failed: {error}")
                            })
                        })
                        .collect::<Result<Vec<_>, _>>()
                        .map(|_| ())
                } else {
                    Ok(())
                };
                if let Err(detail) = validation {
                    failed += 1;
                    scores.entry(scenario.clone()).or_default().push(0.0);
                    rows.push(QueryRow {
                        scenario,
                        query: query.query.clone(),
                        status: "failed".into(),
                        recall_at_10: Some(0.0),
                        error_code: None,
                        detail: Some(detail),
                        duration_ms: Some(duration_ms),
                        scopes: None,
                        worst_expected_rank: None,
                    });
                    continue;
                }
                let recall = recall_at_k(
                    &response
                        .results
                        .iter()
                        .map(|hit| RecallResult {
                            raw_hash: hit.pointer.raw_hash.clone(),
                            section_id: hit.pointer.section_id.clone(),
                            heading_path: hit.pointer.heading_path.clone(),
                            path_at_commit: hit.pointer.path_at_commit.clone(),
                        })
                        .collect::<Vec<_>>(),
                    &expected,
                    10,
                );
                scores.entry(scenario.clone()).or_default().push(recall);
                rows.push(QueryRow {
                    scenario,
                    query: query.query.clone(),
                    status: "ok".into(),
                    recall_at_10: Some(recall),
                    error_code: None,
                    detail,
                    duration_ms: Some(duration_ms),
                    scopes: Some(scopes),
                    worst_expected_rank: worst_expected_rank(&response.results, &expected),
                });
            }
            ClassifiedOutcome::Unimplemented { error_code } => {
                failed += 1;
                scores.entry(scenario.clone()).or_default().push(0.0);
                rows.push(QueryRow {
                    scenario,
                    query: query.query.clone(),
                    status: "unimplemented".into(),
                    recall_at_10: Some(0.0),
                    error_code: Some(error_code),
                    detail: Some("search 未実装 (NOT-IMPLEMENTED)".into()),
                    duration_ms: Some(duration_ms),
                    scopes: None,
                    worst_expected_rank: None,
                });
            }
            ClassifiedOutcome::Failed { error_code, detail } => {
                failed += 1;
                scores.entry(scenario.clone()).or_default().push(0.0);
                rows.push(QueryRow {
                    scenario,
                    query: query.query.clone(),
                    status: "failed".into(),
                    recall_at_10: Some(0.0),
                    error_code,
                    detail: Some(detail),
                    duration_ms: Some(duration_ms),
                    scopes: None,
                    worst_expected_rank: None,
                });
            }
        }
    }
    let mut scenarios = BTreeMap::new();
    let mut all_pass = failed == 0;
    for scenario in Scenario::ALL.map(Scenario::as_str) {
        if !queries
            .iter()
            .any(|query| query.scenario.as_str() == scenario)
        {
            continue;
        }
        let values = scores.get(scenario).cloned().unwrap_or_default();
        let recall = (!values.is_empty()).then(|| values.iter().sum::<f64>() / values.len() as f64);
        let p95_ms = p95(latency.get(scenario).map_or(&[], Vec::as_slice));
        let target = latency_target_ms(scenario).expect("known scenario");
        let passes_target = recall.is_some_and(|value| value >= RECALL_TARGET);
        let passes_latency = p95_ms.is_some_and(|value| value < target);
        all_pass &= passes_target && passes_latency;
        scenarios.insert(
            scenario.to_owned(),
            ScenarioSummary {
                n_queries: values.len(),
                recall_at_10: recall,
                p95_ms,
                latency_target_ms: target,
                passes_target,
                passes_latency,
            },
        );
    }
    let ranks = rows
        .iter()
        .filter_map(|row| row.worst_expected_rank)
        .collect::<Vec<_>>();
    let artifact = CrossscopeResults {
        target_recall_at_10: RECALL_TARGET,
        scenarios,
        queries: rows,
        counts: Counts {
            n_queries: queries.len(),
            n_failed: failed,
            worst_expected_rank_mean: (!ranks.is_empty())
                .then(|| ranks.iter().sum::<usize>() as f64 / ranks.len() as f64),
            worst_expected_rank_max: ranks.into_iter().max(),
        },
    };
    let value = serde_json::to_value(&artifact)?;
    let mut bytes = serde_json::to_vec_pretty(&value)?;
    bytes.push(b'\n');
    destination
        .publish(&bytes, MAX_CROSSSCOPE_REPORT_BYTES)
        .map_err(|error| CrossscopeError::Input(error.to_string()))?;
    Ok(if all_pass {
        kio_core::ExitCode::Success
    } else {
        kio_core::ExitCode::Failure
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::runner::{EvidencePointerRecord, SearchHit};
    use serde_json::json;
    use std::collections::HashSet;

    fn hit(raw: &str) -> SearchHit {
        SearchHit {
            pointer: EvidencePointerRecord {
                commit: "c".into(),
                tree: None,
                raw_hash: raw.into(),
                tool_profile_hash: "p".into(),
                chunk_hash: "h".into(),
                path_at_commit: Some(format!("{raw}.md")),
                section_id: Some("s".into()),
                heading_path: None,
                scope_id: "scope".into(),
            },
            pointer_value: json!({}),
            current_paths: None,
            current_path: None,
            title: None,
        }
    }

    #[test]
    fn rank_diagnostic_uses_lowest_expected_rank() {
        let expected = [hit("a"), hit("c")]
            .iter()
            .map(result_key)
            .collect::<HashSet<_>>();
        assert_eq!(
            worst_expected_rank(&[hit("a"), hit("b"), hit("c")], &expected),
            Some(3)
        );
    }

    #[test]
    fn rejects_single_scope_query_before_filesystem_access() {
        let query = crate::manifest::GoldenQuery {
            scenario: Scenario::M3_1,
            query: "q".into(),
            flags: vec![],
            expected: vec![crate::manifest::Expected {
                scope: "research".into(),
                file: "a.md".into(),
                section: "a".into(),
            }],
        };
        assert!(matches!(
            validate_crossscope_queries(&[query]),
            Err(CrossscopeError::Input(message)) if message.contains("at least two scopes")
        ));
    }

    #[test]
    fn output_schema_is_strict_lf() {
        let artifact = CrossscopeResults {
            target_recall_at_10: RECALL_TARGET,
            scenarios: BTreeMap::new(),
            queries: vec![QueryRow {
                scenario: "M3-1".into(),
                query: "q".into(),
                status: "ok".into(),
                recall_at_10: Some(1.0),
                error_code: None,
                detail: None,
                duration_ms: Some(1.0),
                scopes: Some(vec!["notes".into(), "research".into()]),
                worst_expected_rank: Some(2),
            }],
            counts: Counts {
                n_queries: 0,
                n_failed: 0,
                worst_expected_rank_mean: None,
                worst_expected_rank_max: None,
            },
        };
        let value = serde_json::to_value(artifact).unwrap();
        let mut bytes = serde_json::to_vec_pretty(&value).unwrap();
        bytes.push(b'\n');
        assert!(bytes.ends_with(b"\n"));
        assert!(!bytes.windows(2).any(|pair| pair == b"\r\n"));
        let parsed: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(
            parsed
                .as_object()
                .unwrap()
                .keys()
                .cloned()
                .collect::<Vec<_>>(),
            ["counts", "queries", "scenarios", "target_recall_at_10"]
        );
        assert_eq!(
            parsed["queries"][0]
                .as_object()
                .unwrap()
                .keys()
                .cloned()
                .collect::<Vec<_>>(),
            [
                "duration_ms",
                "query",
                "recall_at_10",
                "scenario",
                "scopes",
                "status",
                "worst_expected_rank"
            ]
        );
        assert!(parsed.get("aggregator").is_none());
        assert_eq!(parsed["counts"]["n_queries"], 0);
    }
}
