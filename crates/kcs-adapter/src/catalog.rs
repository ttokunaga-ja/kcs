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
    IncrementalHints, MarkdownizeMode, MarkdownizeRequest, MarkdownizeResponse, PreparedUnitHint,
    PreviousMarkdownizeContext, RawInput,
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
    standard_online_markdownize_profile_with_bbox(true)
}

#[must_use]
pub fn standard_online_markdownize_profile_with_bbox(enabled: bool) -> AdapterProfile {
    MistralOcrMarkdownizeAdapter::default()
        .with_bbox_annotation(enabled)
        .profile()
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
    // R13-1 + R14-4: incremental Markdownize on the online route. When `mode =
    // Incremental`, `prepared_unit_hints` carries ONLY the changed+added units and
    // `previous` / `hints` carry the prior instance + unit_mapping result. The Mistral
    // client turns those hints' 0-based `order`s into the OCR `pages` parameter so only
    // those pages are processed — before R14-4 the hint was IGNORED by the real client
    // and the whole document was re-sent/re-billed every revision (the "changed only"
    // claim held only under the mock seam). `Full` sends every unit and no `pages`
    // (`previous`/`hints` are `None`), the pre-R13-1 behavior. (Whether the `pages`
    // parameter actually lowers Mistral billing is confirmed by real-API verification,
    // a user-gated step; the code-side hint-ignoring defect is fixed here.)
    pub mode: MarkdownizeMode,
    pub previous: Option<PreviousMarkdownizeContext>,
    pub hints: Option<IncrementalHints>,
    /// R15-5: set on a UNIT-SCOPED retry (the `prepared_unit_hints` carry only the
    /// failed subset, but `mode` is `Full` with no previous/hints). Forwarded to the
    /// Mistral client so it OCRs/bills only those pages instead of the whole document.
    /// A fresh full send leaves this `false`.
    pub restrict_to_hint_pages: bool,
    pub bbox_annotation_enabled: bool,
}

pub struct StandardOnlineMarkdownizeOutcome {
    pub profile: AdapterProfile,
    pub response: MarkdownizeResponse,
    /// The complete unit set used by the adapter before any test-only response seam
    /// mutates the returned units. Fresh OCR-from-scratch requests have no caller
    /// hints, so this is how the provider-discovered page/image identities cross the
    /// adapter boundary and become the normalized manifest's Prepared units.
    pub effective_prepared_unit_hints: Vec<PreparedUnitHint>,
}

pub fn run_standard_online_markdownize(
    request: StandardOnlineMarkdownizeRequest<'_>,
) -> Result<StandardOnlineMarkdownizeOutcome> {
    let bytes = std::fs::read(request.path).map_err(|err| AdapterError::Io {
        path: request.path.display().to_string(),
        message: err.to_string(),
    })?;
    run_standard_online_markdownize_with_bytes(request, &bytes)
}

/// Execute online markdownization from bytes already owned by the caller. The
/// same verified buffer crosses the adapter boundary and is serialized into the
/// provider request; no pathname is reopened by the HTTP client.
pub fn run_standard_online_markdownize_with_bytes(
    request: StandardOnlineMarkdownizeRequest<'_>,
    verified_raw_bytes: &[u8],
) -> Result<StandardOnlineMarkdownizeOutcome> {
    let actual_hash = crate::identity::hash_bytes(verified_raw_bytes);
    if actual_hash != request.raw_hash {
        return Err(AdapterError::ContractViolation(format!(
            "online markdownize input identity changed: expected {}, got {actual_hash}",
            request.raw_hash
        )));
    }
    if request.prepared_unit_hints.is_empty() {
        // Discovery is only a fresh, whole-document operation. Reject unsupported
        // media and contradictory retry/incremental fields before constructing a real
        // client, so no document can be uploaded or billed before the contract error.
        if request.mode != MarkdownizeMode::Full
            || request.previous.is_some()
            || request.hints.is_some()
            || request.restrict_to_hint_pages
        {
            return Err(AdapterError::ContractViolation(
                "OCR-from-scratch requires a fresh unrestricted Full request".to_owned(),
            ));
        }
        if !supports_ocr_from_scratch(request.media_type) {
            return Err(AdapterError::ContractViolation(format!(
                "OCR-from-scratch media type is unsupported: {}",
                request.media_type
            )));
        }
    }
    let requested_prepared_unit_hints = request.prepared_unit_hints.clone();
    let prepared_unit_hint =
        (!request.prepared_unit_hints.is_empty()).then_some(request.prepared_unit_hints);
    let adapter_request = MarkdownizeRequest {
        raw: RawInput {
            raw_hash: request.raw_hash.to_owned(),
            path: Some(request.path.display().to_string()),
        },
        media_type: request.media_type.to_owned(),
        // An empty local Prepare result is meaningful for scanned PDFs and images:
        // the online OCR adapter must discover the page/unit set
        // from the provider response. Preserve that distinction as `None`; `Some([])`
        // previously forced the hint-driven path to return zero units forever.
        prepared_unit_hint,
        // R13-1: forward the caller-computed mode/previous/hints (was hard-coded
        // Full/None/None, which is why incremental never fired on the online route).
        mode: request.mode,
        previous: request.previous,
        hints: request.hints,
        // R15-5: forward the retry page-scoping signal to the real client.
        restrict_to_hint_pages: request.restrict_to_hint_pages,
        bbox_annotation_enabled: request.bbox_annotation_enabled,
        tool_profile_hash: String::new(),
        spec_version: 1,
    };
    match std::env::var(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV)
        .ok()
        .as_deref()
    {
        Some("auth_error") => return Err(AdapterError::Auth("mock auth failure".to_owned())),
        Some("rate_limit") => return Err(AdapterError::rate_limit("mock 429")),
        // QA3 (step4b-contract-tests-p3a.md §A, 04 §5.3): a rate limit WITH a
        // provider `Retry-After` header (30s), proving `retry_after_ms`
        // wiring end-to-end into `next_retry_at` — unlike the headerless
        // "rate_limit" seam above, which exercises the synthetic +2s
        // fallback.
        Some("rate_limit_after") => {
            return Err(AdapterError::RateLimit {
                message: "mock 429".to_owned(),
                retry_after_ms: Some(30_000),
            })
        }
        // R16-7: a retryable NetworkError (mapped from `AdapterError::Network`) — unlike
        // rate_limit it may have been billed server-side, so each retry re-reserves.
        Some("network_error") => {
            return Err(AdapterError::Network("mock network failure".to_owned()))
        }
        // R13-1: `incr_incomplete` simulates an OCR response that drops a requested
        // unit ONLY in incremental mode (a full re-send returns everything), so the
        // KCS-side acceptance check fails and the online route falls back to Full.
        Some("mock")
        | Some("partial")
        | Some("mock_link_image")
        | Some("incr_incomplete")
        | Some("pin_changed")
        | Some("no_change_no_send") => {
            let client = MockStandardOnlineMarkdownizeClient;
            let model_pin = client.resolve_model_pin("mistral-ocr-latest")?;
            let adapter = MistralOcrMarkdownizeAdapter::new(client, model_pin, request.scope_id)
                .with_image_store(request.kcs_dir)
                .with_bbox_annotation(request.bbox_annotation_enabled)
                .with_verified_raw_bytes(verified_raw_bytes.to_vec());
            let profile = adapter.profile();
            let mut adapter_request = adapter_request;
            adapter_request.tool_profile_hash = profile.tool_profile_hash.clone();
            let response_mode = adapter_request.mode;
            let mut response = adapter.markdownize(adapter_request)?;
            // Capture the complete discovered/requested unit set before the partial
            // response seams remove an output. Otherwise a simulated missing page would
            // disappear from the manifest instead of remaining a retryable Failed unit.
            let effective_prepared_unit_hints = effective_prepared_unit_hints(
                &requested_prepared_unit_hints,
                request.raw_hash,
                &response,
            )?;
            // Test-only KCS response seams run after the provider page mapping has
            // passed its exact-bijection checks. This preserves partial/fallback
            // lifecycle coverage without weakening the OCR transport contract.
            if std::env::var(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV)
                .ok()
                .as_deref()
                == Some("partial")
            {
                response.updated_units.pop();
            }
            if std::env::var(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV)
                .ok()
                .as_deref()
                == Some("incr_incomplete")
                && response_mode == MarkdownizeMode::Incremental
                && response.updated_units.len() > 1
            {
                response.updated_units.pop();
            }
            return Ok(StandardOnlineMarkdownizeOutcome {
                profile,
                response,
                effective_prepared_unit_hints,
            });
        }
        _ => {}
    }
    let client = EnvMistralOcrClient::new();
    // R13-2: use the declared `tools.toml` `[markdown] model` alias when present
    // (docs/03 §11: config may carry a mutable alias, resolved to an immutable pin
    // at execution — §5.1/§6), rather than the previously hard-coded
    // `"mistral-ocr-latest"`.
    let configured_model = declared_markdown_model()?;
    let model_pin = client.resolve_model_pin(&configured_model)?;
    let adapter = MistralOcrMarkdownizeAdapter::new(client, model_pin, request.scope_id)
        .with_image_store(request.kcs_dir)
        .with_bbox_annotation(request.bbox_annotation_enabled)
        .with_verified_raw_bytes(verified_raw_bytes.to_vec());
    let profile = adapter.profile();
    let mut adapter_request = adapter_request;
    adapter_request.tool_profile_hash = profile.tool_profile_hash.clone();
    let response = adapter.markdownize(adapter_request)?;
    let effective_prepared_unit_hints =
        effective_prepared_unit_hints(&requested_prepared_unit_hints, request.raw_hash, &response)?;
    Ok(StandardOnlineMarkdownizeOutcome {
        profile,
        response,
        effective_prepared_unit_hints,
    })
}

fn supports_ocr_from_scratch(media_type: &str) -> bool {
    matches!(
        media_type,
        "application/pdf" | "image/png" | "image/jpeg" | "image/webp" | "image/gif"
    )
}

fn effective_prepared_unit_hints(
    requested: &[PreparedUnitHint],
    raw_hash: &str,
    response: &MarkdownizeResponse,
) -> Result<Vec<PreparedUnitHint>> {
    if !requested.is_empty() {
        return Ok(requested.to_vec());
    }
    if response.mode_used != crate::types::MarkdownizeMode::Full {
        return Err(AdapterError::ContractViolation(
            "OCR-from-scratch requires Full markdownize mode".to_owned(),
        ));
    }
    let mut seen = std::collections::BTreeSet::new();
    let hints = response
        .updated_units
        .iter()
        .chain(response.added_units.iter())
        .enumerate()
        .map(|(index, unit)| {
            if !seen.insert(unit.unit_key.clone()) {
                return Err(AdapterError::ContractViolation(
                    "OCR-from-scratch returned duplicate unit keys".to_owned(),
                ));
            }
            let order = u64::try_from(index).map_err(|_| {
                AdapterError::ContractViolation(
                    "OCR-from-scratch unit count exceeds the supported order".to_owned(),
                )
            })?;
            Ok(PreparedUnitHint {
                unit_key: unit.unit_key.clone(),
                prepared_hash: raw_hash.to_owned(),
                unit_kind: unit.unit_type,
                order,
            })
        })
        .collect::<Result<Vec<_>>>()?;
    if hints.is_empty() {
        return Err(AdapterError::ContractViolation(
            "OCR-from-scratch returned no units".to_owned(),
        ));
    }
    Ok(hints)
}

/// R13-2: the configured `[markdown] model` alias (or the built-in `mistral-ocr-latest`),
/// resolved to an immutable pin at execution. Shared by the send path and the
/// resolve-only profile path (R14-6) so both agree on the model.
fn declared_markdown_model() -> Result<String> {
    let declared = crate::tool_lock::registered_declared_adapter("markdown");
    if let Some(declared) = declared.as_ref() {
        crate::tool_lock::validate_declared_runtime_target("markdown", declared)?;
    }
    Ok(declared
        .and_then(|declared| declared.model)
        .unwrap_or_else(|| "mistral-ocr-latest".to_owned()))
}

/// R14-6: resolve the online markdownize adapter's profile (its `tool_profile_hash`)
/// WITHOUT sending an OCR request. Resolving the model pin may hit the network (a
/// `GET /v1/models` to expand a `*-latest` alias) but never uploads the document or bills
/// OCR. The incremental gate compares this *resolved* profile against the prior instance
/// BEFORE deciding to send: a changed pin is a different tool_profile, which is not an
/// eligible incremental (docs/04 §3.1 condition 2), so KCS must fall straight to a Full
/// send instead of wasting an incremental send (and, post-R14-4, a full-document upload)
/// only to discard it. Keep the seam arms in sync with `run_standard_online_markdownize`.
pub fn resolve_standard_online_markdownize_profile(scope_id: &str) -> Result<AdapterProfile> {
    resolve_standard_online_markdownize_profile_with_bbox(scope_id, true)
}

pub fn resolve_standard_online_markdownize_profile_with_bbox(
    scope_id: &str,
    bbox_annotation_enabled: bool,
) -> Result<AdapterProfile> {
    match std::env::var(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV)
        .ok()
        .as_deref()
    {
        Some("auth_error") => return Err(AdapterError::Auth("mock auth failure".to_owned())),
        Some("rate_limit") => return Err(AdapterError::rate_limit("mock 429")),
        // QA3: keep the seam arms in sync with `run_standard_online_markdownize`.
        Some("rate_limit_after") => {
            return Err(AdapterError::RateLimit {
                message: "mock 429".to_owned(),
                retry_after_ms: Some(30_000),
            })
        }
        // R16-7: keep the seam arms in sync with `run_standard_online_markdownize`.
        Some("network_error") => {
            return Err(AdapterError::Network("mock network failure".to_owned()))
        }
        Some("mock")
        | Some("partial")
        | Some("mock_link_image")
        | Some("incr_incomplete")
        | Some("pin_changed")
        | Some("no_change_no_send") => {
            let client = MockStandardOnlineMarkdownizeClient;
            let model_pin = client.resolve_model_pin("mistral-ocr-latest")?;
            return Ok(
                MistralOcrMarkdownizeAdapter::new(client, model_pin, scope_id)
                    .with_bbox_annotation(bbox_annotation_enabled)
                    .profile(),
            );
        }
        _ => {}
    }
    let client = EnvMistralOcrClient::new();
    let model_pin = client.resolve_model_pin(&declared_markdown_model()?)?;
    Ok(
        MistralOcrMarkdownizeAdapter::new(client, model_pin, scope_id)
            .with_bbox_annotation(bbox_annotation_enabled)
            .profile(),
    )
}

#[derive(Debug, Clone)]
struct MockStandardOnlineMarkdownizeClient;

impl MistralOcrClient for MockStandardOnlineMarkdownizeClient {
    fn resolve_model_pin(&self, _configured_model: &str) -> Result<String> {
        // R14-6: the `pin_changed` seam simulates a model-pin change between runs so the
        // incremental gate sees a resolved tool_profile different from the prior instance
        // (which was created under the default `mistral-ocr-2505`).
        if std::env::var(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV)
            .ok()
            .as_deref()
            == Some("pin_changed")
        {
            return Ok("mistral-ocr-2599".to_owned());
        }
        Ok("mistral-ocr-2505".to_owned())
    }

    fn ocr_markdown(
        &self,
        request: &MarkdownizeRequest,
        model_pin: &str,
        _verified_raw_bytes: &[u8],
    ) -> Result<OcrResponse> {
        // R14-6: under `pin_changed`, an INCREMENTAL send must never reach the adapter —
        // the gate resolves the changed pin first and falls back to Full. If one is
        // attempted (a regression that sends before gating), fail loudly so the test
        // catches it. A Full send under the same seam is the expected fallback and works.
        if std::env::var(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV)
            .ok()
            .as_deref()
            == Some("pin_changed")
            && request.mode == crate::types::MarkdownizeMode::Incremental
        {
            return Err(AdapterError::ContractViolation(
                "R14-6: incremental OCR sent after a model-pin change (gate missing)".to_owned(),
            ));
        }
        // R15-6: under `no_change_no_send`, a 0-change incremental must reuse every unit
        // KCS-side WITHOUT reaching the adapter (there is no page to OCR). Unlike
        // `pin_changed`, the model pin is left stable so incremental actually FIRES (the
        // gate passes) — the only incremental send this seam sees is the regression it
        // guards. Fail loudly so the test catches any send.
        if std::env::var(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV)
            .ok()
            .as_deref()
            == Some("no_change_no_send")
            && request.mode == crate::types::MarkdownizeMode::Incremental
        {
            return Err(AdapterError::ContractViolation(
                "R15-6: a 0-change incremental reached the adapter (should reuse without sending)"
                    .to_owned(),
            ));
        }
        let discovered = request
            .prepared_unit_hint
            .as_deref()
            .is_none_or(<[_]>::is_empty);
        let discovered_hint = crate::types::PreparedUnitHint {
            unit_key: "discovered:1".to_owned(),
            prepared_hash: request.raw.raw_hash.clone(),
            unit_kind: crate::types::UnitKind::Page,
            order: 0,
        };
        let hints = if discovered {
            std::slice::from_ref(&discovered_hint)
        } else {
            request.prepared_unit_hint.as_deref().unwrap_or(&[])
        };
        let pages: Vec<OcrPage> = hints
            .iter()
            .map(|hint| {
                // R11-6: index each returned page by the unit's DOCUMENT order
                // (`hint.order`), not its position in the hint list, so a
                // unit-scoped retry (a subset of hints) maps back correctly — the
                // adapter looks pages up by `hint.order` (mistral_ocr.rs). The real
                // OCR API likewise returns pages at their document indices. For a
                // full send `order` == list position, so this is unchanged.
                let index = hint.order as usize;
                OcrPage {
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
                        annotation: request.bbox_annotation_enabled.then(|| {
                            let text = format!(
                                "KCS bbox label {} value 1000",
                                hint.unit_key
                            );
                            crate::bbox_annotation::BboxAnnotation {
                                short_description: "mock chart".to_owned(),
                                transcribed_text:
                                    crate::bbox_annotation::canonical_source_escape(&text),
                            }
                        }),
                    }],
                }
            })
            .collect();
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
    /// QA3 (step4b-contract-tests-p3a.md §A, 04 §5.3): a rate limit WITH a
    /// provider `Retry-After` header (30s) — proves `retry_after_ms` wiring
    /// into `next_retry_at`, unlike `RateLimit` above (headerless, synthetic
    /// +2s backoff).
    RateLimitAfter,
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
        Some("rate_limit_after") => Some(AdoptedEmbeddingExecution::RateLimitAfter),
        Some(_) => None,
        // R13-2: activate the Real path when EITHER a `tools.toml` `[embedding]`
        // adapter is declared (its auth is resolved at execution — keychain there
        // is a loud error) OR the legacy `GEMINI_API_KEY` env var is set. Before
        // this a declared `auth = "env:MY_KEY"` was ignored (silent noop) because
        // only `GEMINI_API_KEY` was checked.
        None => real_embedding_activation(
            crate::tool_lock::registered_declared_adapter("embedding")
                .and_then(|declared| declared.auth)
                .is_some(),
            std::env::var("GEMINI_API_KEY").is_ok(),
        ),
    }
}

/// R13-2: pure activation rule for the adopted embedding adapter (unit-testable).
/// Real when the adapter is declared in `tools.toml` OR the legacy env key is set.
#[must_use]
pub fn real_embedding_activation(
    declared: bool,
    env_key_present: bool,
) -> Option<AdoptedEmbeddingExecution> {
    (declared || env_key_present).then_some(AdoptedEmbeddingExecution::Real)
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
        AdoptedEmbeddingExecution::Real => {
            let declared = crate::tool_lock::registered_declared_adapter("embedding");
            if let Some(declared) = declared.as_ref() {
                crate::tool_lock::validate_declared_runtime_target("embedding", declared)?;
            }
            let configured_model = declared
                .and_then(|declared| declared.model)
                .unwrap_or_else(|| ADOPTED_MODEL_PIN.to_owned());
            GeminiEmbeddingAdapter::new(
                crate::gemini_embedding::EnvGeminiEmbeddingClient::new(),
                configured_model,
                ADOPTED_DIMENSIONS,
            )
            .embed(request)
        }
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
                return Err(AdapterError::rate_limit("mock 429"))
            }
            AdoptedEmbeddingExecution::RateLimitAfter => {
                return Err(AdapterError::RateLimit {
                    message: "mock 429".to_owned(),
                    retry_after_ms: Some(30_000),
                })
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

    static MARKDOWNIZE_ENV_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

    #[test]
    fn adopted_profiles_are_catalog_owned() {
        assert_eq!(builtin_prepare_profile().adapter_id, "prepare_default");
        assert_eq!(
            standard_online_markdownize_profile().adapter_id,
            "mistral_ocr_markdownize"
        );
        assert_eq!(adopted_embedding_profile().adapter_id, "gemini_embedding_2");
    }

    // R13-2(d): a declared `[embedding]` adapter activates the Real path even
    // without GEMINI_API_KEY (the finding: a declared `auth = "env:MY_KEY"` used to
    // be ignored). The legacy env-only activation still works too.
    #[test]
    fn r13_2_real_embedding_activation_honors_declaration_or_env() {
        assert_eq!(
            real_embedding_activation(true, false),
            Some(AdoptedEmbeddingExecution::Real),
            "a declared adapter activates without the env key"
        );
        assert_eq!(
            real_embedding_activation(false, true),
            Some(AdoptedEmbeddingExecution::Real),
            "the legacy env-only activation still works"
        );
        assert_eq!(
            real_embedding_activation(false, false),
            None,
            "neither declared nor env → inactive"
        );
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
            Err(AdapterError::RateLimit { .. })
        ));
    }

    #[test]
    fn standard_online_markdownize_mock_runs() {
        let _env_lock = MARKDOWNIZE_ENV_LOCK.lock().unwrap();
        let temp = tempfile::tempdir().unwrap();
        let input = temp.path().join("input.pdf");
        let input_bytes = b"%PDF mock";
        std::fs::write(&input, input_bytes).unwrap();
        let input_hash = crate::identity::hash_bytes(input_bytes);
        std::env::set_var(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "mock");
        let outcome = run_standard_online_markdownize(StandardOnlineMarkdownizeRequest {
            scope_id: "01H00000000000000000000000",
            kcs_dir: temp.path(),
            raw_hash: &input_hash,
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
            mode: MarkdownizeMode::Full,
            previous: None,
            hints: None,
            restrict_to_hint_pages: false,
            bbox_annotation_enabled: false,
        })
        .unwrap();
        std::env::remove_var(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV);
        assert_eq!(outcome.profile.adapter_kind, AdapterKind::Markdownize);
        assert_eq!(outcome.response.updated_units.len(), 1);

        // A test-only missing output must not shrink the Prepared manifest. Capture
        // the complete provider-discovered set before the seam removes page:1.
        std::env::set_var(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "partial");
        let partial = run_standard_online_markdownize(StandardOnlineMarkdownizeRequest {
            scope_id: "01H00000000000000000000000",
            kcs_dir: temp.path(),
            raw_hash: &input_hash,
            path: &input,
            media_type: "application/pdf",
            prepared_unit_hints: Vec::new(),
            mode: MarkdownizeMode::Full,
            previous: None,
            hints: None,
            restrict_to_hint_pages: false,
            bbox_annotation_enabled: false,
        })
        .unwrap();
        std::env::remove_var(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV);
        assert!(partial.response.updated_units.is_empty());
        assert_eq!(partial.effective_prepared_unit_hints.len(), 1);
        assert_eq!(partial.effective_prepared_unit_hints[0].unit_key, "page:1");
        assert_eq!(
            partial.effective_prepared_unit_hints[0].prepared_hash,
            input_hash
        );
    }

    #[test]
    fn ct4_bbox_003_and_006_catalog_mock_persists_profile_metadata_and_search_text() {
        let _env_lock = MARKDOWNIZE_ENV_LOCK.lock().unwrap();
        let temp = tempfile::tempdir().unwrap();
        let input = temp.path().join("chart.pdf");
        let input_bytes = b"%PDF bbox mock";
        std::fs::write(&input, input_bytes).unwrap();
        let input_hash = crate::identity::hash_bytes(input_bytes);
        std::env::set_var(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "mock");
        let outcome = run_standard_online_markdownize(StandardOnlineMarkdownizeRequest {
            scope_id: "01H00000000000000000000000",
            kcs_dir: temp.path(),
            raw_hash: &input_hash,
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
            mode: MarkdownizeMode::Full,
            previous: None,
            hints: None,
            restrict_to_hint_pages: false,
            bbox_annotation_enabled: true,
        })
        .unwrap();
        std::env::remove_var(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV);

        assert_eq!(
            outcome.profile.tool_profile_hash,
            "sha256:830c45cada7e9ea8c6f6816579fa0493645208626201181f3763b4bc6bddda3e"
        );
        let unit = &outcome.response.updated_units[0];
        assert!(unit.markdown.contains(r"KCS bbox label page\:1 value 1000"));
        assert_eq!(
            unit.metadata["bbox_annotations"][0]["transcribed_text"],
            "KCS bbox label page\\:1 value 1000"
        );
        let images = temp.path().join("objects/image");
        assert!(
            images.exists(),
            "mock image bytes remain persisted in image CAS"
        );
    }

    #[test]
    fn ct4_bbox_001_catalog_default_is_enabled_and_disabled_preserves_old_identity() {
        assert_eq!(
            standard_online_markdownize_profile().tool_profile_hash,
            standard_online_markdownize_profile_with_bbox(true).tool_profile_hash
        );
        assert_ne!(
            standard_online_markdownize_profile().tool_profile_hash,
            standard_online_markdownize_profile_with_bbox(false).tool_profile_hash
        );
    }
}
