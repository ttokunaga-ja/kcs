"""Request-only, non-authorizing persona-PC corpus input closure v3.

The manifest binds exactly four compact pins: the projection-pin semantic
namespace, the complete projection derivation inventory, the seven-class
review-request catalog, and the incomplete three-source blocker ledger.  It
embeds none of those bodies and binds no positive review receipt.

Building this candidate grants no authority.  Public validation and accepted
hashing always cross the producer-independent validator and traverse the
namespace's complete all-253 projection/owner chain.
"""

from __future__ import annotations

import functools
import hashlib
import hmac
import json

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_corpus_input_closure_v3_validator as independent
    from . import persona_v2_corpus_semantic_namespace_v3 as namespace
    from . import persona_v2_g0_blocker_resolution_ledger as ledger
    from . import persona_v2_review_request_catalog as review
    from . import persona_v2_semantic_projection_complete_inventory as complete
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_corpus_input_closure_v3_validator as independent
    import persona_v2_corpus_semantic_namespace_v3 as namespace
    import persona_v2_g0_blocker_resolution_ledger as ledger
    import persona_v2_review_request_catalog as review
    import persona_v2_semantic_projection_complete_inventory as complete


ARTIFACT_SCHEMA = "kio.persona.pc-corpus-input-closure-manifest/v3"
ARTIFACT_KIND = (
    "persona-pc-v2-corpus-input-closure-manifest-request-only-candidate"
)
ARTIFACT_SCHEMA_VERSION = 3
FIXTURE_ID = "kio-persona-pc-v2"
FIXTURE_SCHEMA_VERSION = 2
HYPOTHESIS_STATUS = (
    "authored-benchmark-request-only-corpus-input-closure-candidate-"
    "not-observed-user-data"
)

MAX_MANIFEST_BYTES = 256 * 2**10
TARGET_MANIFEST_BYTES = 64 * 2**10

# Frozen after two isolated full build+validation measurements agreed.
EXPECTED_CLOSURE_CANONICAL_BYTES = 7_590
EXPECTED_CLOSURE_SHA256 = (
    "cd2dbcf3829beb13c2278d93f2d410df8f99611dabc7a3e4c6ce579f671a53ec"
)

DEPENDENCY_ORDER = (
    "corpus-semantic-namespace-v3",
    "complete-semantic-projection-inventory-v2",
    "review-request-catalog-v1",
    "g0-blocker-resolution-ledger-bootstrap-v2",
)

DEPENDENCY_SPECS = {
    "corpus-semantic-namespace-v3": {
        "dependency_role": "projection-pin-only-semantic-root",
        "input_state": "complete-local-unissued",
        "pin": {
            "artifact_kind": (
                "persona-pc-v2-projection-pin-corpus-semantic-namespace"
            ),
            "artifact_schema": "kio.persona.pc-corpus-semantic-namespace/v3",
            "artifact_schema_version": 3,
            "body_framing": "canonical-json",
            "canonical_bytes": 161_665,
            "sha256": (
                "bbb0941e7e640130fb57e07c1301991679c2dea80407573b82e9ef575b074637"
            ),
        },
    },
    "complete-semantic-projection-inventory-v2": {
        "dependency_role": "full-derivation-receipt-and-owner-chain-evidence",
        "input_state": "complete-local-non-authorizing",
        "pin": {
            "artifact_kind": (
                "persona-pc-v2-complete-semantic-projection-derivation-inventory"
            ),
            "artifact_schema": (
                "kio.persona.pc-semantic-projection-derivation-inventory/v2"
            ),
            "artifact_schema_version": 2,
            "body_framing": "canonical-json",
            "canonical_bytes": 697_466,
            "sha256": (
                "820c976a930c3f2ed0a54e44c08b01cad8a0879513f1b06012e353fb9bd3fd91"
            ),
        },
    },
    "review-request-catalog-v1": {
        "dependency_role": "review-request-definition-only-not-positive-evidence",
        "input_state": "request-definition-only",
        "pin": {
            "artifact_kind": (
                "persona-pc-v2-non-authorizing-review-request-catalog"
            ),
            "artifact_schema": "kio.persona.pc-review-request-catalog/v1",
            "artifact_schema_version": 1,
            "body_framing": "canonical-json",
            "canonical_bytes": 42_931,
            "sha256": (
                "3e1231d76aea401931f9a15cc20438918033146d39e50e38ab4c4fd36676efe5"
            ),
        },
    },
    "g0-blocker-resolution-ledger-bootstrap-v2": {
        "dependency_role": "historical-blocker-status-bootstrap-evidence",
        "input_state": "bootstrap-incomplete-active",
        "pin": {
            "artifact_kind": (
                "persona-pc-v2-g0-blocker-resolution-ledger-candidate"
            ),
            "artifact_schema": (
                "kio.persona.pc-g0-blocker-resolution-ledger/v2"
            ),
            "artifact_schema_version": 2,
            "body_framing": "canonical-json",
            "canonical_bytes": 21_645,
            "sha256": (
                "48c9c36a965fbae34b1a89b041515a267284149801120b12e16b548fc4a96c97"
            ),
        },
    },
}

AUTHORITY_FIELDS = frozenset(independent.AUTHORITY_FIELDS)
REMAINING_BLOCKERS = (
    "positive-independent-review-receipts-not-bound",
    "route-independent-human-positive-receipt-not-bound",
    "historical-blocker-source-universe-not-completely-registered",
    "production-namespace-and-positive-review-sources-not-registered-in-ledger",
    "registered-active-g0-claims-not-resolved",
    "authoritative-corpus-input-closure-not-issued",
)


class PersonaV2CorpusInputClosureV3Error(ValueError):
    """Raised when the request-only closure candidate fails closed."""


def _fail(message):
    raise PersonaV2CorpusInputClosureV3Error(message)


def _negative_authority():
    return {field: False for field in sorted(AUTHORITY_FIELDS)}


def _dependency_bindings():
    return [
        {
            "dependency_id": dependency_id,
            "dependency_ordinal": ordinal,
            "dependency_pin": json.loads(
                artifact_common.canonical_json_bytes(
                    DEPENDENCY_SPECS[dependency_id]["pin"],
                    label="corpus closure dependency pin",
                    max_bytes=8 * 2**10,
                )
            ),
            "dependency_role": DEPENDENCY_SPECS[dependency_id][
                "dependency_role"
            ],
            "input_state": DEPENDENCY_SPECS[dependency_id]["input_state"],
        }
        for ordinal, dependency_id in enumerate(DEPENDENCY_ORDER, start=1)
    ]


def _canonical_limits():
    return {
        "dependency_body_hard_caps": {
            "corpus-semantic-namespace-v3": 1 * 2**20,
            "complete-semantic-projection-inventory-v2": 2 * 2**20,
            "review-request-catalog-v1": 256 * 2**10,
            "g0-blocker-resolution-ledger-bootstrap-v2": 16 * 2**20,
        },
        "exact_cumulative_external_projection_bytes": 155_741_381,
        "external_dependency_bodies_embedded": False,
        "external_projection_bodies_embedded": False,
        "framed_byte_cap_before_parse_required": True,
        "max_container_items": 64,
        "max_cumulative_direct_dependency_bytes": 20 * 2**20,
        "max_cumulative_external_projection_bytes": 256 * 2**20,
        "max_direct_dependency_count": 4,
        "max_expanded_bytes": MAX_MANIFEST_BYTES,
        "max_expanded_node_occurrences": 8_192,
        "max_identity_string_bytes": 4 * 2**10,
        "max_manifest_bytes": MAX_MANIFEST_BYTES,
        "max_nesting_depth": 16,
        "max_positive_review_receipt_count": 7,
        "max_projection_body_count": 253,
        "self_hash_embedded": False,
        "target_manifest_bytes": TARGET_MANIFEST_BYTES,
        "unicode_normalization": "NFC",
    }


def _candidate_value():
    return {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": _negative_authority(),
        "blocker_gate": {
            "active_g0_unresolved_count": 36,
            "blocker_claim_count": 21,
            "blocker_ledger_dependency_id": (
                "g0-blocker-resolution-ledger-bootstrap-v2"
            ),
            "claim_count": 36,
            "closure_eligible": False,
            "false_completion_claim_count": 15,
            "g0_eligible": False,
            "historical_blocker_universe_complete": False,
            "registry_profile_id": "bootstrap-three-source-v1",
            "source_count": 3,
            "source_registry_complete": False,
        },
        "canonical_limits": _canonical_limits(),
        "closure_contract": {
            "complete_inventory_full_replay_required": True,
            "dependency_graph_shape": "single-root-direct-pin-set",
            "external_dependency_bodies_embedded": False,
            "external_projection_bodies_embedded": False,
            "only_corpus_inputs_bound": True,
            "positive_receipt_absence_forces_non_authorizing": True,
            "review_request_is_positive_review_evidence": False,
            "solution_final_ids_render_materialization_history_execution_excluded": True,
            "source_identity_derivation_authorized": False,
            "source_owner_suites_are_transitive_inventory_dependencies": True,
        },
        "completion_claims": {
            "all_253_projection_receipts_independently_replayed": True,
            "all_active_g0_blockers_resolved": False,
            "blocker_ledger_bootstrap_bound": True,
            "complete_projection_inventory_bound": True,
            "corpus_input_closure_complete": False,
            "corpus_semantic_namespace_approved": False,
            "namespace_pin_bound": True,
            "positive_independent_review_receipts_bound": False,
            "production_blocker_ledger_complete": False,
            "review_request_catalog_bound": True,
            "route_independent_human_positive_receipt_bound": False,
            "transitive_source_owner_chains_validated": True,
        },
        "dependency_bindings": _dependency_bindings(),
        "fixture_id": FIXTURE_ID,
        "fixture_schema_version": FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "hypothesis_status": HYPOTHESIS_STATUS,
        "orders": {
            "direct_dependencies": list(DEPENDENCY_ORDER),
            "positive_review_receipts": [],
            "remaining_blockers": list(REMAINING_BLOCKERS),
        },
        "remaining_blockers": list(REMAINING_BLOCKERS),
        "review_gate": {
            "all_required_positive_receipts_bound": False,
            "positive_review_receipt_bindings": [],
            "positive_review_receipt_count": 0,
            "request_catalog_is_positive_evidence": False,
            "required_positive_receipt_count": 7,
            "required_review_request_count": 7,
            "review_request_catalog_dependency_id": "review-request-catalog-v1",
            "route_human_positive_receipt_bound": False,
            "route_human_request_id": "persona-v2-review-request-route-human",
            "route_human_required_reviewer_kind": "independent-human",
        },
        "summary": {
            "active_g0_unresolved_count": 36,
            "authority_grant_count": 0,
            "blocking_dependency_count": 2,
            "complete_local_dependency_count": 3,
            "corpus_input_closure_complete": False,
            "direct_dependency_count": 4,
            "external_body_embedded_count": 0,
            "positive_review_receipt_count": 0,
            "projection_body_count": 253,
            "review_request_count": 7,
            "transitive_full_owner_suite_count": 3,
        },
    }


def _require_dependency_constant_alignment():
    actual = {
        "corpus-semantic-namespace-v3": (
            namespace.NAMESPACE_KIND,
            namespace.NAMESPACE_SCHEMA,
            namespace.ARTIFACT_SCHEMA_VERSION,
            namespace.EXPECTED_NAMESPACE_CANONICAL_BYTES,
            namespace.EXPECTED_NAMESPACE_SHA256,
        ),
        "complete-semantic-projection-inventory-v2": (
            complete.SUITE_KIND,
            complete.SUITE_SCHEMA,
            complete.ARTIFACT_SCHEMA_VERSION,
            complete.EXPECTED_SUITE_CANONICAL_BYTES,
            complete.EXPECTED_SUITE_SHA256,
        ),
        "review-request-catalog-v1": (
            review.ARTIFACT_KIND,
            review.ARTIFACT_SCHEMA,
            review.ARTIFACT_SCHEMA_VERSION,
            review.EXPECTED_CATALOG_BYTES,
            review.EXPECTED_CATALOG_SHA256,
        ),
        "g0-blocker-resolution-ledger-bootstrap-v2": (
            ledger.ARTIFACT_KIND,
            ledger.ARTIFACT_SCHEMA,
            ledger.ARTIFACT_SCHEMA_VERSION,
            ledger.EXPECTED_BOOTSTRAP_CANDIDATE_CANONICAL_BYTES,
            ledger.EXPECTED_BOOTSTRAP_CANDIDATE_SHA256,
        ),
    }
    for dependency_id in DEPENDENCY_ORDER:
        pin = DEPENDENCY_SPECS[dependency_id]["pin"]
        expected = (
            pin["artifact_kind"],
            pin["artifact_schema"],
            pin["artifact_schema_version"],
            pin["canonical_bytes"],
            pin["sha256"],
        )
        if actual[dependency_id] != expected:
            _fail(f"current dependency constants drifted for {dependency_id}")


def _canonical_unchecked(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 corpus input closure v3",
            max_bytes=MAX_MANIFEST_BYTES,
        )
    except (RecursionError, artifact_common.PersonaV2ArtifactError) as error:
        _fail(str(error))


def corpus_input_closure_v3_candidate_bytes(value):
    """Canonicalize one exact candidate without granting acceptance."""

    try:
        independent._preflight_candidate(value)
    except independent.PersonaV2CorpusInputClosureV3ValidationError as error:
        _fail(str(error))
    raw = _canonical_unchecked(value)
    if len(raw) > TARGET_MANIFEST_BYTES:
        _fail("closure candidate exceeds its authored target")
    return raw


@functools.lru_cache(maxsize=1)
def _canonical_candidate_raw():
    _require_dependency_constant_alignment()
    raw = corpus_input_closure_v3_candidate_bytes(_candidate_value())
    if (
        EXPECTED_CLOSURE_CANONICAL_BYTES is not None
        and len(raw) != EXPECTED_CLOSURE_CANONICAL_BYTES
    ):
        _fail("closure candidate canonical byte length drifted")
    if (
        EXPECTED_CLOSURE_SHA256 is not None
        and not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), EXPECTED_CLOSURE_SHA256)
    ):
        _fail("closure candidate SHA-256 drifted")
    return raw


def build_corpus_input_closure_v3():
    """Return a detached request-only closure candidate."""

    _require_dependency_constant_alignment()
    return json.loads(_canonical_candidate_raw().decode("utf-8"))


def _authenticate_cached_dependency_body(dependency_id, raw):
    """Recheck one immutable snapshot body against its literal frozen pin."""

    spec = DEPENDENCY_SPECS.get(dependency_id)
    if spec is None:
        _fail("dependency provider received an unknown dependency ID")
    pin = spec["pin"]
    if (
        type(raw) is not bytes
        or len(raw) != pin["canonical_bytes"]
        or not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), pin["sha256"])
    ):
        _fail(f"cached dependency body drifted for {dependency_id}")
    return raw


def _build_canonical_dependency_snapshot():
    """Build each direct body once, sharing one complete-inventory value."""

    _require_dependency_constant_alignment()
    complete_value = complete.build_semantic_projection_complete_inventory()
    complete_raw = complete.canonical_json_bytes(complete_value)
    namespace_value = namespace.build_corpus_semantic_namespace_v3(
        complete_inventory=complete_value
    )
    namespace_raw = namespace.corpus_semantic_namespace_v3_candidate_bytes(
        namespace_value
    )
    review_raw = review.review_request_catalog_bytes()
    ledger_value = ledger.build_g0_blocker_resolution_ledger_bootstrap_candidate()
    ledger_raw = ledger.canonical_bootstrap_candidate_json_bytes(ledger_value)
    snapshot = (namespace_raw, complete_raw, review_raw, ledger_raw)
    for dependency_id, raw in zip(DEPENDENCY_ORDER, snapshot):
        _authenticate_cached_dependency_body(dependency_id, raw)
    return snapshot


@functools.lru_cache(maxsize=1)
def _canonical_dependency_snapshot():
    """Cache only one immutable tuple of exact canonical byte strings."""

    return _build_canonical_dependency_snapshot()


def _current_dependency_body(dependency_id):
    """Return a pinned snapshot body while preserving opening/closing reads."""

    _require_dependency_constant_alignment()
    try:
        index = DEPENDENCY_ORDER.index(dependency_id)
    except ValueError:
        _fail("dependency provider received an unknown dependency ID")
    snapshot = _canonical_dependency_snapshot()
    if (
        type(snapshot) is not tuple
        or len(snapshot) != len(DEPENDENCY_ORDER)
        or any(type(raw) is not bytes for raw in snapshot)
    ):
        _fail("cached dependency snapshot is not immutable exact bytes")
    return _authenticate_cached_dependency_body(dependency_id, snapshot[index])


def validate_corpus_input_closure_v3(value):
    """Run normal full validation, including all 253 projection bodies."""

    opening_raw = corpus_input_closure_v3_candidate_bytes(value)
    try:
        result = independent.validate_corpus_input_closure_v3(
            value,
            dependency_body_provider=_current_dependency_body,
            projection_body_provider=complete.projection_body_provider,
        )
    except independent.PersonaV2CorpusInputClosureV3ValidationError as error:
        _fail(str(error))
    finally:
        closing_raw = corpus_input_closure_v3_candidate_bytes(value)
        if not hmac.compare_digest(opening_raw, closing_raw):
            _fail("caller-owned closure candidate changed during validation")
    if result is not True:
        _fail("independent closure validator did not return exact true")
    return True


def accepted_corpus_input_closure_v3_sha256(value=None):
    """Hash only the immutable opening bytes accepted by full validation."""

    if value is None:
        value = build_corpus_input_closure_v3()
    opening_raw = corpus_input_closure_v3_candidate_bytes(value)
    validate_corpus_input_closure_v3(value)
    closing_raw = corpus_input_closure_v3_candidate_bytes(value)
    if not hmac.compare_digest(opening_raw, closing_raw):
        _fail("closure candidate changed while producing its accepted digest")
    return hashlib.sha256(opening_raw).hexdigest()


def require_corpus_input_closure_v3_candidate():
    """Return the fully validated candidate without implying completion."""

    value = build_corpus_input_closure_v3()
    validate_corpus_input_closure_v3(value)
    return value


def require_authoritative_corpus_input_closure_v3():
    """Fail closed: request-only evidence cannot authorize a closure."""

    raise PersonaV2CorpusInputClosureV3Error(
        "the request-only v3 candidate has no positive review receipts, binds "
        "an incomplete active blocker ledger, and is not authoritative"
    )


__all__ = [
    "ARTIFACT_KIND",
    "ARTIFACT_SCHEMA",
    "ARTIFACT_SCHEMA_VERSION",
    "AUTHORITY_FIELDS",
    "DEPENDENCY_ORDER",
    "DEPENDENCY_SPECS",
    "EXPECTED_CLOSURE_CANONICAL_BYTES",
    "EXPECTED_CLOSURE_SHA256",
    "MAX_MANIFEST_BYTES",
    "PersonaV2CorpusInputClosureV3Error",
    "accepted_corpus_input_closure_v3_sha256",
    "build_corpus_input_closure_v3",
    "corpus_input_closure_v3_candidate_bytes",
    "require_authoritative_corpus_input_closure_v3",
    "require_corpus_input_closure_v3_candidate",
    "validate_corpus_input_closure_v3",
]
