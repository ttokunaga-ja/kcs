//! Built-in adapter catalog and execution entry points.
//!
//! Non-adapter crates should depend on these stable catalog functions instead of
//! naming or constructing concrete built-in adapters directly.

use std::path::Path;

use sha2::{Digest, Sha256};

use crate::deterministic::DeterministicAdapter;
use crate::gemini_embedding::{
    GeminiEmbeddingAdapter, GeminiEmbeddingClient, ADOPTED_DIMENSIONS, ADOPTED_MODEL_PIN,
};
use crate::mistral_ocr::{
    EnvMistralOcrClient, MistralOcrClient, MistralOcrMarkdownizeAdapter, OcrImage, OcrPage,
    OcrResponse,
};
use crate::traits::{EmbeddingAdapter, MarkdownizeAdapter, PrepareAdapter};
use crate::types::{
    AdapterProfile, EmbeddingInputType, EmbeddingItem, EmbeddingRequest, EmbeddingVector,
    MarkdownizeMode, MarkdownizeRequest, MarkdownizeResponse, PreparedUnitHint, RawInput,
};
use crate::{AdapterError, Result};

pub const TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV: &str = "KCS_TEST_MISTRAL_OCR";
pub const TEST_ADOPTED_EMBEDDING_ENV: &str = "KCS_TEST_GEMINI_EMBED";

#[must_use]
pub fn builtin_prepare_profile() -> AdapterProfile {
    let mut profile = PrepareAdapter::profile(&DeterministicAdapter);
    profile.adapter_id = "prepare_default".to_owned();
    profile
}

#[must_use]
pub fn standard_online_markdownize_profile() -> AdapterProfile {
    MistralOcrMarkdownizeAdapter::default().profile()
}

pub fn builtin_offline_markdownize_adapter() -> Box<dyn MarkdownizeAdapter> {
    Box::new(DeterministicAdapter)
}

#[must_use]
pub fn adopted_embedding_profile() -> AdapterProfile {
    GeminiEmbeddingAdapter::default().profile()
}

pub struct StandardOnlineMarkdownizeRequest<'a> {
    pub scope_id: &'a str,
    pub kcs_dir: &'a Path,
    pub raw_hash: &'a str,
    pub path: &'a Path,
    pub media_type: &'a str,
    pub prepared_unit_hints: Vec<PreparedUnitHint>,
}

pub struct StandardOnlineMarkdownizeOutcome {
    pub profile: AdapterProfile,
    pub response: MarkdownizeResponse,
}

pub fn run_standard_online_markdownize(
    request: StandardOnlineMarkdownizeRequest<'_>,
) -> Result<StandardOnlineMarkdownizeOutcome> {
    let adapter_request = MarkdownizeRequest {
        raw: RawInput {
            raw_hash: request.raw_hash.to_owned(),
            path: Some(request.path.display().to_string()),
        },
        media_type: request.media_type.to_owned(),
        prepared_unit_hint: Some(request.prepared_unit_hints),
        mode: MarkdownizeMode::Full,
        previous: None,
        hints: None,
        tool_profile_hash: String::new(),
        spec_version: 1,
    };
    match std::env::var(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV)
        .ok()
        .as_deref()
    {
        Some("auth_error") => return Err(AdapterError::Auth("mock auth failure".to_owned())),
        Some("rate_limit") => return Err(AdapterError::RateLimit("mock 429".to_owned())),
        Some("mock") | Some("partial") | Some("mock_link_image") => {
            let client = MockStandardOnlineMarkdownizeClient;
            let model_pin = client.resolve_model_pin("mistral-ocr-latest")?;
            let adapter = MistralOcrMarkdownizeAdapter::new(client, model_pin, request.scope_id)
                .with_image_store(request.kcs_dir);
            let profile = adapter.profile();
            let mut adapter_request = adapter_request;
            adapter_request.tool_profile_hash = profile.tool_profile_hash.clone();
            let response = adapter.markdownize(adapter_request)?;
            return Ok(StandardOnlineMarkdownizeOutcome { profile, response });
        }
        _ => {}
    }
    let client = EnvMistralOcrClient::new();
    let model_pin = client.resolve_model_pin("mistral-ocr-latest")?;
    let adapter = MistralOcrMarkdownizeAdapter::new(client, model_pin, request.scope_id)
        .with_image_store(request.kcs_dir);
    let profile = adapter.profile();
    let mut adapter_request = adapter_request;
    adapter_request.tool_profile_hash = profile.tool_profile_hash.clone();
    let response = adapter.markdownize(adapter_request)?;
    Ok(StandardOnlineMarkdownizeOutcome { profile, response })
}

#[derive(Debug, Clone)]
struct MockStandardOnlineMarkdownizeClient;

impl MistralOcrClient for MockStandardOnlineMarkdownizeClient {
    fn resolve_model_pin(&self, _configured_model: &str) -> Result<String> {
        Ok("mistral-ocr-2505".to_owned())
    }

    fn ocr_markdown(&self, request: &MarkdownizeRequest, model_pin: &str) -> Result<OcrResponse> {
        let mut pages: Vec<OcrPage> = request
            .prepared_unit_hint
            .as_deref()
            .unwrap_or(&[])
            .iter()
            .enumerate()
            .map(|(index, hint)| OcrPage {
                index,
                markdown: if std::env::var(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV)
                    .ok()
                    .as_deref()
                    == Some("mock_link_image")
                {
                    format!(
                        "[source](https://example.com/{index}) mock ocr {} ![img-{index}](img-{index}.png)\n",
                        hint.unit_key
                    )
                } else {
                    format!(
                        "mock ocr {} ![img-{index}](img-{index}.png)\n",
                        hint.unit_key
                    )
                },
                images: vec![OcrImage {
                    bytes: format!("image-{}", hint.unit_key).into_bytes(),
                    media_type: "image/png".to_owned(),
                    bbox: Some([index as i64, 0, index as i64 + 1, 1]),
                    confidence: Some("0.99".to_owned()),
                }],
            })
            .collect();
        if std::env::var(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV)
            .ok()
            .as_deref()
            == Some("partial")
        {
            pages.pop();
        }
        Ok(OcrResponse {
            pages,
            model_version_pin: model_pin.to_owned(),
        })
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AdoptedEmbeddingExecution {
    Mock,
    IncompatibleProfile,
    NonMultimodal,
    AuthError,
    RateLimit,
    Real,
}

#[must_use]
pub fn active_adopted_embedding_execution() -> Option<AdoptedEmbeddingExecution> {
    match std::env::var(TEST_ADOPTED_EMBEDDING_ENV).ok().as_deref() {
        Some("mock") => Some(AdoptedEmbeddingExecution::Mock),
        Some("incompatible_profile") => Some(AdoptedEmbeddingExecution::IncompatibleProfile),
        Some("non_multimodal") => Some(AdoptedEmbeddingExecution::NonMultimodal),
        Some("auth_error") => Some(AdoptedEmbeddingExecution::AuthError),
        Some("rate_limit") => Some(AdoptedEmbeddingExecution::RateLimit),
        Some(_) => None,
        None => std::env::var("GEMINI_API_KEY")
            .is_ok()
            .then_some(AdoptedEmbeddingExecution::Real),
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DeclaredEmbeddingProfile {
    pub tool_id: String,
    pub dimensions: u64,
    pub distance: String,
    pub modality: String,
    pub profile_hash: String,
}

#[must_use]
pub fn declared_adopted_embedding_profile(
    execution: AdoptedEmbeddingExecution,
) -> DeclaredEmbeddingProfile {
    let adopted = adopted_embedding_profile();
    match execution {
        AdoptedEmbeddingExecution::IncompatibleProfile => DeclaredEmbeddingProfile {
            tool_id: "test_embedding_incompatible".to_owned(),
            dimensions: ADOPTED_DIMENSIONS as u64,
            distance: "cosine".to_owned(),
            modality: "multimodal".to_owned(),
            profile_hash: "sha256:00000000000000000000000000000000000000000000000000000000incompat"
                .to_owned(),
        },
        AdoptedEmbeddingExecution::NonMultimodal => DeclaredEmbeddingProfile {
            tool_id: "test_text_embedding".to_owned(),
            dimensions: ADOPTED_DIMENSIONS as u64,
            distance: "cosine".to_owned(),
            modality: "text".to_owned(),
            profile_hash: adopted.tool_profile_hash,
        },
        _ => DeclaredEmbeddingProfile {
            tool_id: adopted.adapter_id,
            dimensions: ADOPTED_DIMENSIONS as u64,
            distance: "cosine".to_owned(),
            modality: "multimodal".to_owned(),
            profile_hash: adopted.tool_profile_hash,
        },
    }
}

pub fn run_adopted_embedding(
    execution: AdoptedEmbeddingExecution,
    items: Vec<EmbeddingItem>,
    input_type: EmbeddingInputType,
) -> Result<Vec<EmbeddingVector>> {
    let request = EmbeddingRequest { input_type, items };
    let response = match execution {
        AdoptedEmbeddingExecution::Real => GeminiEmbeddingAdapter::default().embed(request),
        other => GeminiEmbeddingAdapter::new(
            MockAdoptedEmbeddingClient { execution: other },
            ADOPTED_MODEL_PIN,
            ADOPTED_DIMENSIONS,
        )
        .embed(request),
    }?;
    Ok(response.vectors)
}

#[must_use]
pub fn deterministic_embedding_vector(seed: &str, dimensions: usize) -> Vec<f32> {
    let mut values = Vec::with_capacity(dimensions);
    let mut counter = 0u32;
    while values.len() < dimensions {
        let mut hasher = Sha256::new();
        hasher.update(seed.as_bytes());
        hasher.update(counter.to_le_bytes());
        let digest = hasher.finalize();
        for chunk in digest.chunks_exact(4) {
            if values.len() >= dimensions {
                break;
            }
            let bits = u32::from_le_bytes([chunk[0], chunk[1], chunk[2], chunk[3]]);
            values.push((bits as f64 / u32::MAX as f64 * 2.0 - 1.0) as f32);
        }
        counter += 1;
    }
    let norm = values.iter().map(|value| value * value).sum::<f32>().sqrt();
    if norm > 0.0 {
        for value in &mut values {
            *value /= norm;
        }
    }
    values
}

#[derive(Debug, Clone, Copy)]
struct MockAdoptedEmbeddingClient {
    execution: AdoptedEmbeddingExecution,
}

impl GeminiEmbeddingClient for MockAdoptedEmbeddingClient {
    fn resolve_model_pin(&self, _configured_model: &str) -> Result<String> {
        Ok(ADOPTED_MODEL_PIN.to_owned())
    }

    fn embed(
        &self,
        items: &[EmbeddingItem],
        _model_pin: &str,
        dimensions: u32,
    ) -> Result<Vec<EmbeddingVector>> {
        match self.execution {
            AdoptedEmbeddingExecution::AuthError => {
                return Err(AdapterError::Auth("mock auth failure".to_owned()))
            }
            AdoptedEmbeddingExecution::RateLimit => {
                return Err(AdapterError::RateLimit("mock 429".to_owned()))
            }
            _ => {}
        }
        Ok(items
            .iter()
            .map(|item| EmbeddingVector {
                id: item.id.clone(),
                vector: deterministic_embedding_vector(
                    item.text.as_deref().unwrap_or(""),
                    dimensions as usize,
                ),
            })
            .collect())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::AdapterKind;

    #[test]
    fn adopted_profiles_are_catalog_owned() {
        assert_eq!(builtin_prepare_profile().adapter_id, "prepare_default");
        assert_eq!(
            standard_online_markdownize_profile().adapter_id,
            "mistral_ocr_markdownize"
        );
        assert_eq!(adopted_embedding_profile().adapter_id, "gemini_embedding_2");
    }

    #[test]
    fn deterministic_embedding_vector_is_stable_and_normalized() {
        let a = deterministic_embedding_vector("認証仕様 トークン", 768);
        let b = deterministic_embedding_vector("認証仕様 トークン", 768);
        assert_eq!(a, b);
        let norm = a.iter().map(|value| value * value).sum::<f32>().sqrt();
        assert!((norm - 1.0).abs() < 0.0001);

        let other = deterministic_embedding_vector("別のクエリ", 768);
        assert_ne!(a, other);
    }

    #[test]
    fn declared_adopted_embedding_profile_uses_adopted_profile_by_default() {
        let declared = declared_adopted_embedding_profile(AdoptedEmbeddingExecution::Mock);
        let adopted = adopted_embedding_profile();
        assert_eq!(declared.tool_id, adopted.adapter_id);
        assert_eq!(declared.profile_hash, adopted.tool_profile_hash);
        assert_eq!(declared.modality, "multimodal");
        assert_eq!(declared.dimensions, 768);
    }

    #[test]
    fn run_adopted_embedding_mock_returns_one_vector_per_item() {
        let vectors = run_adopted_embedding(
            AdoptedEmbeddingExecution::Mock,
            vec![
                EmbeddingItem {
                    id: "a".to_owned(),
                    text: Some("hello".to_owned()),
                    path: None,
                    mime: None,
                },
                EmbeddingItem {
                    id: "b".to_owned(),
                    text: Some("world".to_owned()),
                    path: None,
                    mime: None,
                },
            ],
            EmbeddingInputType::MarkdownChunk,
        )
        .unwrap();
        assert_eq!(vectors.len(), 2);
        assert_eq!(vectors[0].id, "a");
        assert_eq!(vectors[1].id, "b");
    }

    #[test]
    fn run_adopted_embedding_mock_errors_are_classified() {
        assert!(matches!(
            run_adopted_embedding(
                AdoptedEmbeddingExecution::AuthError,
                Vec::new(),
                EmbeddingInputType::Query,
            ),
            Err(AdapterError::Auth(_))
        ));
        assert!(matches!(
            run_adopted_embedding(
                AdoptedEmbeddingExecution::RateLimit,
                Vec::new(),
                EmbeddingInputType::Query,
            ),
            Err(AdapterError::RateLimit(_))
        ));
    }

    #[test]
    fn standard_online_markdownize_mock_runs() {
        let temp = tempfile::tempdir().unwrap();
        let input = temp.path().join("input.pdf");
        std::fs::write(&input, b"%PDF mock").unwrap();
        std::env::set_var(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "mock");
        let outcome = run_standard_online_markdownize(StandardOnlineMarkdownizeRequest {
            scope_id: "01H00000000000000000000000",
            kcs_dir: temp.path(),
            raw_hash: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            path: &input,
            media_type: "application/pdf",
            prepared_unit_hints: vec![PreparedUnitHint {
                unit_key: "page:1".to_owned(),
                prepared_hash:
                    "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                        .to_owned(),
                unit_kind: crate::types::UnitKind::Page,
                order: 0,
            }],
        })
        .unwrap();
        std::env::remove_var(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV);
        assert_eq!(outcome.profile.adapter_kind, AdapterKind::Markdownize);
        assert_eq!(outcome.response.updated_units.len(), 1);
    }
}
