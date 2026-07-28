"""Independent validator for the three-source blocker-ledger bootstrap.

This module intentionally does not import the ledger producer.  Its public
entry point is candidate-specific and cannot be used as evidence that the
historical blocker universe, a corpus closure, or G0 is complete.
"""

from __future__ import annotations

import copy
import functools
import hashlib
import hmac
import json
import unicodedata

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
EXPECTED_SOURCE_COUNT = 3
EXPECTED_RESOLUTION_ENTRY_COUNT = 36
EXPECTED_BOOTSTRAP_CANDIDATE_CANONICAL_BYTES = 21_645
EXPECTED_BOOTSTRAP_CANDIDATE_SHA256 = (
    "e6428d280f8438875896dc210102611cfef54fd569e5c50ad9874ecef68146f2"
)
MAX_PREFLIGHT_EXPANDED_NODES = 200_000
MAX_PREFLIGHT_EXPANDED_BYTES = MAX_LEDGER_BYTES
MAX_PREFLIGHT_CONTAINER_ITEMS = MAX_RESOLUTION_ENTRY_COUNT

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
RESOLVED_CLASSIFICATION_BASIS = "downstream-resolution-pin-and-field-path-v1"
DEFERRED_CLASSIFICATION_BASIS = "explicit-post-g0-defer-policy-v1"
HISTORICAL_CLASSIFICATION_BASIS = (
    "historical-local-negative-no-current-authority-v1"
)

SOURCE_ORDER = (
    "source:realism-profile-v2",
    "source:variant-catalog-v2",
    "source:negative-route-review-v2",
)
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

TOP_LEVEL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "canonical_limits",
        "completion_claims",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
        "hypothesis_status",
        "orders",
        "registry_profile_id",
        "registry_scope",
        "remaining_blockers",
        "resolution_entries",
        "source_artifact_registry",
        "summary",
    }
)
AUTHORITY_FIELDS = frozenset(
    {
        "authorizes_g0_freeze",
        "authorizes_solver_execution",
        "authorizes_source_plan",
        "authorizes_write_or_history",
        "blocker_universe_authoritative",
        "resolution_ledger_authoritative",
    }
)
SOURCE_REGISTRY_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "blocker_claim_count",
        "body_framing",
        "canonical_bytes",
        "claim_count",
        "claims_sha256",
        "coordinates",
        "false_completion_claim_count",
        "sha256",
        "source_id",
    }
)
RESOLUTION_ENTRY_FIELDS = frozenset(
    {
        "claim_key_sha256",
        "claim_kind",
        "classification_basis",
        "defer_gate_ids",
        "field_path",
        "resolution_evidence",
        "source_id",
        "source_value",
        "status",
    }
)
PATH_TOKEN_FIELDS = frozenset({"token_kind", "value"})
RESOLUTION_EVIDENCE_FIELDS = frozenset(
    {"resolution_field_path", "resolution_value", "resolver_id", "resolver_pin"}
)
RESOLVER_PIN_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "body_framing",
        "canonical_bytes",
        "sha256",
    }
)
SUMMARY_FIELDS = frozenset(
    {
        "active_g0_count",
        "active_g0_count_zero",
        "active_g0_unresolved_count",
        "blocker_claim_count",
        "claim_count",
        "dependency_edge_count",
        "dependency_graph_sha256",
        "false_completion_claim_count",
        "ordered_claim_keys_sha256",
        "source_count",
        "source_registry_complete",
        "source_registry_sha256",
        "status_counts",
    }
)

EXPECTED_AUTHORITY = {field: False for field in sorted(AUTHORITY_FIELDS)}
EXPECTED_CANONICAL_LIMITS = {
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
}
EXPECTED_COMPLETION_CLAIMS = {
    "all_active_g0_blockers_resolved": False,
    "closure_eligible": False,
    "g0_eligible": False,
    "historical_blocker_universe_complete": False,
    "local_status_policy_applied": True,
    "namespace_and_review_sources_bound": False,
    "registered_source_claims_exactly_enumerated": True,
    "source_registry_complete": False,
}
EXPECTED_ORDERS = {
    "claims": (
        "source-order-then-blocker-collection-order-then-list-index-"
        "then-explicit-false-completion-path-order"
    ),
    "source": list(SOURCE_ORDER),
    "status": list(STATUS_ORDER),
}
EXPECTED_REGISTRY_SCOPE = {
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
}
EXPECTED_HYPOTHESIS_STATUS = (
    "safe-standalone-three-schema-bootstrap-candidate-non-authorizing-"
    "incomplete-historical-universe"
)


class PersonaV2G0BlockerResolutionLedgerValidationError(ValueError):
    """Raised when the bootstrap candidate fails closed."""


def _fail(message):
    raise PersonaV2G0BlockerResolutionLedgerValidationError(message)


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _require_frozen_golden_raw(raw):
    """Enforce the validator-owned byte identity independently of the producer."""

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
        or not hmac.compare_digest(
            _sha256(raw), EXPECTED_BOOTSTRAP_CANDIDATE_SHA256
        )
    ):
        _fail("blocker-ledger bootstrap differs from its frozen golden")
    return raw


def _exact_dict(value, fields, label):
    if type(value) is not dict or len(value) != len(fields) or set(value) != fields:
        _fail(f"{label} must be one exact object")
    return value


def _bounded_string(value, label):
    if (
        type(value) is not str
        or not value
        or len(value) > artifact_common.MAX_CANONICAL_STRING_BYTES
    ):
        _fail(f"{label} must be one bounded non-empty string")
    try:
        encoded = value.encode("utf-8", "strict")
    except UnicodeEncodeError:
        _fail(f"{label} must be valid UTF-8")
    if (
        len(encoded) > artifact_common.MAX_CANONICAL_STRING_BYTES
        or unicodedata.normalize("NFC", value) != value
    ):
        _fail(f"{label} must be one bounded non-empty string")
    return value


def _bounded_integer(value, label, *, minimum=0, maximum=None):
    if maximum is None:
        maximum = artifact_common.MAX_INTEGER_MAGNITUDE
    if (
        type(value) is not int
        or type(value) is bool
        or value < minimum
        or value > maximum
    ):
        _fail(f"{label} must be one bounded exact integer")
    return value


def _digest(value, label):
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _fail(f"{label} must be one lowercase SHA-256")
    return value


def _canonical_fragment(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 blocker-ledger validation fragment",
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
    except PersonaV2G0BlockerResolutionLedgerValidationError:
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
    if not hmac.compare_digest(canonical, raw):
        _fail(f"{label} is not exact canonical JSON")
    return value


def load_and_validate_g0_blocker_resolution_ledger_bootstrap_candidate(raw):
    """Strict duplicate-key-aware bytes entry point for this profile only."""

    value = _strict_json_body(
        raw,
        label="persona v2 G0 blocker-ledger bootstrap candidate",
        max_body_bytes=MAX_LEDGER_BYTES,
    )
    validate_g0_blocker_resolution_ledger_bootstrap_candidate(value)
    _require_frozen_golden_raw(raw)
    return copy.deepcopy(value)


def _typed_path(path):
    if type(path) is not tuple or not path or len(path) > MAX_FIELD_PATH_DEPTH:
        _fail("expected source field path exceeds its exact depth bound")
    result = []
    for token in path:
        if type(token) is str and token:
            result.append({"token_kind": "object-key", "value": token})
        elif type(token) is int and type(token) is not bool and token >= 0:
            result.append({"token_kind": "array-index", "value": token})
        else:
            _fail("expected source field path contains an invalid token")
    return result


def _validate_and_decode_path(path, label):
    if type(path) is not list or not path or len(path) > MAX_FIELD_PATH_DEPTH:
        _fail(f"{label} exceeds its exact shallow path bound")
    decoded = []
    for item in path:
        _exact_dict(item, PATH_TOKEN_FIELDS, f"{label} token")
        kind = item["token_kind"]
        token = item["value"]
        if kind == "object-key":
            decoded.append(_bounded_string(token, f"{label} object key"))
        elif kind == "array-index":
            decoded.append(
                _bounded_integer(token, f"{label} array index", maximum=MAX_CLAIMS_PER_SOURCE)
            )
        else:
            _fail(f"{label} token kind is unknown")
    return tuple(decoded)


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
    return _sha256(
        _canonical_fragment(
            {
                "claim_kind": claim_kind,
                "field_path": field_path,
                "source_id": source_id,
                "source_value": source_value,
            }
        )
    )


def _claims_for_source(definition, value):
    claims = []
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
            _fail("registered blocker collection must contain unique strings")
        for ordinal, blocker in enumerate(blockers):
            path = _typed_path(collection_path + (ordinal,))
            claims.append(
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
        claims.append(
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
    if len(claims) > MAX_CLAIMS_PER_SOURCE:
        _fail("registered source exceeds its exact claim cap")
    return claims, blocker_count, false_count


@functools.lru_cache(maxsize=1)
def _immutable_source_body_cache():
    result = []
    for definition in _SOURCE_DEFINITIONS:
        value = definition["builder"]()
        definition["validator"](value)
        raw = definition["canonicalizer"](value)
        result.append((definition["source_id"], raw))
    return tuple(result)


def _trusted_source_body(source_id):
    for candidate_id, raw in _immutable_source_body_cache():
        if candidate_id == source_id:
            return raw
    _fail("unknown explicit blocker-ledger source ID")


def _opening_source_snapshot(source_provider):
    if not callable(source_provider):
        _fail("internal source provider must be callable")
    if len(_SOURCE_DEFINITIONS) > MAX_SOURCE_COUNT:
        _fail("explicit source registry exceeds its source cap")
    result = {}
    cumulative = 0
    for definition in _SOURCE_DEFINITIONS:
        raw = source_provider(definition["source_id"])
        if type(raw) is not bytes or len(raw) > definition["max_body_bytes"]:
            _fail("source provider returned an invalid framed body")
        cumulative += len(raw)
        if cumulative > MAX_CUMULATIVE_SOURCE_BYTES:
            _fail("cumulative source bodies exceed the ledger cap")
        result[definition["source_id"]] = raw
    return result


def _validate_source_snapshot(opening):
    parsed = {}
    for definition in _SOURCE_DEFINITIONS:
        source_id = definition["source_id"]
        raw = opening[source_id]
        value = _strict_json_body(
            raw,
            label=source_id,
            max_body_bytes=definition["max_body_bytes"],
        )
        definition["validator"](value)
        if not hmac.compare_digest(definition["canonicalizer"](value), raw):
            _fail("registered source validator did not preserve canonical bytes")
        if (
            value.get("artifact_kind") != definition["artifact_kind"]
            or value.get("artifact_schema") != definition["artifact_schema"]
            or value.get("artifact_schema_version")
            != definition["artifact_schema_version"]
        ):
            _fail("registered source identity differs from the explicit registry")
        parsed[source_id] = value
    return parsed


def _expected_value(opening, parsed):
    source_registry = []
    resolution_entries = []
    for definition in _SOURCE_DEFINITIONS:
        raw = opening[definition["source_id"]]
        claims, blocker_count, false_count = _claims_for_source(
            definition, parsed[definition["source_id"]]
        )
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
    claim_keys = [entry["claim_key_sha256"] for entry in resolution_entries]
    if len(claim_keys) != len(set(claim_keys)):
        _fail("independently reconstructed claims are not uniquely keyed")
    status_counts = {
        status: sum(entry["status"] == status for entry in resolution_entries)
        for status in STATUS_ORDER
    }
    dependency_edges = []
    return {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": copy.deepcopy(EXPECTED_AUTHORITY),
        "canonical_limits": copy.deepcopy(EXPECTED_CANONICAL_LIMITS),
        "completion_claims": copy.deepcopy(EXPECTED_COMPLETION_CLAIMS),
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "hypothesis_status": EXPECTED_HYPOTHESIS_STATUS,
        "orders": copy.deepcopy(EXPECTED_ORDERS),
        "registry_profile_id": REGISTRY_PROFILE_ID,
        "registry_scope": copy.deepcopy(EXPECTED_REGISTRY_SCOPE),
        "remaining_blockers": list(REMAINING_BLOCKERS),
        "resolution_entries": resolution_entries,
        "source_artifact_registry": source_registry,
        "summary": {
            "active_g0_count": status_counts["active-g0"],
            "active_g0_count_zero": status_counts["active-g0"] == 0,
            "active_g0_unresolved_count": status_counts["active-g0"],
            "blocker_claim_count": sum(
                item["blocker_claim_count"] for item in source_registry
            ),
            "claim_count": len(resolution_entries),
            "dependency_edge_count": 0,
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


def _preflight_expected_shape(value, expected, label):
    """Check one small frozen shape without traversing attacker-owned extras."""

    if type(expected) is dict:
        _exact_dict(value, frozenset(expected), label)
        for key, expected_item in expected.items():
            _preflight_expected_shape(value[key], expected_item, f"{label}.{key}")
        return
    if type(expected) is list:
        if type(value) is not list or len(value) != len(expected):
            _fail(f"{label} must retain its exact bounded list shape")
        for ordinal, (item, expected_item) in enumerate(zip(value, expected)):
            _preflight_expected_shape(item, expected_item, f"{label}[{ordinal}]")
        return
    if type(value) is not type(expected) or value != expected:
        _fail(f"{label} must retain its exact scalar value")


def _preflight_resolution_scalar_schema(entries):
    """Reject container substitution before generic canonical traversal."""

    for entry in entries:
        _exact_dict(entry, RESOLUTION_ENTRY_FIELDS, "resolution entry")
        _digest(entry.get("claim_key_sha256"), "claim key")
        claim_kind = _bounded_string(entry.get("claim_kind"), "claim kind")
        if claim_kind not in {"remaining-blocker", "false-completion"}:
            _fail("resolution entry claim kind is unknown")
        _bounded_string(entry.get("classification_basis"), "classification basis")
        _bounded_string(entry.get("source_id"), "claim source ID")
        status = _bounded_string(entry.get("status"), "resolution status")
        if status not in STATUS_ORDER:
            _fail("resolution status is outside the exact status enum")
        source_value = entry.get("source_value")
        if claim_kind == "remaining-blocker":
            _bounded_string(source_value, "remaining blocker value")
        elif source_value is not False:
            _fail("false completion claim must bind exact boolean false")

        path = entry.get("field_path")
        evidence = entry.get("resolution_evidence")
        gates = entry.get("defer_gate_ids")
        if type(path) is not list or not path or len(path) > MAX_FIELD_PATH_DEPTH:
            _fail("claim field path exceeds its exact shallow bound")
        if (
            type(evidence) is not list
            or len(evidence) > MAX_RESOLVER_PINS_PER_CLAIM
        ):
            _fail("resolution evidence exceeds its exact shallow bound")
        if type(gates) is not list or len(gates) > 1:
            _fail("defer gates exceed their exact shallow bound")
        _validate_and_decode_path(path, "claim field path")
        for gate in gates:
            _bounded_string(gate, "defer gate ID")
        for item in evidence:
            _exact_dict(item, RESOLUTION_EVIDENCE_FIELDS, "resolution evidence")
            _bounded_string(item.get("resolver_id"), "resolver ID")
            if type(item.get("resolution_value")) is not bool:
                _fail("resolution evidence value must be one exact boolean")
            _validate_resolver_pin(item.get("resolver_pin"))
            _validate_and_decode_path(
                item.get("resolution_field_path"),
                "resolution evidence field path",
            )


def _preflight_summary_scalar_schema(summary):
    _exact_dict(summary, SUMMARY_FIELDS, "ledger summary")
    for field in (
        "active_g0_count",
        "active_g0_unresolved_count",
        "blocker_claim_count",
        "claim_count",
        "dependency_edge_count",
        "false_completion_claim_count",
        "source_count",
    ):
        _bounded_integer(summary.get(field), f"summary {field}")
    for field in (
        "active_g0_count_zero",
        "source_registry_complete",
    ):
        if type(summary.get(field)) is not bool:
            _fail(f"summary {field} must be one exact boolean")
    for field in (
        "dependency_graph_sha256",
        "ordered_claim_keys_sha256",
        "source_registry_sha256",
    ):
        _digest(summary.get(field), f"summary {field}")
    status_counts = summary.get("status_counts")
    _exact_dict(status_counts, frozenset(STATUS_ORDER), "summary status counts")
    for status in STATUS_ORDER:
        _bounded_integer(status_counts.get(status), f"summary status {status}")


def _preflight_expanded_budget(value):
    """Bound expanded traversal, counting shared containers on every reference."""

    stack = [(value, 0)]
    node_count = 0
    expanded_bytes = 0
    while stack:
        item, depth = stack.pop()
        node_count += 1
        if node_count > MAX_PREFLIGHT_EXPANDED_NODES:
            _fail("bootstrap ledger exceeds the expanded node budget")
        if depth > artifact_common.MAX_CANONICAL_DEPTH:
            _fail("bootstrap ledger exceeds the preflight nesting budget")

        if type(item) is dict:
            if len(item) > MAX_PREFLIGHT_CONTAINER_ITEMS:
                _fail("bootstrap ledger object exceeds the container item budget")
            expanded_bytes += 2 + max(0, len(item) - 1)
            for key, child in item.items():
                _bounded_string(key, "bootstrap ledger object key")
                key_bytes = len(key.encode("utf-8", "strict"))
                expanded_bytes += (6 * key_bytes) + 3
                stack.append((child, depth + 1))
        elif type(item) is list:
            if len(item) > MAX_PREFLIGHT_CONTAINER_ITEMS:
                _fail("bootstrap ledger list exceeds the container item budget")
            expanded_bytes += 2 + max(0, len(item) - 1)
            stack.extend((child, depth + 1) for child in item)
        elif type(item) is str:
            _bounded_string(item, "bootstrap ledger string")
            expanded_bytes += (6 * len(item.encode("utf-8", "strict"))) + 2
        elif type(item) is bool:
            expanded_bytes += 5
        elif type(item) is int and type(item) is not bool:
            _bounded_integer(item, "bootstrap ledger integer")
            expanded_bytes += 40
        else:
            _fail("bootstrap ledger contains a non-canonical value type")
        if expanded_bytes > MAX_PREFLIGHT_EXPANDED_BYTES:
            _fail("bootstrap ledger exceeds the expanded byte budget")


def _preflight_top_level(value):
    _exact_dict(value, TOP_LEVEL_FIELDS, "blocker-ledger bootstrap candidate")
    if (
        type(value.get("artifact_kind")) is not str
        or value.get("artifact_kind") != ARTIFACT_KIND
        or type(value.get("artifact_schema")) is not str
        or value.get("artifact_schema") != ARTIFACT_SCHEMA
        or type(value.get("artifact_schema_version")) is not int
        or type(value.get("artifact_schema_version")) is bool
        or value.get("artifact_schema_version") != ARTIFACT_SCHEMA_VERSION
        or type(value.get("registry_profile_id")) is not str
        or value.get("registry_profile_id") != REGISTRY_PROFILE_ID
    ):
        _fail("blocker-ledger schema or bootstrap profile identity drifted")
    sources = value.get("source_artifact_registry")
    claims = value.get("resolution_entries")
    blockers = value.get("remaining_blockers")
    if type(sources) is not list or len(sources) != EXPECTED_SOURCE_COUNT:
        _fail("bootstrap source registry differs from its exact shallow count")
    if type(claims) is not list or len(claims) != EXPECTED_RESOLUTION_ENTRY_COUNT:
        _fail("bootstrap resolution entries differ from their exact shallow count")
    if type(blockers) is not list or len(blockers) != len(REMAINING_BLOCKERS):
        _fail("bootstrap remaining blockers differ from their exact shallow count")

    _preflight_expected_shape(value.get("authority"), EXPECTED_AUTHORITY, "authority")
    _preflight_expected_shape(
        value.get("canonical_limits"), EXPECTED_CANONICAL_LIMITS, "canonical limits"
    )
    _preflight_expected_shape(
        value.get("completion_claims"),
        EXPECTED_COMPLETION_CLAIMS,
        "completion claims",
    )
    _preflight_expected_shape(value.get("orders"), EXPECTED_ORDERS, "orders")
    _preflight_expected_shape(
        value.get("registry_scope"), EXPECTED_REGISTRY_SCOPE, "registry scope"
    )
    _preflight_expected_shape(
        blockers, list(REMAINING_BLOCKERS), "remaining blockers"
    )
    if (
        type(value.get("fixture_id")) is not str
        or value.get("fixture_id") != envelope.FIXTURE_ID
        or type(value.get("fixture_schema_version")) is not int
        or value.get("fixture_schema_version") != envelope.FIXTURE_SCHEMA_VERSION
        or type(value.get("g0_contract_frozen")) is not bool
        or value.get("g0_contract_frozen") is not False
        or type(value.get("hypothesis_status")) is not str
        or value.get("hypothesis_status") != EXPECTED_HYPOTHESIS_STATUS
    ):
        _fail("bootstrap identity scalars drifted")
    _validate_source_registry(sources)
    _preflight_resolution_scalar_schema(claims)
    _preflight_summary_scalar_schema(value.get("summary"))
    _preflight_expanded_budget(value)
    try:
        artifact_common.validate_plain_value(
            value, label="persona v2 G0 blocker-ledger bootstrap candidate"
        )
        raw = artifact_common.canonical_json_bytes(
            value,
            label="persona v2 G0 blocker-ledger bootstrap candidate",
            max_bytes=MAX_LEDGER_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))
    return raw


def _validate_source_registry(registry):
    if len(registry) != len(SOURCE_ORDER):
        _fail("bootstrap source registry omits or adds a source")
    ids = []
    for item in registry:
        _exact_dict(item, SOURCE_REGISTRY_FIELDS, "source registry entry")
        source_id = _bounded_string(item["source_id"], "source ID")
        ids.append(source_id)
        _bounded_string(item["artifact_kind"], "source artifact kind")
        _bounded_string(item["artifact_schema"], "source artifact schema")
        _bounded_integer(
            item["artifact_schema_version"], "source artifact schema version", minimum=1
        )
        framing = _bounded_string(item["body_framing"], "source body framing")
        coordinates = item["coordinates"]
        if (
            framing != BODY_FRAMING
            or type(coordinates) is not dict
            or coordinates
        ):
            _fail("bootstrap sources must be global canonical JSON bodies")
        _bounded_integer(item["canonical_bytes"], "source canonical bytes", minimum=1)
        _bounded_integer(
            item["claim_count"],
            "source claim count",
            maximum=MAX_CLAIMS_PER_SOURCE,
        )
        _bounded_integer(
            item["blocker_claim_count"],
            "source blocker claim count",
            maximum=MAX_CLAIMS_PER_SOURCE,
        )
        _bounded_integer(
            item["false_completion_claim_count"],
            "source false completion count",
            maximum=MAX_CLAIMS_PER_SOURCE,
        )
        if (
            item["claim_count"]
            != item["blocker_claim_count"] + item["false_completion_claim_count"]
        ):
            _fail("source claim subtotals do not add up")
        _digest(item["sha256"], "source body digest")
        _digest(item["claims_sha256"], "source claims digest")
    if tuple(ids) != SOURCE_ORDER or len(ids) != len(set(ids)):
        _fail("bootstrap source registry order or uniqueness drifted")


def _validate_resolver_pin(pin):
    _exact_dict(pin, RESOLVER_PIN_FIELDS, "resolver pin")
    _bounded_string(pin["artifact_kind"], "resolver artifact kind")
    schema = _bounded_string(pin["artifact_schema"], "resolver artifact schema")
    _bounded_integer(
        pin["artifact_schema_version"], "resolver artifact schema version", minimum=1
    )
    framing = _bounded_string(pin["body_framing"], "resolver body framing")
    if framing != BODY_FRAMING:
        _fail("resolver pin must use the exact canonical JSON framing")
    _bounded_integer(pin["canonical_bytes"], "resolver canonical bytes", minimum=1)
    _digest(pin["sha256"], "resolver body digest")
    if schema == ARTIFACT_SCHEMA:
        _fail("blocker ledger cannot resolve a claim with a self-schema pin")


def _validate_resolution_entries(entries, registry):
    registered = {item["source_id"]: item for item in registry}
    keys = []
    edges = set()
    for entry in entries:
        source_id = _bounded_string(entry["source_id"], "claim source ID")
        if source_id not in registered:
            _fail("resolution entry names an unregistered source")
        claim_kind = entry["claim_kind"]
        if claim_kind not in {"remaining-blocker", "false-completion"}:
            _fail("resolution entry claim kind is unknown")
        decoded_path = _validate_and_decode_path(entry["field_path"], "claim field path")
        source_value = entry["source_value"]
        if claim_kind == "remaining-blocker":
            _bounded_string(source_value, "remaining blocker value")
        elif source_value is not False:
            _fail("false completion claim must bind exact boolean false")
        key = _digest(entry["claim_key_sha256"], "claim key")
        if key != _claim_key(source_id, claim_kind, entry["field_path"], source_value):
            _fail("claim key does not bind its typed source path and value")
        keys.append(key)
        status = entry["status"]
        if status not in STATUS_ORDER:
            _fail("resolution status is outside the exact status enum")
        evidence = entry["resolution_evidence"]
        gates = entry["defer_gate_ids"]
        for gate in gates:
            if gate not in DEFER_GATE_ALLOWLIST:
                _fail("defer gate is outside the exact allowlist")
        if status == "active-g0":
            if evidence or gates or entry["classification_basis"] != ACTIVE_CLASSIFICATION_BASIS:
                _fail("active G0 claim cannot carry resolution or deferral evidence")
        elif status == "resolved-by-downstream-pin":
            if (
                not evidence
                or gates
                or entry["classification_basis"] != RESOLVED_CLASSIFICATION_BASIS
            ):
                _fail("resolved claim requires downstream pin/path/value evidence")
        elif status == "deferred-post-g0":
            if (
                evidence
                or len(gates) != 1
                or entry["classification_basis"] != DEFERRED_CLASSIFICATION_BASIS
            ):
                _fail("deferred claim requires exactly one allowed post-G0 gate")
        elif (
            evidence
            or gates
            or entry["classification_basis"] != HISTORICAL_CLASSIFICATION_BASIS
        ):
            _fail("historical negative claim cannot carry current resolution authority")

        seen_resolvers = set()
        for item in evidence:
            _exact_dict(item, RESOLUTION_EVIDENCE_FIELDS, "resolution evidence")
            resolver_id = _bounded_string(item["resolver_id"], "resolver ID")
            if resolver_id == LEDGER_NODE_ID or resolver_id == source_id:
                _fail("resolution dependency graph contains a direct self edge")
            if resolver_id in seen_resolvers:
                _fail("resolution entry repeats a resolver dependency")
            seen_resolvers.add(resolver_id)
            _validate_resolver_pin(item["resolver_pin"])
            _validate_and_decode_path(
                item["resolution_field_path"], "resolution evidence field path"
            )
            if item["resolution_value"] is not True:
                _fail("resolution evidence must bind exact boolean true")
            if resolver_id in registered:
                expected_pin = registered[resolver_id]
                pin = item["resolver_pin"]
                if any(
                    pin[field] != expected_pin[field]
                    for field in (
                        "artifact_kind",
                        "artifact_schema",
                        "artifact_schema_version",
                        "body_framing",
                        "canonical_bytes",
                        "sha256",
                    )
                ):
                    _fail("registered resolver ID does not match its source pin")
            edges.add((source_id, resolver_id))
    if len(keys) != len(set(keys)):
        _fail("resolution entries duplicate a typed source claim")

    adjacency = {}
    for source_id, resolver_id in edges:
        adjacency.setdefault(source_id, set()).add(resolver_id)
    visiting = set()
    visited = set()

    def visit(node):
        if node in visiting:
            _fail("resolution dependency graph contains a cycle")
        if node in visited:
            return
        visiting.add(node)
        for child in adjacency.get(node, ()):
            visit(child)
        visiting.remove(node)
        visited.add(node)

    for node in tuple(adjacency):
        visit(node)
    return keys, [
        {"from_source_id": source_id, "to_resolver_id": resolver_id}
        for source_id, resolver_id in sorted(edges)
    ]


def _validate_semantics(value):
    if value["authority"] != EXPECTED_AUTHORITY or any(value["authority"].values()):
        _fail("bootstrap candidate must retain exact negative authority")
    if value["canonical_limits"] != EXPECTED_CANONICAL_LIMITS:
        _fail("bootstrap candidate canonical limits drifted")
    if value["completion_claims"] != EXPECTED_COMPLETION_CLAIMS:
        _fail("bootstrap candidate completion claims drifted")
    if (
        value["fixture_id"] != envelope.FIXTURE_ID
        or value["fixture_schema_version"] != envelope.FIXTURE_SCHEMA_VERSION
        or value["g0_contract_frozen"] is not False
        or value["hypothesis_status"] != EXPECTED_HYPOTHESIS_STATUS
        or value["orders"] != EXPECTED_ORDERS
        or value["registry_scope"] != EXPECTED_REGISTRY_SCOPE
        or value["remaining_blockers"] != list(REMAINING_BLOCKERS)
    ):
        _fail("bootstrap profile identity or explicit incompleteness drifted")
    _validate_source_registry(value["source_artifact_registry"])
    claim_keys, dependency_edges = _validate_resolution_entries(
        value["resolution_entries"], value["source_artifact_registry"]
    )
    summary = _exact_dict(value["summary"], SUMMARY_FIELDS, "ledger summary")
    status_counts = {
        status: sum(entry["status"] == status for entry in value["resolution_entries"])
        for status in STATUS_ORDER
    }
    expected_summary = {
        "active_g0_count": status_counts["active-g0"],
        "active_g0_count_zero": status_counts["active-g0"] == 0,
        "active_g0_unresolved_count": status_counts["active-g0"],
        "blocker_claim_count": sum(
            item["blocker_claim_count"] for item in value["source_artifact_registry"]
        ),
        "claim_count": len(value["resolution_entries"]),
        "dependency_edge_count": len(dependency_edges),
        "dependency_graph_sha256": _sha256(_canonical_fragment(dependency_edges)),
        "false_completion_claim_count": sum(
            item["false_completion_claim_count"]
            for item in value["source_artifact_registry"]
        ),
        "ordered_claim_keys_sha256": _sha256(_canonical_fragment(claim_keys)),
        "source_count": len(value["source_artifact_registry"]),
        "source_registry_complete": False,
        "source_registry_sha256": _sha256(
            _canonical_fragment(value["source_artifact_registry"])
        ),
        "status_counts": status_counts,
    }
    if summary != expected_summary:
        _fail("ledger summary is not an exact recomputation")
    if summary["active_g0_unresolved_count"] <= 0 or summary["active_g0_count_zero"]:
        _fail("bootstrap candidate must retain explicit active G0 blockers")


def _validate_against_internal_trust_root(value):
    """Validate against the module-owned immutable source-byte cache only."""

    actual_raw = _preflight_top_level(value)
    snapshot = _strict_json_body(
        actual_raw,
        label="persona v2 G0 blocker-ledger bootstrap opening snapshot",
        max_body_bytes=MAX_LEDGER_BYTES,
    )
    if not hmac.compare_digest(_preflight_top_level(snapshot), actual_raw):
        _fail("bootstrap ledger opening snapshot changed during preflight")
    _validate_semantics(snapshot)
    source_provider = _trusted_source_body
    opening = _opening_source_snapshot(source_provider)
    parsed = _validate_source_snapshot(opening)
    expected = _expected_value(opening, parsed)
    expected_raw = _canonical_fragment(expected)
    if not hmac.compare_digest(actual_raw, expected_raw):
        _fail("bootstrap ledger differs from independent source reconstruction")
    for definition in _SOURCE_DEFINITIONS:
        source_id = definition["source_id"]
        closing = source_provider(source_id)
        if type(closing) is not bytes or not hmac.compare_digest(opening[source_id], closing):
            _fail("registered source changed during ledger validation")
    closing_raw = _preflight_top_level(value)
    if not hmac.compare_digest(actual_raw, closing_raw):
        _fail("bootstrap ledger changed during validation")
    _require_frozen_golden_raw(closing_raw)
    return True


def validate_g0_blocker_resolution_ledger_bootstrap_candidate(value):
    """Validate only the exact non-authorizing bootstrap registry profile."""

    return _validate_against_internal_trust_root(value)


def require_production_g0_blocker_resolution_ledger(value=None):
    """Fail closed even after validating this historical bootstrap profile."""

    if value is not None:
        validate_g0_blocker_resolution_ledger_bootstrap_candidate(value)
    _fail(
        "bootstrap-three-source-v1 is not a production registry profile and is "
        "not closure-eligible"
    )
