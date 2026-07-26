//! Adapter request and response contracts.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AdapterKind {
    Prepare,
    Markdownize,
    Embedding,
    Summary,
    Classification,
    Rerank,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ExecutionMode {
    OnlineApi,
    OfflineApi,
    DeterministicLibrary,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AdapterRunStatus {
    Pending,
    Running,
    Done,
    Partial,
    Failed,
}

/// QA18 (step4b-contract-tests-p3a.md §F): the closed `usage.billable_units[].kind`
/// enum (07 §4 L294) — extension is a spec revision, not adapter-declared.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BillableUnitKind {
    Pages,
    TokensIn,
    TokensOut,
}

/// QA18: "billable" | "nonbillable" (07 §4 L270-275). Whether a billable
/// Adapter's provider charges for a permanent-4xx submission rejection.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BillingDeclaration {
    Billable,
    Nonbillable,
}

/// QA13 (step4b-contract-tests-p3a.md §E, 04 §5.5 L880): whether this
/// adapter's provider offers a request-level idempotency mechanism for a
/// SYNC call. `HttpHeader(name)` names the HTTP header a caller must set to
/// request it; `NotProvided` is the common case — neither built-in adapter's
/// pinned endpoint offers one (04 §5.5: "job 作成に idempotency key の無い
/// provider が現実"), so dedup rests solely on the ledger's own §5.4/§5.8
/// 2-phase (`batch_requests` row) protocol. This is a declaration of what the
/// PROVIDER offers, never a blanket Adapter-layer requirement (04 §5.5:
/// "Adapter 層への idempotency_key 一律要求はしない").
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum ProviderIdempotency {
    #[default]
    NotProvided,
    HttpHeader(String),
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AdapterProfile {
    pub adapter_kind: AdapterKind,
    pub adapter_id: String,
    pub execution_mode: ExecutionMode,
    pub tool_profile_hash: String,
    pub version: String,
    pub capability_flags: Vec<String>,
    pub allow_network: bool,
    /// QA18: required when this adapter declares a billable capability
    /// (07 §5.7 condition 6) — the closed set of `usage.billable_units[].kind`
    /// values it may report. Empty for a non-billable adapter. Output-inert
    /// (not part of `tool_profile_hash`, `identity::PROFILE_FIELDS`).
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub billable_kinds: Vec<BillableUnitKind>,
    /// QA18: required when this adapter declares a billable capability.
    /// `None` for a non-billable adapter. Output-inert, same as
    /// `billable_kinds`.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reject_billing: Option<BillingDeclaration>,
    /// QA13 (step4b-contract-tests-p3a.md §E, 04 §5.5 L880): sync-call
    /// provider idempotency declaration — see [`ProviderIdempotency`].
    /// Output-inert (not part of `tool_profile_hash`, `identity::PROFILE_FIELDS`),
    /// same posture as `billable_kinds`/`reject_billing` above.
    pub provider_idempotency: ProviderIdempotency,
}

/// QA16 (step4b-contract-tests-p3a.md §F): `transient | permanent | rate_limit`
/// (07 §4 L287) — the coarse retry-classification input for 04-pipeline.md
/// §5.3's table. `error_code` carries the fine-grained machine code; this
/// field is only the coarse bucket the retry table keys off.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ErrorCategory {
    Transient,
    Permanent,
    RateLimit,
}

/// QA17: one `usage.billable_units[]` entry (07 §4 L294). `count` is a
/// non-negative unit count; USD conversion is the caller's per-kind price ×
/// count, summed across entries (`kind` duplicates are a billing-field
/// defect — see [`AdapterUsage::is_well_formed`]).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct BillableUnit {
    pub kind: BillableUnitKind,
    pub count: u64,
}

/// QA17: `usage one-of { usd } | { billable_units }` (07 §4 L291-307) —
/// request-scoped billing report on a terminal `AdapterRun`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(untagged)]
pub enum AdapterUsage {
    Usd { usd: f64 },
    BillableUnits { billable_units: Vec<BillableUnit> },
}

impl AdapterUsage {
    /// QA17: structural well-formedness (07 §4 L291-307) — `usd` must be a
    /// finite, non-negative amount; `billable_units` must be non-empty with
    /// unique `kind`s. A malformed `usage` is not itself a contract
    /// violation (it degrades to an `estimated` charge with a warning,
    /// 04-pipeline.md §5.4) — callers use this to decide that degrade, not
    /// to reject the response.
    #[must_use]
    pub fn is_well_formed(&self) -> bool {
        match self {
            Self::Usd { usd } => usd.is_finite() && *usd >= 0.0,
            Self::BillableUnits { billable_units } => {
                !billable_units.is_empty() && {
                    let mut kinds = billable_units.iter().map(|unit| unit.kind);
                    let mut seen = std::collections::BTreeSet::new();
                    kinds.all(|kind| seen.insert(format!("{kind:?}")))
                }
            }
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AdapterRun {
    pub task_id: String,
    pub input_hashes: Vec<String>,
    pub output_hashes: Vec<String>,
    pub status: AdapterRunStatus,
    /// QA16: machine-judgeable error code (06 §8), independent of the coarse
    /// `error_category` bucket.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub error_code: Option<String>,
    /// QA16: `transient | permanent | rate_limit` — see [`ErrorCategory`].
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub error_category: Option<ErrorCategory>,
    /// QA16: provider `Retry-After`, verbatim in milliseconds, when present
    /// on a rate-limited run.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub retry_after_ms: Option<u64>,
    /// QA17: request-scoped billing report — see [`AdapterUsage`].
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub usage: Option<AdapterUsage>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RawInput {
    pub raw_hash: String,
    pub path: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum UnitKind {
    Page,
    Slide,
    HeadingSection,
    Sheet,
    Image,
    File,
    Symbol,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct UnitFingerprint {
    pub perceptual_hash: String,
    pub text_hash: String,
    pub visual_hash: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PreparedUnitMetadata {
    pub unit_key: String,
    pub unit_kind: UnitKind,
    pub page_number: Option<u64>,
    pub mime: Option<String>,
    pub fingerprint: UnitFingerprint,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PrepareRequest {
    pub raw_hash: String,
    pub media_type: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PrepareResponse {
    pub prepared_object_hashes: Vec<String>,
    pub prepared_unit_hashes: Vec<String>,
    pub image_object_hashes: Vec<String>,
    pub metadata: Vec<PreparedUnitMetadata>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MarkdownizeMode {
    Full,
    Incremental,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PreparedUnitHint {
    pub unit_key: String,
    pub prepared_hash: String,
    pub unit_kind: UnitKind,
    pub order: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MarkdownUnit {
    pub unit_key: String,
    pub unit_type: UnitKind,
    pub markdown: String,
    pub metadata: BTreeMap<String, Value>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PreviousMarkdownizeContext {
    pub raw: RawInput,
    pub normalized_units: Vec<MarkdownUnit>,
    pub tool_profile_hash: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IncrementalHints {
    pub changed_unit_keys: Vec<String>,
    pub added_unit_keys: Vec<String>,
    pub removed_unit_keys: Vec<String>,
    pub page_fingerprints: BTreeMap<String, UnitFingerprint>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MarkdownizeRequest {
    pub raw: RawInput,
    pub media_type: String,
    pub prepared_unit_hint: Option<Vec<PreparedUnitHint>>,
    pub mode: MarkdownizeMode,
    pub previous: Option<PreviousMarkdownizeContext>,
    pub hints: Option<IncrementalHints>,
    /// R15-5: restrict the real OCR send to the pages named by `prepared_unit_hint`
    /// (their 0-based `order`) REGARDLESS of `mode`. A unit-scoped retry re-sends only
    /// the failed subset but with `mode = Full` (no previous/hints), so keying page
    /// scoping on `mode == Incremental` alone let the real Mistral client OCR/bill the
    /// whole document while the ledger reserved just the subset. A FRESH full send
    /// leaves this `false` (whole document, no `pages`); the retry sets it `true`.
    #[serde(default)]
    pub restrict_to_hint_pages: bool,
    /// Step 4 Mistral bbox annotation policy.
    pub bbox_annotation_enabled: bool,
    pub tool_profile_hash: String,
    pub spec_version: u64,
    /// QA13 (step4b-contract-tests-p3a.md §E, 04 §5.5 L880): the ledger
    /// phase-1 `intent_token` (04 §5.8 相 1, UUIDv7) — stable across a
    /// crash-window resend because `reserve_or_reuse_task_charge` returns the
    /// SAME token while the row stays open, which is exactly the dedup
    /// property a provider-side idempotency key needs. Carried only when the
    /// executing adapter's profile declares
    /// `ProviderIdempotency::HttpHeader` (the ledger's own §5.4/§5.8 2-phase
    /// record is the sole guard otherwise). `None` for a send with no ledger
    /// charge (e.g. the offline/free-local Markdownize path).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub idempotency_token: Option<String>,
}

/// QA36 (step4b-contract-tests-p3a.md §K): one partially-failed unit (04 §3
/// L295, 07 §5.2 L345-348). `error_kind` must be a member of
/// `kio_pipeline::task::RetryErrorKind`'s closed enum (04 §3.2 V6) — checked
/// by the pipeline crate's `validate_markdownize_response` (this crate has no
/// dependency on `kio-pipeline`, so the membership check lives there).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FailedUnit {
    pub unit_key: String,
    pub error_kind: String,
}

// QA17: no longer `Eq` — `usage: Option<AdapterUsage>` can carry an `f64` USD
// amount, and `f64` has no total order (NaN), so it cannot derive `Eq`.
// `PartialEq` (used by every `assert_eq!` call site) is unaffected.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct MarkdownizeResponse {
    pub mode_used: MarkdownizeMode,
    pub updated_units: Vec<MarkdownUnit>,
    pub unchanged_unit_keys: Vec<String>,
    pub added_units: Vec<MarkdownUnit>,
    pub removed_unit_keys: Vec<String>,
    /// QA36: partially-failed units (04 §3.2 V1/V4/V6) — not persisted; the
    /// pipeline transitions the named unit to `failed` in the manifest.
    #[serde(default)]
    pub failed_units: Vec<FailedUnit>,
    pub fallback_to_full: bool,
    pub reason: Option<String>,
    /// QA17 (step4b-contract-tests-p3a.md §F, 07 §4 L291-307): this request's
    /// self-reported billing usage, when the concrete Adapter can determine
    /// one from the provider's own response (e.g. Mistral OCR's processed
    /// page count). `None` when no real signal is available — the caller
    /// degrades to the reservation estimate exactly as it did before this
    /// field existed (04-pipeline.md §5.4's `estimated=1` path).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub usage: Option<AdapterUsage>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EmbeddingInputType {
    Text,
    Image,
    MarkdownChunk,
    ImageObject,
    Query,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct EmbeddingItem {
    pub id: String,
    pub text: Option<String>,
    pub path: Option<String>,
    pub mime: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct EmbeddingRequest {
    pub input_type: EmbeddingInputType,
    pub items: Vec<EmbeddingItem>,
    /// QA13 (step4b-contract-tests-p3a.md §E, 04 §5.5 L880): see
    /// `MarkdownizeRequest::idempotency_token`'s doc — same semantics,
    /// carried only when the executing adapter's profile declares
    /// `ProviderIdempotency::HttpHeader`.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub idempotency_token: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct EmbeddingVector {
    pub id: String,
    pub vector: Vec<f32>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct EmbeddingResponse {
    pub vectors: Vec<EmbeddingVector>,
    pub dimensions: u32,
    pub distance: String,
    pub modality: String,
    /// QA49 (step4b-contract-tests-p3a.md §N): the adapter's
    /// `tool_profile_hash` at response time, so the consumer can reject a
    /// same-dimension vector from an unexpected embedding profile (07 §5.3
    /// (5)) instead of trusting `dimensions`/`distance`/`modality` alone.
    /// `None` for an adapter that predates this field (degrades to the old
    /// dimensions/distance/modality-only check).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub embedding_profile_hash: Option<String>,
    /// QA17: this request's self-reported billing usage (07 §4 L291-307).
    /// `None` when the concrete Adapter has no real per-call signal to report —
    /// the caller degrades to the reservation estimate.
    ///
    /// I12: this doc used to name Gemini `batchEmbedContents` as the example of
    /// an endpoint carrying no token count. It carries one — measured against
    /// the live endpoint, `usageMetadata.promptTokenCount`, as a per-CALL total.
    /// The absent per-REQUEST count is true and beside the point, since per-call
    /// is the granularity the provider bills at. `gemini_embedding` populates
    /// this field accordingly; a caller that settles on the reservation while
    /// this is `Some` is discarding the provider's own number.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub usage: Option<AdapterUsage>,
}

/// Validate the numeric domain required by cosine distance. Width alone is not
/// sufficient: non-finite values and a zero vector make cosine results
/// undefined and must never reach persistence or search.
pub fn validate_cosine_vector(vector: &[f32], dimensions: u32) -> crate::Result<()> {
    if vector.len() != dimensions as usize {
        return Err(crate::AdapterError::ContractViolation(format!(
            "embedding dimension mismatch: expected {dimensions}, got {}",
            vector.len()
        )));
    }
    if vector.iter().any(|value| !value.is_finite()) {
        return Err(crate::AdapterError::ContractViolation(
            "embedding values must be finite f32 values".to_owned(),
        ));
    }
    let norm_squared = vector
        .iter()
        .map(|value| f64::from(*value).powi(2))
        .sum::<f64>();
    if !norm_squared.is_finite() || norm_squared <= 0.0 {
        return Err(crate::AdapterError::ContractViolation(
            "embedding vector must have a positive finite norm".to_owned(),
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn placeholder_markdownize_request_uses_spec_mode() {
        let request = MarkdownizeRequest {
            raw: RawInput {
                raw_hash: "sha256:abc".to_owned(),
                path: Some("report.pdf".to_owned()),
            },
            media_type: "application/pdf".to_owned(),
            prepared_unit_hint: None,
            mode: MarkdownizeMode::Incremental,
            previous: None,
            hints: None,
            restrict_to_hint_pages: false,
            bbox_annotation_enabled: true,
            tool_profile_hash: "sha256:tool".to_owned(),
            spec_version: 1,
            idempotency_token: None,
        };

        let value = serde_json::to_value(request).expect("serialize markdownize request");
        assert_eq!(value["mode"], "incremental");
        assert_eq!(value["bbox_annotation_enabled"], true);
    }

    #[test]
    fn cosine_vector_requires_finite_positive_norm() {
        validate_cosine_vector(&[1.0, 0.0], 2).unwrap();
        assert!(validate_cosine_vector(&[0.0, 0.0], 2).is_err());
        assert!(validate_cosine_vector(&[f32::INFINITY, 0.0], 2).is_err());
        assert!(validate_cosine_vector(&[1.0], 2).is_err());
    }
}
