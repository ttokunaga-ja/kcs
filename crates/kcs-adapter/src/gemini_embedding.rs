//! Gemini multimodal Embedding Adapter (07 §5.3 / §6).
//!
//! Mirrors the Mistral OCR adapter structure: a `GeminiEmbeddingClient` trait
//! (network boundary) with an `Env`-backed HTTP implementation and a generic
//! `GeminiEmbeddingAdapter<C>` that implements [`EmbeddingAdapter`]. The adopted
//! profile is the single multimodal profile fixed on 2026-07-03: `gemini-embedding-2`
//! (GA, pinned at startup) / 768 dims (MRL) / cosine / `modality="multimodal"`.
//!
//! The live HTTP path is not exercised in the hermetic test suite (decision #28);
//! the wire format below is documentation-accurate best effort and the contract is
//! covered by the CLI mock seam. `profile()` never performs network I/O.

use crate::identity::{is_mutable_model_alias, tool_profile_hash};
use crate::traits::EmbeddingAdapter;
use crate::types::{
    AdapterKind, AdapterProfile, EmbeddingItem, EmbeddingRequest, EmbeddingResponse,
    EmbeddingVector, ExecutionMode,
};
use crate::{AdapterError, Result};
use serde_json::{json, Value};

/// Adopted embedding profile constants. Non-adapter crates access this profile
/// through `crate::catalog`, not by naming this adapter directly.
pub const ADOPTED_MODEL_FAMILY: &str = "gemini-embedding";
pub const ADOPTED_MODEL_PIN: &str = "gemini-embedding-2";
pub const ADOPTED_DIMENSIONS: u32 = 768;

/// Network boundary for the Gemini embedding backend.
pub trait GeminiEmbeddingClient: Clone {
    /// Resolve a possibly-mutable configured model alias to an immutable GA
    /// version at startup (07 §6: mutable aliases must never be pinned).
    fn resolve_model_pin(&self, configured_model: &str) -> Result<String>;

    /// Embed the batch of items, returning one vector per item (order preserved).
    fn embed(
        &self,
        items: &[EmbeddingItem],
        model_pin: &str,
        dimensions: u32,
    ) -> Result<Vec<EmbeddingVector>>;
}

#[derive(Debug, Clone, Default)]
pub struct EnvGeminiEmbeddingClient {
    base_url: Option<String>,
}

impl EnvGeminiEmbeddingClient {
    #[must_use]
    pub fn new() -> Self {
        Self { base_url: None }
    }

    #[allow(dead_code)]
    #[must_use]
    pub fn with_base_url(base_url: impl Into<String>) -> Self {
        Self {
            base_url: Some(base_url.into()),
        }
    }

    fn base_url(&self) -> String {
        self.base_url
            .clone()
            .or_else(|| std::env::var("GEMINI_API_BASE").ok())
            .unwrap_or_else(|| "https://generativelanguage.googleapis.com".to_owned())
            .trim_end_matches('/')
            .to_owned()
    }

    fn api_key() -> Result<String> {
        std::env::var("GEMINI_API_KEY")
            .map_err(|_| AdapterError::Auth("GEMINI_API_KEY is not set".to_owned()))
    }
}

impl GeminiEmbeddingClient for EnvGeminiEmbeddingClient {
    fn resolve_model_pin(&self, configured_model: &str) -> Result<String> {
        if !is_mutable_model_alias(configured_model) {
            return Ok(configured_model.to_owned());
        }
        let api_key = Self::api_key()?;
        let value: Value = ureq::get(&format!("{}/v1beta/models", self.base_url()))
            .set("x-goog-api-key", &api_key)
            .call()
            .map_err(http_error)?
            .into_json()
            .map_err(|err| AdapterError::ContractViolation(err.to_string()))?;
        // Model ids arrive as "models/<family>-NNN"; pick the max stable version
        // of the configured family, rejecting any remaining "-latest" alias.
        let family = configured_model
            .trim_end_matches("-latest")
            .rsplit('/')
            .next()
            .unwrap_or(configured_model);
        value
            .get("models")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
            .filter_map(|model| model.get("name").and_then(Value::as_str))
            .map(|name| name.rsplit('/').next().unwrap_or(name))
            .filter(|id| id.starts_with(family) && !id.ends_with("-latest"))
            .max()
            .map(str::to_owned)
            .ok_or_else(|| {
                AdapterError::ContractViolation(format!(
                    "no versioned model found for {configured_model}"
                ))
            })
    }

    fn embed(
        &self,
        items: &[EmbeddingItem],
        model_pin: &str,
        dimensions: u32,
    ) -> Result<Vec<EmbeddingVector>> {
        let api_key = Self::api_key()?;
        // `:batchEmbedContents` embeds the whole batch in one request. Vertex has
        // no batch inference, so batching is client-side (07 §5.3).
        let requests = items
            .iter()
            .map(|item| {
                json!({
                    "model": format!("models/{model_pin}"),
                    "content": { "parts": [{ "text": item.text.clone().unwrap_or_default() }] },
                    "outputDimensionality": dimensions,
                })
            })
            .collect::<Vec<_>>();
        let response: Value = ureq::post(&format!(
            "{}/v1beta/models/{model_pin}:batchEmbedContents",
            self.base_url()
        ))
        .set("x-goog-api-key", &api_key)
        .set("Content-Type", "application/json")
        .send_json(json!({ "requests": requests }))
        .map_err(http_error)?
        .into_json()
        .map_err(|err| AdapterError::ContractViolation(err.to_string()))?;
        parse_embeddings(&response, items, dimensions)
    }
}

fn parse_embeddings(
    response: &Value,
    items: &[EmbeddingItem],
    dimensions: u32,
) -> Result<Vec<EmbeddingVector>> {
    let embeddings = response
        .get("embeddings")
        .and_then(Value::as_array)
        .ok_or_else(|| {
            AdapterError::ContractViolation("embedding response missing embeddings".to_owned())
        })?;
    if embeddings.len() != items.len() {
        return Err(AdapterError::ContractViolation(
            "embedding response count does not match request".to_owned(),
        ));
    }
    items
        .iter()
        .zip(embeddings)
        .map(|(item, embedding)| {
            let vector = embedding
                .get("values")
                .and_then(Value::as_array)
                .ok_or_else(|| {
                    AdapterError::ContractViolation("embedding missing values".to_owned())
                })?
                .iter()
                .map(|value| value.as_f64().map(|value| value as f32))
                .collect::<Option<Vec<f32>>>()
                .ok_or_else(|| {
                    AdapterError::ContractViolation("embedding values must be numeric".to_owned())
                })?;
            // F7: the response vector must have exactly the requested
            // `outputDimensionality`. A wrong-width vector would otherwise be
            // persisted with the declared `dimensions` (768) but a mismatched
            // byte length, so `link_chunk_vec` silently drops it from `chunk_vec`
            // (permanent KNN exclusion) even though the chunk is billed and marked
            // done, with no self-repair path. Reject it as a contract violation so
            // the batch fails (retryable/reportable) instead of being charged.
            if vector.len() != dimensions as usize {
                return Err(AdapterError::ContractViolation(format!(
                    "embedding dimension mismatch: expected {dimensions}, got {}",
                    vector.len()
                )));
            }
            Ok(EmbeddingVector {
                id: item.id.clone(),
                vector,
            })
        })
        .collect()
}

#[derive(Debug, Clone)]
pub struct GeminiEmbeddingAdapter<C = EnvGeminiEmbeddingClient> {
    client: C,
    configured_model: String,
    dimensions: u32,
}

impl Default for GeminiEmbeddingAdapter<EnvGeminiEmbeddingClient> {
    fn default() -> Self {
        Self::new(
            EnvGeminiEmbeddingClient::new(),
            ADOPTED_MODEL_PIN,
            ADOPTED_DIMENSIONS,
        )
    }
}

impl<C> GeminiEmbeddingAdapter<C> {
    pub fn new(client: C, configured_model: impl Into<String>, dimensions: u32) -> Self {
        Self {
            client,
            configured_model: configured_model.into(),
            dimensions,
        }
    }

    /// The adopted profile JSON value (07 §5.3).
    #[must_use]
    pub fn profile_value(&self) -> Value {
        // Network-free (like Mistral): if an unresolved mutable alias is still
        // held, use a deterministic placeholder rather than resolving over HTTP.
        let model_pin = if is_mutable_model_alias(&self.configured_model) {
            format!(
                "{}-unresolved",
                self.configured_model.trim_end_matches("-latest")
            )
        } else {
            self.configured_model.clone()
        };
        json!({
            "adapter_kind": "embedding",
            "adapter_role": "multimodal",
            "dimensions": self.dimensions,
            "distance": "cosine",
            "modality": "multimodal",
            "model_or_tool_family": ADOPTED_MODEL_FAMILY,
            "model_version_pin": model_pin,
            "runtime_kind": "cloud",
            "spec_version": 1
        })
    }
}

impl<C: GeminiEmbeddingClient> EmbeddingAdapter for GeminiEmbeddingAdapter<C> {
    fn profile(&self) -> AdapterProfile {
        let profile = self.profile_value();
        AdapterProfile {
            adapter_kind: AdapterKind::Embedding,
            adapter_id: "gemini_embedding_2".to_owned(),
            execution_mode: ExecutionMode::OnlineApi,
            tool_profile_hash: tool_profile_hash(&profile)
                .expect("built-in Gemini embedding profile is valid"),
            version: env!("CARGO_PKG_VERSION").to_owned(),
            capability_flags: vec!["text".to_owned(), "multimodal".to_owned()],
            allow_network: true,
        }
    }

    fn embed(&self, request: EmbeddingRequest) -> Result<EmbeddingResponse> {
        let model_pin = self.client.resolve_model_pin(&self.configured_model)?;
        let vectors = self
            .client
            .embed(&request.items, &model_pin, self.dimensions)?;
        Ok(EmbeddingResponse {
            vectors,
            dimensions: self.dimensions,
            distance: "cosine".to_owned(),
            modality: "multimodal".to_owned(),
        })
    }
}

fn http_error(error: ureq::Error) -> AdapterError {
    match error {
        ureq::Error::Status(401 | 403, response) => AdapterError::Auth(format!(
            "Gemini embedding HTTP auth: {}",
            response.status_text()
        )),
        ureq::Error::Status(429, response) => AdapterError::RateLimit(format!(
            "Gemini embedding HTTP 429: {}",
            response.status_text()
        )),
        ureq::Error::Status(402, response) => AdapterError::QuotaExceeded(format!(
            "Gemini embedding HTTP quota: {}",
            response.status_text()
        )),
        ureq::Error::Status(code, response) => AdapterError::Network(format!(
            "Gemini embedding HTTP {code}: {}",
            response.status_text()
        )),
        ureq::Error::Transport(transport) => AdapterError::Network(transport.to_string()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::EmbeddingInputType;

    #[derive(Clone)]
    struct StubClient;

    impl GeminiEmbeddingClient for StubClient {
        fn resolve_model_pin(&self, _configured_model: &str) -> Result<String> {
            Ok(ADOPTED_MODEL_PIN.to_owned())
        }

        fn embed(
            &self,
            items: &[EmbeddingItem],
            _model_pin: &str,
            dimensions: u32,
        ) -> Result<Vec<EmbeddingVector>> {
            Ok(items
                .iter()
                .map(|item| EmbeddingVector {
                    id: item.id.clone(),
                    vector: vec![0.0; dimensions as usize],
                })
                .collect())
        }
    }

    #[test]
    fn adopted_profile_hash_matches_frozen_vector() {
        let adapter =
            GeminiEmbeddingAdapter::new(StubClient, ADOPTED_MODEL_PIN, ADOPTED_DIMENSIONS);
        assert_eq!(
            adapter.profile().tool_profile_hash,
            "sha256:66aff638f38a099ff989ca97675ebd3c573a40ee53cc1cdfe05fb06102d2bb09"
        );
        assert_eq!(adapter.profile().adapter_kind, AdapterKind::Embedding);
        assert!(adapter.profile().allow_network);
    }

    #[test]
    fn embed_returns_one_vector_per_item() {
        let adapter =
            GeminiEmbeddingAdapter::new(StubClient, ADOPTED_MODEL_PIN, ADOPTED_DIMENSIONS);
        let response = adapter
            .embed(EmbeddingRequest {
                input_type: EmbeddingInputType::MarkdownChunk,
                items: vec![
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
            })
            .unwrap();
        assert_eq!(response.vectors.len(), 2);
        assert_eq!(response.dimensions, 768);
        assert_eq!(response.distance, "cosine");
        assert_eq!(response.modality, "multimodal");
    }

    #[test]
    fn batch_embed_response_is_parsed_in_order() {
        let items = vec![
            EmbeddingItem {
                id: "x".to_owned(),
                text: Some("a".to_owned()),
                path: None,
                mime: None,
            },
            EmbeddingItem {
                id: "y".to_owned(),
                text: Some("b".to_owned()),
                path: None,
                mime: None,
            },
        ];
        let response = json!({
            "embeddings": [
                { "values": [1.0, 2.0] },
                { "values": [3.0, 4.0] }
            ]
        });
        let vectors = parse_embeddings(&response, &items, 2).unwrap();
        assert_eq!(vectors[0].id, "x");
        assert_eq!(vectors[0].vector, vec![1.0, 2.0]);
        assert_eq!(vectors[1].id, "y");
    }

    // F7: a response whose vector length disagrees with the requested dimension
    // must be rejected as a contract violation, not persisted (which would make
    // the chunk permanently invisible to KNN yet billed and marked done).
    #[test]
    fn embedding_wrong_dimension_is_contract_violation() {
        let items = vec![EmbeddingItem {
            id: "x".to_owned(),
            text: Some("a".to_owned()),
            path: None,
            mime: None,
        }];
        // 768 requested, but the backend returns a 5-element vector.
        let response = json!({
            "embeddings": [
                { "values": [0.0, 0.1, 0.2, 0.3, 0.4] }
            ]
        });
        let err = parse_embeddings(&response, &items, ADOPTED_DIMENSIONS).unwrap_err();
        assert!(
            matches!(err, AdapterError::ContractViolation(_)),
            "expected ContractViolation, got {err:?}"
        );
    }
}
