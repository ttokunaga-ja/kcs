//! The `offline_api` embedding adapter — a local multimodal embedding server
//! reached over loopback (07 §5.3, 07 §3's D1 url restriction).
//!
//! # What is here, and what is not
//!
//! Only the **mock** implementation ships today. The wire format is settled in
//! principle — 07 §5.3 mandates chat-form `messages` for every call, text-only
//! ones included, because a server's plain-`input` path tokenizes the same
//! characters differently and would split one declared profile across two
//! vector spaces that [03 §7]'s compatibility gate cannot tell apart. What is
//! *not* settled is the chat template and task instruction themselves, and
//! those are folded into `prompt_template_hash`, i.e. into the profile identity.
//!
//! Shipping a real client before that value is measured would mint vectors
//! under a placeholder identity, and correcting the identity afterwards means
//! re-embedding everything already stored — the exact cost the profile hash
//! exists to make visible. So a declared local adapter with no test seam is a
//! loud `NotImplemented` rather than a guess.
//!
//! The mock is not a placeholder for that work: it is how the offline path's
//! *semantics* (no consent gate, no ledger charge, no batch lane) are exercised
//! in CI, which has no GPU and never will.

use serde_json::{json, Value};

use crate::catalog::deterministic_embedding_vector;
use crate::identity::tool_profile_hash;
use crate::traits::EmbeddingAdapter;
use crate::types::{
    validate_cosine_vector, AdapterKind, AdapterProfile, EmbeddingRequest, EmbeddingResponse,
    EmbeddingVector, ExecutionMode,
};
use crate::{AdapterError, Result};

/// The `tool_id` the local embedding target is declared under in `tools.toml`
/// (see `tool_lock::EMBEDDING_RUNTIME_TARGETS`).
pub const LOCAL_EMBEDDING_ADAPTER_ID: &str = "qwen3_vl_embedding_local";
pub const LOCAL_EMBEDDING_MODEL_FAMILY: &str = "qwen3-vl-embedding";

/// 04 §4.3: `chunk_vec` is `float[768]`, so a local model is MRL-truncated to
/// the same width. A different width would produce vectors vector search
/// cannot read.
pub const LOCAL_EMBEDDING_DIMENSIONS: u32 = 768;

/// Declared by an embedding adapter that genuinely embeds image OBJECTS — i.e.
/// one that reads `EmbeddingItem::path`/`mime` rather than only `text`.
///
/// `modality: "multimodal"` does not answer this. It describes the vector
/// space (03 §7 fixes one space for every modality), not what a given
/// implementation can be handed. The adopted online adapter declares multimodal
/// and reads only `text`, so it must not be given image items until that
/// changes — at which point adding this flag is the whole of turning it on.
pub const IMAGE_OBJECT_CAPABILITY: &str = "image_object";

/// Selects which local implementation runs. `Mock` is the only one that exists;
/// see the module docs for why the real one waits on a measured chat template.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LocalEmbeddingExecution {
    Mock,
}

/// The `offline_api` embedding adapter.
pub struct LocalEmbeddingAdapter {
    execution: LocalEmbeddingExecution,
    dimensions: u32,
}

impl LocalEmbeddingAdapter {
    #[must_use]
    pub fn new(execution: LocalEmbeddingExecution) -> Self {
        Self {
            execution,
            dimensions: LOCAL_EMBEDDING_DIMENSIONS,
        }
    }

    /// The profile JSON `tool_profile_hash` is taken over (03 §5.1).
    ///
    /// `runtime_kind` is `"local"` and carries no serving backend: 07 §5.3
    /// forbids naming one here, so that the same weights served two ways stay
    /// one profile and a backend swap costs no re-embed.
    #[must_use]
    pub fn profile_value(&self) -> Value {
        json!({
            "adapter_kind": "embedding",
            "adapter_role": "multimodal",
            "dimensions": self.dimensions,
            "distance": "cosine",
            // Same chunk-input construction as the online adapter: the
            // humanized filename is prepended before embedding, which is part
            // of what a vector MEANS and therefore of this identity.
            "input_construction": "chunk_filename_context_v1",
            "modality": "multimodal",
            "model_or_tool_family": LOCAL_EMBEDDING_MODEL_FAMILY,
            // 03 §5.1: a weight-bearing local adapter pins the sha256 of the
            // weights, not a tag — quantization variants share tag names. The
            // mock has no weights, so it pins its own identity instead of
            // borrowing a real model's and minting vectors under it.
            "model_version_pin": "kio-local-embedding-mock-1.0.0",
            "runtime_kind": "local",
            "spec_version": 1
        })
    }
}

impl EmbeddingAdapter for LocalEmbeddingAdapter {
    fn profile(&self) -> AdapterProfile {
        let profile = self.profile_value();
        AdapterProfile {
            adapter_kind: AdapterKind::Embedding,
            adapter_id: LOCAL_EMBEDDING_ADAPTER_ID.to_owned(),
            execution_mode: ExecutionMode::OfflineApi,
            tool_profile_hash: tool_profile_hash(&profile)
                .expect("built-in local embedding profile is valid"),
            version: env!("CARGO_PKG_VERSION").to_owned(),
            // `image_object` is the flag the index path gates image enrichment
            // on. It says this implementation actually reads an item's
            // `path`/`mime`, which is not something `modality: "multimodal"`
            // implies — the adopted online adapter declares multimodal and then
            // reads only `text`, so handing it an image item would embed the
            // empty string and store a confidently wrong vector. Capability
            // flags are outside `PROFILE_FIELDS`, so this does not perturb the
            // profile hash (qa35 pins that `capabilities` are not hashed).
            capability_flags: vec![
                "text".to_owned(),
                "multimodal".to_owned(),
                IMAGE_OBJECT_CAPABILITY.to_owned(),
            ],
            // 07 §3: an offline_api adapter reaches loopback only, which is why
            // it is exempt from the §3 consent gate. This flag is what the
            // exemption keys off, so it must stay false.
            allow_network: false,
            // Nothing to bill: the model runs on hardware the user already has.
            // An empty set is also what stops the ledger from reserving and
            // settling against a price that does not exist.
            billable_kinds: Vec::new(),
            reject_billing: None,
            provider_idempotency: crate::types::ProviderIdempotency::NotProvided,
        }
    }

    fn embed(&self, request: EmbeddingRequest) -> Result<EmbeddingResponse> {
        let LocalEmbeddingExecution::Mock = self.execution;
        let vectors = request
            .items
            .iter()
            .map(|item| EmbeddingVector {
                id: item.id.clone(),
                // An image item carries no `text`; seeding on the empty string
                // would give every image in a corpus the same vector, and
                // vector search would rank them all identically. The id of an
                // image item is its content hash, so it distinguishes images
                // exactly as far as their bytes do.
                vector: deterministic_embedding_vector(
                    item.text.as_deref().unwrap_or(item.id.as_str()),
                    self.dimensions as usize,
                ),
            })
            .collect::<Vec<_>>();
        // 07 §5.3 acceptance checks (1)-(3): one vector per input, in order,
        // each of the declared width and usable as a cosine operand. The mock
        // satisfies these by construction, but running them here means the
        // checks are exercised on this path too rather than only on Gemini's.
        if vectors.len() != request.items.len() {
            return Err(AdapterError::ContractViolation(
                "local embedding returned a different number of vectors than inputs".to_owned(),
            ));
        }
        for (vector, item) in vectors.iter().zip(&request.items) {
            if vector.id != item.id {
                return Err(AdapterError::ContractViolation(
                    "local embedding returned vectors out of input order".to_owned(),
                ));
            }
            validate_cosine_vector(&vector.vector, self.dimensions)?;
        }
        Ok(EmbeddingResponse {
            vectors,
            dimensions: self.dimensions,
            distance: "cosine".to_owned(),
            modality: "multimodal".to_owned(),
            embedding_profile_hash: Some(self.profile().tool_profile_hash),
            // No token accounting: there is no provider and no invoice. The
            // ledger path reads `billable_kinds` (empty, above) and skips.
            usage: None,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::{EmbeddingInputType, EmbeddingItem};

    fn request(texts: &[&str]) -> EmbeddingRequest {
        EmbeddingRequest {
            input_type: EmbeddingInputType::MarkdownChunk,
            items: texts
                .iter()
                .enumerate()
                .map(|(index, text)| EmbeddingItem {
                    id: format!("item-{index}"),
                    text: Some((*text).to_owned()),
                    path: None,
                    mime: None,
                })
                .collect(),
            idempotency_token: None,
        }
    }

    #[test]
    fn profile_declares_the_offline_posture() {
        let profile = LocalEmbeddingAdapter::new(LocalEmbeddingExecution::Mock).profile();
        assert_eq!(profile.execution_mode, ExecutionMode::OfflineApi);
        assert_eq!(profile.adapter_id, LOCAL_EMBEDDING_ADAPTER_ID);
        // The three properties the offline forks key off (07 §3 / 07 §5.7).
        assert!(!profile.allow_network, "offline_api must not claim network");
        assert!(
            profile.billable_kinds.is_empty(),
            "a local model has nothing to bill"
        );
        assert!(profile.reject_billing.is_none());
    }

    /// The flag that gates image enrichment. The local adapter reads an item's
    /// `path`/`mime`; the adopted online one does not, and declaring
    /// `multimodal` is not the same claim.
    #[test]
    fn declares_the_image_object_capability_that_the_online_adapter_does_not() {
        let local = LocalEmbeddingAdapter::new(LocalEmbeddingExecution::Mock).profile();
        assert!(local
            .capability_flags
            .iter()
            .any(|flag| flag == IMAGE_OBJECT_CAPABILITY));
        let online = crate::catalog::adopted_embedding_profile();
        assert!(
            !online
                .capability_flags
                .iter()
                .any(|flag| flag == IMAGE_OBJECT_CAPABILITY),
            "the online adapter reads only `text`; claiming this flag would have \
             it embed the empty string for every image"
        );
    }

    /// An image item has no `text`. Seeding on the empty string would collapse
    /// every image in a corpus onto one vector.
    #[test]
    fn image_items_embed_distinctly_without_text() {
        let adapter = LocalEmbeddingAdapter::new(LocalEmbeddingExecution::Mock);
        let items = ["sha256:aaa", "sha256:bbb"]
            .iter()
            .map(|hash| EmbeddingItem {
                id: (*hash).to_owned(),
                text: None,
                path: Some(format!("/cache/{hash}")),
                mime: Some("image/png".to_owned()),
            })
            .collect::<Vec<_>>();
        let response = adapter
            .embed(EmbeddingRequest {
                input_type: EmbeddingInputType::ImageObject,
                items,
                idempotency_token: None,
            })
            .unwrap();
        assert_eq!(response.vectors.len(), 2);
        assert_ne!(response.vectors[0].vector, response.vectors[1].vector);
        for vector in &response.vectors {
            validate_cosine_vector(&vector.vector, LOCAL_EMBEDDING_DIMENSIONS).unwrap();
        }
    }

    /// 07 §5.3: the serving backend must not appear anywhere in the hashed
    /// profile, so that the same weights served two ways stay one vector space
    /// and a backend swap does not force a re-embed.
    #[test]
    fn profile_identity_names_no_serving_backend() {
        let value = LocalEmbeddingAdapter::new(LocalEmbeddingExecution::Mock).profile_value();
        let rendered = value.to_string().to_ascii_lowercase();
        for backend in ["vllm", "sglang", "llama.cpp", "llamacpp", "ollama", "mlx"] {
            assert!(
                !rendered.contains(backend),
                "profile identity must not name `{backend}`: {rendered}"
            );
        }
        assert_eq!(value["runtime_kind"], "local");
    }

    /// 03 §7 / 07 §5.3: the local profile is a DIFFERENT vector space from the
    /// online one. The compatibility gate must be able to tell them apart, and
    /// it only has the profile hash to do it with.
    #[test]
    fn local_profile_hash_differs_from_the_online_one() {
        let local = LocalEmbeddingAdapter::new(LocalEmbeddingExecution::Mock).profile();
        let online = crate::catalog::adopted_embedding_profile();
        assert_ne!(local.tool_profile_hash, online.tool_profile_hash);
        // Same width and metric, though — `chunk_vec` is one table (04 §4.3),
        // so a swap is a re-embed and not a schema migration.
        assert_eq!(LOCAL_EMBEDDING_DIMENSIONS, 768);
    }

    #[test]
    fn embed_returns_one_usable_vector_per_input_in_order() {
        let adapter = LocalEmbeddingAdapter::new(LocalEmbeddingExecution::Mock);
        let response = adapter.embed(request(&["alpha", "beta", "gamma"])).unwrap();
        assert_eq!(response.vectors.len(), 3);
        assert_eq!(response.dimensions, LOCAL_EMBEDDING_DIMENSIONS);
        assert_eq!(response.distance, "cosine");
        assert_eq!(response.modality, "multimodal");
        assert_eq!(
            response.embedding_profile_hash.as_deref(),
            Some(adapter.profile().tool_profile_hash.as_str())
        );
        for (index, vector) in response.vectors.iter().enumerate() {
            assert_eq!(vector.id, format!("item-{index}"));
            validate_cosine_vector(&vector.vector, LOCAL_EMBEDDING_DIMENSIONS).unwrap();
        }
        // Distinct inputs must not collapse onto one vector, or vector search
        // would rank every chunk identically.
        assert_ne!(response.vectors[0].vector, response.vectors[1].vector);
    }

    #[test]
    fn embed_reports_no_usage_because_there_is_no_invoice() {
        let response = LocalEmbeddingAdapter::new(LocalEmbeddingExecution::Mock)
            .embed(request(&["alpha"]))
            .unwrap();
        assert!(response.usage.is_none());
    }

    /// 07 §5.7: no batch lane. A local server has no job queue to submit to,
    /// and the half-price rationale that puts Gemini on Batch does not exist.
    #[test]
    fn prefers_the_sync_lane() {
        use crate::traits::PreferredRequestKind;
        assert_eq!(
            LocalEmbeddingAdapter::new(LocalEmbeddingExecution::Mock).preferred_request_kind(),
            PreferredRequestKind::Sync
        );
    }
}
