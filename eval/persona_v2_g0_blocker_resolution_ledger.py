"""Non-authorizing three-schema G0 blocker-ledger bootstrap candidate.

This is deliberately a *registry slice*, not the final historical blocker
universe.  It binds three already accepted compact artifacts and enumerates
every blocker string and schema-declared false completion assertion in those bodies
using typed JSON paths.  No claim is resolved or deferred here.  A later
schema-compatible expansion must register the remaining accepted artifacts,
the production corpus namespace, and positive independent review evidence
before any G0 authority can exist.

The source registry is explicit.  Filesystem discovery is never an authority
for this artifact.
"""

from __future__ import annotations

import copy
import functools
import hashlib
import json

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_realism_profile as realism_profile
    from . import persona_v2_route_review_receipt as route_review
    from . import persona_v2_variant_catalog as variant_catalog
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_realism_profile as realism_profile
    import persona_v2_route_review_receipt as route_review
    import persona_v2_variant_catalog as variant_catalog


ARTIFACT_SCHEMA = "kio.persona.pc-g0-blocker-resolution-ledger/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-g0-blocker-resolution-ledger-candidate"
REGISTRY_PROFILE_ID = "bootstrap-three-source-v1"
LEDGER_NODE_ID = "ledger:g0-blocker-resolution-ledger-v2-candidate"
BODY_FRAMING = "canonical-json"
MAX_LEDGER_BYTES = 16 * 2**20
TARGET_LEDGER_BYTES = 4 * 2**20
MAX_SOURCE_COUNT = 4_096
MAX_CLAIMS_PER_SOURCE = 1_024
MAX_RESOLUTION_ENTRY_COUNT = 65_536
MAX_RESOLVER_PINS_PER_CLAIM = 8
MAX_FIELD_PATH_DEPTH = 64
MAX_CUMULATIVE_SOURCE_BYTES = 8 * 2**20
EXPECTED_BOOTSTRAP_CANDIDATE_CANONICAL_BYTES = 21_645
EXPECTED_BOOTSTRAP_CANDIDATE_SHA256 = (
    "48c9c36a965fbae34b1a89b041515a267284149801120b12e16b548fc4a96c97"
)

STATUS_ORDER = (
    "active-g0",
    "resolved-by-downstream-pin",
    "deferred-post-g0",
    "historical-local-negative",
)
DEFER_GATE_ALLOWLIST = (
    "G2-pilot-W0-observation",
    "G3-history-execution",
    "G4-root-bound-capacity",
    "G7-cross-replay-observation",
    "pre-W2-move-delta-patch",
)
ACTIVE_CLASSIFICATION_BASIS = (
    "candidate-registry-slice-unresolved-no-resolution-pin-v1"
)

SOURCE_ORDER = (
    "source:realism-profile-v2",
    "source:variant-catalog-v2",
    "source:negative-route-review-v2",
)

# Each path is an exact tuple of object keys.  List indices are appended only
# after the exact blocker collection itself has been checked.
_SOURCE_DEFINITIONS = (
    {
        "source_id": "source:realism-profile-v2",
        "artifact_kind": realism_profile.ARTIFACT_KIND,
        "artifact_schema": realism_profile.ARTIFACT_SCHEMA,
        "artifact_schema_version": realism_profile.ARTIFACT_SCHEMA_VERSION,
        "max_body_bytes": realism_profile.MAX_PROFILE_BYTES,
        "builder": realism_profile.build_realism_profile,
        "canonicalizer": realism_profile.canonical_json_bytes,
        "validator": realism_profile.validate_realism_profile,
        "blocker_list_paths": (("remaining_blockers",),),
        "false_completion_paths": (
            ("g0_contract_frozen",),
            ("eight_axis_ledger_contract_complete",),
            ("overlay_membership_complete",),
            ("overlay_scoring_and_search_semantics_complete",),
            ("placement_integer_allocation_complete",),
            ("realism_input_closure_complete",),
        ),
    },
    {
        "source_id": "source:variant-catalog-v2",
        "artifact_kind": variant_catalog.ARTIFACT_KIND,
        "artifact_schema": variant_catalog.ARTIFACT_SCHEMA,
        "artifact_schema_version": variant_catalog.ARTIFACT_SCHEMA_VERSION,
        "max_body_bytes": variant_catalog.MAX_CATALOG_BYTES,
        "builder": variant_catalog.build_variant_catalog,
        "canonicalizer": variant_catalog.canonical_json_bytes,
        "validator": variant_catalog.validate_variant_catalog,
        "blocker_list_paths": (("remaining_blockers",),),
        "false_completion_paths": (
            ("g0_contract_frozen",),
            ("kio_media_policy", "cross_language_production_tables_verified"),
            ("renderer_validator_implementation_complete",),
            ("source_level_feasibility_complete",),
            ("variant_catalog_complete",),
        ),
    },
    {
        "source_id": "source:negative-route-review-v2",
        "artifact_kind": route_review.ARTIFACT_KIND,
        "artifact_schema": route_review.ARTIFACT_SCHEMA,
        "artifact_schema_version": route_review.ARTIFACT_SCHEMA_VERSION,
        "max_body_bytes": route_review.MAX_ROUTE_REVIEW_RECEIPT_BYTES,
        "builder": route_review.build_negative_route_review_receipt,
        "canonicalizer": route_review.canonical_json_bytes,
        "validator": route_review.validate_negative_route_review_receipt,
        "blocker_list_paths": (("authoritative_review_blockers",),),
        "false_completion_paths": (
            ("g0_contract_frozen",),
            ("review_summary", "independent_review_complete"),
            ("review_summary", "review_authoritative"),
            ("route_affinity_matrix_review_receipt_bound",),
        ),
    },
)

REMAINING_BLOCKERS = (
    "historical-blocker-source-universe-not-completely-registered",
    "production-corpus-semantic-namespace-source-not-registered",
    "positive-independent-review-sources-not-registered",
    "registered-active-g0-claims-not-resolved",
    "final-authoritative-ledger-golden-not-frozen",
)


class PersonaV2G0BlockerResolutionLedgerError(ValueError):
    """Raised when the non-authorizing ledger candidate cannot be built."""


def _fail(message):
    raise PersonaV2G0BlockerResolutionLedgerError(message)


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _require_frozen_golden_raw(raw):
    """Enforce the producer-owned byte identity without importing a validator."""

    if (
        type(EXPECTED_BOOTSTRAP_CANDIDATE_CANONICAL_BYTES) is not int
        or type(EXPECTED_BOOTSTRAP_CANDIDATE_CANONICAL_BYTES) is bool
        or EXPECTED_BOOTSTRAP_CANDIDATE_CANONICAL_BYTES <= 0
        or type(EXPECTED_BOOTSTRAP_CANDIDATE_SHA256) is not str
        or len(EXPECTED_BOOTSTRAP_CANDIDATE_SHA256) != 64
        or any(
            character not in "0123456789abcdef"
            for character in EXPECTED_BOOTSTRAP_CANDIDATE_SHA256
        )
    ):
        _fail("blocker-ledger bootstrap frozen golden configuration is invalid")
    if (
        type(raw) is not bytes
        or len(raw) != EXPECTED_BOOTSTRAP_CANDIDATE_CANONICAL_BYTES
        or _sha256(raw) != EXPECTED_BOOTSTRAP_CANDIDATE_SHA256
    ):
        _fail("blocker-ledger bootstrap differs from its frozen golden")
    return raw


def _canonical_fragment(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 blocker-ledger fragment",
            max_bytes=MAX_LEDGER_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _strict_json_body(raw, *, label, max_body_bytes):
    if type(raw) is not bytes or len(raw) > max_body_bytes:
        _fail(f"{label} must be immutable bytes within its framed cap")
    if raw.startswith(b"\xef\xbb\xbf"):
        _fail(f"{label} must not contain a UTF-8 BOM")

    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                _fail(f"{label} contains a duplicate object key")
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=object_pairs)
    except PersonaV2G0BlockerResolutionLedgerError:
        raise
    except RecursionError:
        _fail(f"{label} exceeds the JSON parser nesting bound")
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        _fail(f"{label} is not strict UTF-8 JSON: {type(error).__name__}")
    if type(value) is not dict:
        _fail(f"{label} must be one JSON object")
    try:
        canonical = artifact_common.canonical_json_bytes(
            value,
            label=label,
            max_bytes=max_body_bytes,
        )
    except RecursionError:
        _fail(f"{label} exceeds the canonical nesting recursion bound")
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))
    if canonical != raw:
        _fail(f"{label} is not exact canonical JSON")
    return value


def _typed_path(path):
    if type(path) is not tuple or not path or len(path) > MAX_FIELD_PATH_DEPTH:
        _fail("source field path is not within its exact depth bound")
    result = []
    for token in path:
        if type(token) is str and token:
            result.append({"token_kind": "object-key", "value": token})
        elif type(token) is int and type(token) is not bool and token >= 0:
            result.append({"token_kind": "array-index", "value": token})
        else:
            _fail("source field path contains an invalid typed token")
    return result


def _read_path(value, path):
    current = value
    for token in path:
        if type(token) is str:
            if type(current) is not dict or token not in current:
                _fail("registered source field path is absent")
            current = current[token]
        else:
            if type(current) is not list or token >= len(current):
                _fail("registered source array path is absent")
            current = current[token]
    return current


def _claim_key(source_id, claim_kind, field_path, source_value):
    preimage = {
        "claim_kind": claim_kind,
        "field_path": field_path,
        "source_id": source_id,
        "source_value": source_value,
    }
    return _sha256(_canonical_fragment(preimage))


def _source_claims(definition, value):
    entries = []
    blocker_count = 0
    false_count = 0
    for collection_path in definition["blocker_list_paths"]:
        blockers = _read_path(value, collection_path)
        if (
            type(blockers) is not list
            or not blockers
            or len(blockers) > MAX_CLAIMS_PER_SOURCE
            or any(type(item) is not str or not item for item in blockers)
            or len(blockers) != len(set(blockers))
        ):
            _fail("registered blocker collection must contain unique bounded strings")
        for ordinal, blocker in enumerate(blockers):
            path = _typed_path(collection_path + (ordinal,))
            entries.append(
                {
                    "claim_key_sha256": _claim_key(
                        definition["source_id"], "remaining-blocker", path, blocker
                    ),
                    "claim_kind": "remaining-blocker",
                    "classification_basis": ACTIVE_CLASSIFICATION_BASIS,
                    "defer_gate_ids": [],
                    "field_path": path,
                    "resolution_evidence": [],
                    "source_id": definition["source_id"],
                    "source_value": blocker,
                    "status": "active-g0",
                }
            )
            blocker_count += 1
    for completion_path in definition["false_completion_paths"]:
        if _read_path(value, completion_path) is not False:
            _fail("registered false completion assertion is no longer false")
        path = _typed_path(completion_path)
        entries.append(
            {
                "claim_key_sha256": _claim_key(
                    definition["source_id"], "false-completion", path, False
                ),
                "claim_kind": "false-completion",
                "classification_basis": ACTIVE_CLASSIFICATION_BASIS,
                "defer_gate_ids": [],
                "field_path": path,
                "resolution_evidence": [],
                "source_id": definition["source_id"],
                "source_value": False,
                "status": "active-g0",
            }
        )
        false_count += 1
    if len(entries) > MAX_CLAIMS_PER_SOURCE:
        _fail("registered source exceeds its exact claim cap")
    return entries, blocker_count, false_count


@functools.lru_cache(maxsize=1)
def _immutable_source_body_cache():
    bodies = []
    for definition in _SOURCE_DEFINITIONS:
        value = definition["builder"]()
        definition["validator"](value)
        raw = definition["canonicalizer"](value)
        parsed = _strict_json_body(
            raw,
            label=definition["source_id"],
            max_body_bytes=definition["max_body_bytes"],
        )
        if (
            parsed.get("artifact_kind") != definition["artifact_kind"]
            or parsed.get("artifact_schema") != definition["artifact_schema"]
            or parsed.get("artifact_schema_version")
            != definition["artifact_schema_version"]
        ):
            _fail("registered source identity differs from the explicit registry")
        bodies.append((definition["source_id"], raw))
    return tuple(bodies)


def _source_body(source_id):
    for candidate_id, raw in _immutable_source_body_cache():
        if candidate_id == source_id:
            return raw
    _fail("unknown explicit blocker-ledger source ID")


def _build_from_source_provider(source_provider):
    if not callable(source_provider):
        _fail("source provider must be callable")
    if len(_SOURCE_DEFINITIONS) > MAX_SOURCE_COUNT:
        _fail("explicit source registry exceeds its source cap")
    opening = {}
    cumulative = 0
    for definition in _SOURCE_DEFINITIONS:
        raw = source_provider(definition["source_id"])
        if type(raw) is not bytes or len(raw) > definition["max_body_bytes"]:
            _fail("source provider returned an invalid framed body")
        cumulative += len(raw)
        if cumulative > MAX_CUMULATIVE_SOURCE_BYTES:
            _fail("cumulative source bodies exceed the ledger cap")
        opening[definition["source_id"]] = raw

    source_registry = []
    resolution_entries = []
    for definition in _SOURCE_DEFINITIONS:
        raw = opening[definition["source_id"]]
        value = _strict_json_body(
            raw,
            label=definition["source_id"],
            max_body_bytes=definition["max_body_bytes"],
        )
        definition["validator"](value)
        if definition["canonicalizer"](value) != raw:
            _fail("registered source validator did not preserve exact canonical bytes")
        if (
            value.get("artifact_kind") != definition["artifact_kind"]
            or value.get("artifact_schema") != definition["artifact_schema"]
            or value.get("artifact_schema_version")
            != definition["artifact_schema_version"]
        ):
            _fail("registered source identity differs from the explicit registry")
        claims, blocker_count, false_count = _source_claims(definition, value)
        resolution_entries.extend(claims)
        source_registry.append(
            {
                "artifact_kind": definition["artifact_kind"],
                "artifact_schema": definition["artifact_schema"],
                "artifact_schema_version": definition["artifact_schema_version"],
                "blocker_claim_count": blocker_count,
                "body_framing": BODY_FRAMING,
                "canonical_bytes": len(raw),
                "claim_count": len(claims),
                "claims_sha256": _sha256(
                    _canonical_fragment([item["claim_key_sha256"] for item in claims])
                ),
                "coordinates": {},
                "false_completion_claim_count": false_count,
                "sha256": _sha256(raw),
                "source_id": definition["source_id"],
            }
        )

    if tuple(item["source_id"] for item in source_registry) != SOURCE_ORDER:
        _fail("explicit source registry order drifted")
    claim_keys = [entry["claim_key_sha256"] for entry in resolution_entries]
    if len(claim_keys) != len(set(claim_keys)):
        _fail("typed source claims are not uniquely keyed")
    status_counts = {
        status: sum(entry["status"] == status for entry in resolution_entries)
        for status in STATUS_ORDER
    }
    dependency_edges = []
    value = {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {
            "authorizes_g0_freeze": False,
            "authorizes_solver_execution": False,
            "authorizes_source_plan": False,
            "authorizes_write_or_history": False,
            "blocker_universe_authoritative": False,
            "resolution_ledger_authoritative": False,
        },
        "canonical_limits": {
            "defer_gate_allowlist": list(DEFER_GATE_ALLOWLIST),
            "framed_byte_cap_before_body_required": True,
            "max_claims_per_source": MAX_CLAIMS_PER_SOURCE,
            "max_cumulative_source_bytes": MAX_CUMULATIVE_SOURCE_BYTES,
            "max_field_path_depth": MAX_FIELD_PATH_DEPTH,
            "max_ledger_bytes": MAX_LEDGER_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_resolution_entry_count": MAX_RESOLUTION_ENTRY_COUNT,
            "max_resolver_pins_per_claim": MAX_RESOLVER_PINS_PER_CLAIM,
            "max_source_count": MAX_SOURCE_COUNT,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "target_ledger_bytes": TARGET_LEDGER_BYTES,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_active_g0_blockers_resolved": False,
            "closure_eligible": False,
            "g0_eligible": False,
            "historical_blocker_universe_complete": False,
            "local_status_policy_applied": True,
            "namespace_and_review_sources_bound": False,
            "registered_source_claims_exactly_enumerated": True,
            "source_registry_complete": False,
        },
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "hypothesis_status": (
            "safe-standalone-three-schema-bootstrap-candidate-non-authorizing-"
            "incomplete-historical-universe"
        ),
        "orders": {
            "claims": (
                "source-order-then-blocker-collection-order-then-list-index-"
                "then-explicit-false-completion-path-order"
            ),
            "source": list(SOURCE_ORDER),
            "status": list(STATUS_ORDER),
        },
        "registry_profile_id": REGISTRY_PROFILE_ID,
        "registry_scope": {
            "candidate_slice_id": "three-schema-bootstrap-candidate",
            "claim_path_policy_id": (
                "explicit-schema-specific-blocker-collections-and-false-"
                "completion-paths-v1"
            ),
            "closure_eligible": False,
            "corpus_semantic_namespace_source_included": False,
            "coverage_statement": (
                "exact-for-three-explicit-schemas-only-no-historical-universe-claim"
            ),
            "historical_source_universe_complete": False,
            "known_unregistered_source_count_asserted": False,
            "positive_independent_review_sources_included": False,
            "remaining_registry_expansion_classes": [
                "remaining-accepted-blocker-bearing-persona-v2-schemas",
                "production-corpus-semantic-namespace-after-acceptance",
                "positive-independent-review-receipts-after-acceptance",
            ],
            "source_registry_complete": False,
        },
        "remaining_blockers": list(REMAINING_BLOCKERS),
        "resolution_entries": resolution_entries,
        "source_artifact_registry": source_registry,
        "summary": {
            "active_g0_count": status_counts["active-g0"],
            "active_g0_unresolved_count": status_counts["active-g0"],
            "active_g0_count_zero": status_counts["active-g0"] == 0,
            "blocker_claim_count": sum(
                item["blocker_claim_count"] for item in source_registry
            ),
            "claim_count": len(resolution_entries),
            "dependency_edge_count": len(dependency_edges),
            "dependency_graph_sha256": _sha256(
                _canonical_fragment(dependency_edges)
            ),
            "false_completion_claim_count": sum(
                item["false_completion_claim_count"] for item in source_registry
            ),
            "ordered_claim_keys_sha256": _sha256(_canonical_fragment(claim_keys)),
            "source_count": len(source_registry),
            "source_registry_complete": False,
            "source_registry_sha256": _sha256(_canonical_fragment(source_registry)),
            "status_counts": status_counts,
        },
    }

    for definition in _SOURCE_DEFINITIONS:
        closing = source_provider(definition["source_id"])
        if type(closing) is not bytes or closing != opening[definition["source_id"]]:
            _fail("registered source changed during ledger construction")
    return value


@functools.lru_cache(maxsize=1)
def _canonical_ledger_value():
    return _build_from_source_provider(_source_body)


def build_g0_blocker_resolution_ledger_bootstrap_candidate():
    """Return a detached, non-authorizing three-schema bootstrap candidate."""

    value = copy.deepcopy(_canonical_ledger_value())
    _require_frozen_golden_raw(
        _canonical_bootstrap_candidate_json_bytes_unchecked(value)
    )
    return value


def _require_independent_candidate_preflight(value):
    """Bound a caller-owned candidate before producer-side serialization."""

    try:
        from . import persona_v2_g0_blocker_resolution_ledger_validator as validator
    except ImportError:  # pragma: no cover - direct-script compatibility
        try:
            import persona_v2_g0_blocker_resolution_ledger_validator as validator
        except ImportError:
            validator = None
    preflight = (
        None if validator is None else getattr(validator, "_preflight_top_level", None)
    )
    if not callable(preflight):
        _fail("independent blocker-ledger bootstrap preflight is unavailable")
    try:
        preflight(value)
    except Exception:
        raise PersonaV2G0BlockerResolutionLedgerError(
            "blocker-ledger bootstrap candidate failed strict preflight"
        ) from None


def _canonical_bootstrap_candidate_json_bytes_unchecked(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 G0 blocker-resolution ledger candidate",
            max_bytes=MAX_LEDGER_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2G0BlockerResolutionLedgerError(str(error)) from None


def canonical_bootstrap_candidate_json_bytes(value):
    _require_independent_candidate_preflight(value)
    return _require_frozen_golden_raw(
        _canonical_bootstrap_candidate_json_bytes_unchecked(value)
    )


def g0_blocker_resolution_ledger_bootstrap_candidate_sha256(value=None):
    """Hash a validated exact candidate; never imply G0 authority."""

    if value is None:
        value = build_g0_blocker_resolution_ledger_bootstrap_candidate()
    opening = canonical_bootstrap_candidate_json_bytes(value)
    try:
        from . import persona_v2_g0_blocker_resolution_ledger_validator as validator
    except ImportError:  # pragma: no cover - direct-script compatibility
        import persona_v2_g0_blocker_resolution_ledger_validator as validator

    validator.load_and_validate_g0_blocker_resolution_ledger_bootstrap_candidate(opening)
    _require_independent_candidate_preflight(value)
    closing = _canonical_bootstrap_candidate_json_bytes_unchecked(value)
    if closing != opening:
        raise PersonaV2G0BlockerResolutionLedgerError(
            "bootstrap ledger changed during validated hashing"
        )
    _require_frozen_golden_raw(closing)
    return _sha256(opening)


def require_complete_g0_blocker_resolution_ledger():
    """Fail closed: this bootstrap slice can never satisfy a closure."""

    raise PersonaV2G0BlockerResolutionLedgerError(
        "the three-schema bootstrap candidate is incomplete, non-authorizing, "
        "and not closure-eligible"
    )
