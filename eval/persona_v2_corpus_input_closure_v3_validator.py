"""Producer-independent validation for the request-only corpus closure v3.

This module deliberately does not import the sibling closure producer.  It
owns the complete four-pin registry and reconstructs the exact candidate from
literal policy.  The public validator always authenticates the namespace
through the complete all-253 projection/owner chain.  A private trust-source
adapter exists only so ordinary unit tests can exercise the closure state
machine without performing the long all-253 replay.

The accepted body remains non-authorizing: a review request is not a positive
review receipt, the bound blocker ledger is an incomplete three-source
bootstrap, and no solver, identifier, renderer, filesystem, history, KIO, or
G0 capability is granted.
"""

from __future__ import annotations

import functools
import hashlib
import hmac
import json
import unicodedata

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_corpus_semantic_namespace_v3_validator as namespace_validator
    from . import persona_v2_g0_blocker_resolution_ledger_validator as ledger_validator
    from . import persona_v2_review_request_catalog_validator as review_validator
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_corpus_semantic_namespace_v3_validator as namespace_validator
    import persona_v2_g0_blocker_resolution_ledger_validator as ledger_validator
    import persona_v2_review_request_catalog_validator as review_validator


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
MAX_DIRECT_DEPENDENCY_COUNT = 4
MAX_POSITIVE_REVIEW_RECEIPT_COUNT = 7
MAX_IDENTITY_STRING_BYTES = 4 * 2**10
MAX_NESTING_DEPTH = 16
MAX_EXPANDED_NODE_OCCURRENCES = 8_192
MAX_EXPANDED_BYTES = MAX_MANIFEST_BYTES
MAX_CONTAINER_ITEMS = 64
MAX_INTEGER_MAGNITUDE = 2**63 - 1
MAX_CUMULATIVE_DIRECT_DEPENDENCY_BYTES = 20 * 2**20
MAX_PROJECTION_BODY_COUNT = 253
MAX_CUMULATIVE_EXTERNAL_PROJECTION_BYTES = 256 * 2**20
EXACT_CUMULATIVE_EXTERNAL_PROJECTION_BYTES = 155_741_469

# Frozen after two isolated full validations under distinct hash seeds agreed.
EXPECTED_CLOSURE_CANONICAL_BYTES = 7_590
EXPECTED_CLOSURE_SHA256 = (
    "66d78474d80e4aa75266c98bab0177e3dd5196685088acab826580345bb8b245"
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
        "hard_cap": 1 * 2**20,
        "pin": {
            "artifact_kind": (
                "persona-pc-v2-projection-pin-corpus-semantic-namespace"
            ),
            "artifact_schema": "kio.persona.pc-corpus-semantic-namespace/v3",
            "artifact_schema_version": 3,
            "body_framing": "canonical-json",
            "canonical_bytes": 161_665,
            "sha256": (
                "a8bc67e182ff57b64ae6df0f97bd5be31faf6e5f7b7cfbd0bc3f1ba7bc5cc509"
            ),
        },
    },
    "complete-semantic-projection-inventory-v2": {
        "dependency_role": "full-derivation-receipt-and-owner-chain-evidence",
        "input_state": "complete-local-non-authorizing",
        "hard_cap": 2 * 2**20,
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
        "hard_cap": 256 * 2**10,
        "pin": {
            "artifact_kind": (
                "persona-pc-v2-non-authorizing-review-request-catalog"
            ),
            "artifact_schema": "kio.persona.pc-review-request-catalog/v1",
            "artifact_schema_version": 1,
            "body_framing": "canonical-json",
            "canonical_bytes": 42_931,
            "sha256": (
                "3c6eb74ab89f3476650135cd66bd0064cf46c66ac985a0b05891a5974250afb3"
            ),
        },
    },
    "g0-blocker-resolution-ledger-bootstrap-v2": {
        "dependency_role": "historical-blocker-status-bootstrap-evidence",
        "input_state": "bootstrap-incomplete-active",
        "hard_cap": 16 * 2**20,
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

AUTHORITY_FIELDS = frozenset(
    {
        "actual_chunks_attested",
        "actual_lifecycle_receipts_attested",
        "authorizes_compiled_history_plan",
        "authorizes_corpus_input_closure",
        "authorizes_corpus_semantic_namespace",
        "authorizes_final_identifiers",
        "authorizes_g0_freeze",
        "authorizes_history_mutation",
        "authorizes_kio_execution",
        "authorizes_namespace_completion",
        "authorizes_physical_write",
        "authorizes_positive_review_receipt",
        "authorizes_renderer_execution",
        "authorizes_solver_execution",
        "authorizes_source_identity_derivation",
        "authorizes_source_plan",
        "blocker_ledger_authoritative",
        "compiled_history_plan_available",
        "corpus_input_closure_authoritative",
        "corpus_semantic_namespace_available",
        "filesystem_writer_available",
        "formal_capacity_gate_satisfied",
        "history_executor_available",
        "kio_execution_available",
        "physical_materialization_observed",
        "solver_solution_available",
        "source_identity_namespace_authoritative",
    }
)

PIN_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "body_framing",
        "canonical_bytes",
        "sha256",
    }
)
DEPENDENCY_BINDING_FIELDS = frozenset(
    {
        "dependency_id",
        "dependency_ordinal",
        "dependency_pin",
        "dependency_role",
        "input_state",
    }
)
TOP_LEVEL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "blocker_gate",
        "canonical_limits",
        "closure_contract",
        "completion_claims",
        "dependency_bindings",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
        "hypothesis_status",
        "orders",
        "remaining_blockers",
        "review_gate",
        "summary",
    }
)

REMAINING_BLOCKERS = (
    "positive-independent-review-receipts-not-bound",
    "route-independent-human-positive-receipt-not-bound",
    "historical-blocker-source-universe-not-completely-registered",
    "production-namespace-and-positive-review-sources-not-registered-in-ledger",
    "registered-active-g0-claims-not-resolved",
    "authoritative-corpus-input-closure-not-issued",
)


class PersonaV2CorpusInputClosureV3ValidationError(ValueError):
    """Raised when the request-only corpus closure candidate fails closed."""


def _fail(message):
    raise PersonaV2CorpusInputClosureV3ValidationError(message)


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _bounded_string(value, label):
    if type(value) is not str or not value or len(value) > MAX_IDENTITY_STRING_BYTES:
        _fail(f"{label} must be one bounded exact string")
    try:
        encoded = value.encode("utf-8", "strict")
    except UnicodeEncodeError:
        _fail(f"{label} must be valid UTF-8")
    if (
        len(encoded) > MAX_IDENTITY_STRING_BYTES
        or unicodedata.normalize("NFC", value) != value
    ):
        _fail(f"{label} exceeds its UTF-8/NFC bound")
    return value


def _bounded_integer(value, label, *, minimum=0, maximum=MAX_INTEGER_MAGNITUDE):
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
        _fail(f"{label} must be one lowercase SHA-256 digest")
    return value


def _exact_dict(value, fields, label):
    if type(value) is not dict or set(value) != fields:
        _fail(f"{label} must use its exact field schema")
    return value


def _negative_authority():
    return {field: False for field in sorted(AUTHORITY_FIELDS)}


def _dependency_bindings():
    return [
        {
            "dependency_id": dependency_id,
            "dependency_ordinal": ordinal,
            "dependency_pin": json.loads(
                json.dumps(
                    DEPENDENCY_SPECS[dependency_id]["pin"],
                    sort_keys=True,
                    separators=(",", ":"),
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
            dependency_id: DEPENDENCY_SPECS[dependency_id]["hard_cap"]
            for dependency_id in DEPENDENCY_ORDER
        },
        "exact_cumulative_external_projection_bytes": (
            EXACT_CUMULATIVE_EXTERNAL_PROJECTION_BYTES
        ),
        "external_dependency_bodies_embedded": False,
        "external_projection_bodies_embedded": False,
        "framed_byte_cap_before_parse_required": True,
        "max_container_items": MAX_CONTAINER_ITEMS,
        "max_cumulative_direct_dependency_bytes": (
            MAX_CUMULATIVE_DIRECT_DEPENDENCY_BYTES
        ),
        "max_cumulative_external_projection_bytes": (
            MAX_CUMULATIVE_EXTERNAL_PROJECTION_BYTES
        ),
        "max_direct_dependency_count": MAX_DIRECT_DEPENDENCY_COUNT,
        "max_expanded_bytes": MAX_EXPANDED_BYTES,
        "max_expanded_node_occurrences": MAX_EXPANDED_NODE_OCCURRENCES,
        "max_identity_string_bytes": MAX_IDENTITY_STRING_BYTES,
        "max_manifest_bytes": MAX_MANIFEST_BYTES,
        "max_nesting_depth": MAX_NESTING_DEPTH,
        "max_positive_review_receipt_count": MAX_POSITIVE_REVIEW_RECEIPT_COUNT,
        "max_projection_body_count": MAX_PROJECTION_BODY_COUNT,
        "self_hash_embedded": False,
        "target_manifest_bytes": TARGET_MANIFEST_BYTES,
        "unicode_normalization": "NFC",
    }


def _closure_contract():
    return {
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
    }


def _completion_claims():
    return {
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
    }


def _review_gate():
    return {
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
    }


def _blocker_gate():
    return {
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
    }


def _summary():
    return {
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
    }


def _expected_value():
    return {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": _negative_authority(),
        "blocker_gate": _blocker_gate(),
        "canonical_limits": _canonical_limits(),
        "closure_contract": _closure_contract(),
        "completion_claims": _completion_claims(),
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
        "review_gate": _review_gate(),
        "summary": _summary(),
    }


def _preflight_expanded_budget(value):
    stack = [(value, 0)]
    nodes = 0
    expanded_bytes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > MAX_EXPANDED_NODE_OCCURRENCES:
            _fail("closure candidate exceeds its expanded node budget")
        if depth > MAX_NESTING_DEPTH:
            _fail("closure candidate exceeds its nesting budget")
        if type(item) is dict:
            if len(item) > MAX_CONTAINER_ITEMS:
                _fail("closure object exceeds its item budget")
            expanded_bytes += 2 + max(0, len(item) - 1)
            for key, child in item.items():
                _bounded_string(key, "closure object key")
                expanded_bytes += (6 * len(key.encode("utf-8", "strict"))) + 3
                stack.append((child, depth + 1))
        elif type(item) is list:
            if len(item) > MAX_CONTAINER_ITEMS:
                _fail("closure list exceeds its item budget")
            expanded_bytes += 2 + max(0, len(item) - 1)
            stack.extend((child, depth + 1) for child in item)
        elif type(item) is str:
            _bounded_string(item, "closure string")
            expanded_bytes += (6 * len(item.encode("utf-8", "strict"))) + 2
        elif type(item) is bool:
            expanded_bytes += 5
        elif type(item) is int and type(item) is not bool:
            _bounded_integer(item, "closure integer")
            expanded_bytes += 40
        else:
            _fail("closure candidate contains a forbidden scalar type")
        if expanded_bytes > MAX_EXPANDED_BYTES:
            _fail("closure candidate exceeds its expanded byte budget")


def _validate_pin(pin, expected, label):
    _exact_dict(pin, PIN_FIELDS, label)
    for field in ("artifact_kind", "artifact_schema", "body_framing"):
        _bounded_string(pin[field], f"{label} {field}")
    _bounded_integer(
        pin["artifact_schema_version"],
        f"{label} artifact schema version",
        minimum=1,
    )
    _bounded_integer(pin["canonical_bytes"], f"{label} canonical bytes", minimum=1)
    _digest(pin["sha256"], f"{label} SHA-256")
    if pin != expected:
        _fail(f"{label} differs from its exact literal pin")


def _validate_candidate_shape(value):
    # Bound the complete expanded occurrence graph before even copying the
    # caller-owned top-level key set. Shared aliases count on every reference.
    _preflight_expanded_budget(value)
    _exact_dict(value, TOP_LEVEL_FIELDS, "corpus input closure v3")
    if (
        value.get("artifact_kind") != ARTIFACT_KIND
        or value.get("artifact_schema") != ARTIFACT_SCHEMA
        or type(value.get("artifact_schema_version")) is not int
        or type(value.get("artifact_schema_version")) is bool
        or value.get("artifact_schema_version") != ARTIFACT_SCHEMA_VERSION
        or value.get("fixture_id") != FIXTURE_ID
        or type(value.get("fixture_schema_version")) is not int
        or type(value.get("fixture_schema_version")) is bool
        or value.get("fixture_schema_version") != FIXTURE_SCHEMA_VERSION
        or value.get("g0_contract_frozen") is not False
        or value.get("hypothesis_status") != HYPOTHESIS_STATUS
    ):
        _fail("closure identity scalar drifted")
    for field, expected in (
        ("authority", _negative_authority()),
        ("canonical_limits", _canonical_limits()),
        ("closure_contract", _closure_contract()),
        ("completion_claims", _completion_claims()),
        ("review_gate", _review_gate()),
        ("blocker_gate", _blocker_gate()),
        ("remaining_blockers", list(REMAINING_BLOCKERS)),
        ("summary", _summary()),
    ):
        if value.get(field) != expected:
            _fail(f"closure {field} drifted")
    expected_orders = {
        "direct_dependencies": list(DEPENDENCY_ORDER),
        "positive_review_receipts": [],
        "remaining_blockers": list(REMAINING_BLOCKERS),
    }
    if value.get("orders") != expected_orders:
        _fail("closure orders drifted")
    bindings = value.get("dependency_bindings")
    if type(bindings) is not list or len(bindings) != MAX_DIRECT_DEPENDENCY_COUNT:
        _fail("closure must bind exactly four direct dependencies")
    ids = []
    digests = []
    for ordinal, row in enumerate(bindings, start=1):
        _exact_dict(row, DEPENDENCY_BINDING_FIELDS, "dependency binding")
        dependency_id = _bounded_string(row.get("dependency_id"), "dependency ID")
        ids.append(dependency_id)
        spec = DEPENDENCY_SPECS.get(dependency_id)
        if spec is None:
            _fail("closure dependency ID is outside the literal registry")
        if (
            row.get("dependency_ordinal") != ordinal
            or row.get("dependency_role") != spec["dependency_role"]
            or row.get("input_state") != spec["input_state"]
        ):
            _fail("closure dependency order, role, or state drifted")
        _validate_pin(
            row.get("dependency_pin"),
            spec["pin"],
            f"dependency {dependency_id} pin",
        )
        digests.append(row["dependency_pin"]["sha256"])
    if tuple(ids) != DEPENDENCY_ORDER or len(set(ids)) != len(ids):
        _fail("closure dependency order or uniqueness drifted")
    if len(set(digests)) != len(digests):
        _fail("closure dependency body pins alias one another")


def _canonical_candidate(value, *, label="corpus input closure v3 candidate"):
    _validate_candidate_shape(value)
    try:
        raw = artifact_common.canonical_json_bytes(
            value,
            label=label,
            max_bytes=MAX_MANIFEST_BYTES,
        )
    except (RecursionError, artifact_common.PersonaV2ArtifactError) as error:
        _fail(str(error))
    if len(raw) > TARGET_MANIFEST_BYTES:
        _fail("closure candidate exceeds its authored 64-KiB target")
    if (
        EXPECTED_CLOSURE_CANONICAL_BYTES is not None
        and len(raw) != EXPECTED_CLOSURE_CANONICAL_BYTES
    ):
        _fail("closure candidate canonical byte length drifted")
    digest = _sha256(raw)
    if (
        EXPECTED_CLOSURE_SHA256 is not None
        and not hmac.compare_digest(digest, EXPECTED_CLOSURE_SHA256)
    ):
        _fail("closure candidate SHA-256 drifted")
    return raw


@functools.lru_cache(maxsize=1)
def _expected_raw():
    # Cache immutable bytes only.  No caller can poison an expected container.
    return _canonical_candidate(_expected_value(), label="expected corpus closure v3")


def _preflight_candidate(value):
    """Bound and canonicalize a caller-owned candidate before any callback."""

    raw = _canonical_candidate(value)
    if not hmac.compare_digest(raw, _expected_raw()):
        _fail("closure candidate differs from independent reconstruction")
    return raw


def _strict_json_object(raw, *, label, maximum):
    if type(raw) is not bytes or not raw or len(raw) > maximum:
        _fail(f"{label} must be exact bytes within its pre-read cap")
    if raw.startswith(b"\xef\xbb\xbf"):
        _fail(f"{label} must not contain a UTF-8 BOM")

    def object_pairs(pairs):
        result = {}
        for key, child in pairs:
            if key in result:
                _fail(f"{label} contains a duplicate object key")
            result[key] = child
        return result

    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=object_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
            parse_float=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except PersonaV2CorpusInputClosureV3ValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
        _fail(f"{label} is not strict UTF-8 JSON")
    if type(value) is not dict:
        _fail(f"{label} must be one JSON object")
    try:
        canonical = artifact_common.canonical_json_bytes(
            value,
            label=label,
            max_bytes=maximum,
        )
    except (RecursionError, artifact_common.PersonaV2ArtifactError) as error:
        _fail(str(error))
    if not hmac.compare_digest(canonical, raw):
        _fail(f"{label} is not exact canonical JSON")
    return value


def _authenticate_dependency_body(raw, binding):
    dependency_id = binding["dependency_id"]
    spec = DEPENDENCY_SPECS[dependency_id]
    pin = binding["dependency_pin"]
    hard_cap = spec["hard_cap"]
    if type(raw) is not bytes or len(raw) > hard_cap:
        _fail(f"dependency {dependency_id} exceeds its framed byte cap")
    if len(raw) != pin["canonical_bytes"]:
        _fail(f"dependency {dependency_id} byte length differs from its pin")
    if not hmac.compare_digest(_sha256(raw), pin["sha256"]):
        _fail(f"dependency {dependency_id} digest differs from its pin")
    value = _strict_json_object(
        raw,
        label=f"dependency {dependency_id}",
        maximum=hard_cap,
    )
    if (
        value.get("artifact_kind") != pin["artifact_kind"]
        or value.get("artifact_schema") != pin["artifact_schema"]
        or value.get("artifact_schema_version") != pin["artifact_schema_version"]
    ):
        _fail(f"dependency {dependency_id} identity differs from its pin")
    return value


def _validate_review_semantics(value):
    requests = value.get("review_requests")
    if type(requests) is not list or len(requests) != 7:
        _fail("review request dependency must contain exactly seven requests")
    if value.get("summary", {}).get("positive_receipt_count") != 0:
        _fail("review request dependency unexpectedly binds a positive receipt")
    by_class = {row.get("review_class_id"): row for row in requests}
    if len(by_class) != 7:
        _fail("review request classes are not unique")
    route = by_class.get("route-human")
    if (
        type(route) is not dict
        or route.get("request_id") != "persona-v2-review-request-route-human"
        or route.get("required_reviewer_kind") != "independent-human"
        or route.get("positive_receipt_bound") is not False
    ):
        _fail("route-human request dependency drifted")
    inventory_request = by_class.get("semantic-projection-inventory")
    subjects = (
        [] if type(inventory_request) is not dict else inventory_request.get("subject_pins")
    )
    if type(subjects) is not list or len(subjects) != 1:
        _fail("inventory review request must bind one exact inventory subject")
    subject = subjects[0]
    inventory_pin = DEPENDENCY_SPECS[
        "complete-semantic-projection-inventory-v2"
    ]["pin"]
    for field in PIN_FIELDS:
        if subject.get(field) != inventory_pin[field]:
            _fail("review request inventory subject differs from the closure pin")


def _validate_ledger_semantics(value):
    summary = value.get("summary")
    completion = value.get("completion_claims")
    scope = value.get("registry_scope")
    if (
        type(summary) is not dict
        or summary.get("source_count") != 3
        or summary.get("claim_count") != 36
        or summary.get("blocker_claim_count") != 21
        or summary.get("false_completion_claim_count") != 15
        or summary.get("active_g0_unresolved_count") != 36
        or summary.get("status_counts")
        != {
            "active-g0": 36,
            "deferred-post-g0": 0,
            "historical-local-negative": 0,
            "resolved-by-downstream-pin": 0,
        }
        or type(completion) is not dict
        or completion.get("closure_eligible") is not False
        or completion.get("g0_eligible") is not False
        or completion.get("all_active_g0_blockers_resolved") is not False
        or type(scope) is not dict
        or scope.get("historical_source_universe_complete") is not False
        or scope.get("source_registry_complete") is not False
    ):
        _fail("blocker ledger dependency is not the exact active bootstrap")


class _FullTrustSource:
    """Full direct-body and transitive all-253 trust-source adapter."""

    def __init__(self, dependency_body_provider, projection_body_provider):
        if not callable(dependency_body_provider):
            _fail("direct dependency body provider must be callable")
        if not callable(projection_body_provider):
            _fail("projection body provider must be callable")
        self._dependency_body_provider = dependency_body_provider
        self._projection_body_provider = projection_body_provider
        self._opening = {}
        self._values = {}
        self._inventory_validated = False

    def open(self, bindings):
        cumulative = 0
        for binding in bindings:
            dependency_id = binding["dependency_id"]
            try:
                raw = self._dependency_body_provider(dependency_id)
            except Exception:
                _fail(f"dependency provider failed for {dependency_id}")
            if type(raw) is not bytes:
                _fail(f"dependency provider returned non-bytes for {dependency_id}")
            cumulative += len(raw)
            if cumulative > MAX_CUMULATIVE_DIRECT_DEPENDENCY_BYTES:
                _fail("direct dependency bodies exceed their cumulative cap")
            self._opening[dependency_id] = raw
            self._values[dependency_id] = _authenticate_dependency_body(raw, binding)
        return True

    def validate(self, binding):
        dependency_id = binding["dependency_id"]
        value = self._values[dependency_id]
        if dependency_id == "corpus-semantic-namespace-v3":
            inventory = self._values[
                "complete-semantic-projection-inventory-v2"
            ]
            try:
                result = namespace_validator.validate_corpus_semantic_namespace_v3(
                    value,
                    complete_inventory=inventory,
                    projection_body_provider=self._projection_body_provider,
                )
            except Exception:
                _fail("namespace and complete-inventory trust-source validation failed")
            if result is not True:
                _fail("namespace validator did not return exact true")
            self._inventory_validated = True
        elif dependency_id == "complete-semantic-projection-inventory-v2":
            if not self._inventory_validated:
                _fail("complete inventory was not traversed through the namespace")
            if (
                value.get("summary", {}).get("derivation_receipt_count") != 253
                or value.get("summary", {}).get(
                    "cumulative_external_projection_bytes"
                )
                != EXACT_CUMULATIVE_EXTERNAL_PROJECTION_BYTES
            ):
                _fail("complete inventory summary drifted")
        elif dependency_id == "review-request-catalog-v1":
            try:
                result = review_validator.validate_review_request_catalog(value)
            except Exception:
                _fail("review request trust-source validation failed")
            if result is not True:
                _fail("review request validator did not return exact true")
            _validate_review_semantics(value)
        elif dependency_id == "g0-blocker-resolution-ledger-bootstrap-v2":
            raw = self._opening[dependency_id]
            try:
                loaded = ledger_validator.load_and_validate_g0_blocker_resolution_ledger_bootstrap_candidate(
                    raw
                )
            except Exception:
                _fail("blocker ledger trust-source validation failed")
            _validate_ledger_semantics(loaded)
        else:  # pragma: no cover - guarded by exact literal registry.
            _fail("unknown direct dependency")
        return True

    def close(self):
        for dependency_id in DEPENDENCY_ORDER:
            try:
                closing = self._dependency_body_provider(dependency_id)
            except Exception:
                _fail(f"dependency provider closing read failed for {dependency_id}")
            if (
                type(closing) is not bytes
                or not hmac.compare_digest(self._opening[dependency_id], closing)
            ):
                _fail(f"dependency {dependency_id} changed during validation")
        return True


def _validate_with_trust_source(value, trust_source):
    """Validate the exact candidate through an explicit trust-source protocol.

    This is private because only ``_FullTrustSource`` establishes the production
    dependency chain.  Tests may supply a mock solely to exercise orchestration;
    no accepted digest helper exposes that path.
    """

    opening_raw = _preflight_candidate(value)
    if not hmac.compare_digest(opening_raw, _expected_raw()):
        _fail("closure candidate differs from independent reconstruction")
    for method_name in ("open", "validate", "close"):
        if not callable(getattr(trust_source, method_name, None)):
            _fail("closure trust source does not implement its exact protocol")
    bindings = json.loads(json.dumps(value["dependency_bindings"]))
    opened = False
    validation_failure = None
    try:
        if trust_source.open(bindings) is not True:
            _fail("closure trust source opening did not return exact true")
        opened = True
        for binding in bindings:
            if trust_source.validate(binding) is not True:
                _fail("closure trust source validation did not return exact true")
    except Exception as error:
        validation_failure = error

    # Once an opening has been accepted, both postflights are mandatory even
    # when semantic validation fails.  This prevents a failing validator from
    # suppressing dependency or caller-owned-object TOCTOU detection.
    postflight_failure = None
    if opened:
        try:
            if trust_source.close() is not True:
                _fail("closure trust source closing did not return exact true")
        except Exception as error:
            postflight_failure = error
    try:
        closing_raw = _preflight_candidate(value)
        if not hmac.compare_digest(opening_raw, closing_raw):
            _fail("caller-owned closure candidate changed during validation")
    except Exception as error:
        if postflight_failure is None:
            postflight_failure = error

    if postflight_failure is not None:
        raise postflight_failure
    if validation_failure is not None:
        raise validation_failure
    return True


def validate_corpus_input_closure_v3(
    value,
    *,
    dependency_body_provider,
    projection_body_provider,
):
    """Fully validate all four direct bodies and the transitive all-253 chain."""

    trust_source = _FullTrustSource(
        dependency_body_provider,
        projection_body_provider,
    )
    return _validate_with_trust_source(value, trust_source)


def validate_corpus_input_closure_v3_bytes(
    raw,
    *,
    dependency_body_provider,
    projection_body_provider,
):
    """Strict duplicate-key-aware full-validation bytes entry point."""

    value = _strict_json_object(
        raw,
        label="framed corpus input closure v3",
        maximum=MAX_MANIFEST_BYTES,
    )
    return validate_corpus_input_closure_v3(
        value,
        dependency_body_provider=dependency_body_provider,
        projection_body_provider=projection_body_provider,
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
    "PersonaV2CorpusInputClosureV3ValidationError",
    "validate_corpus_input_closure_v3",
    "validate_corpus_input_closure_v3_bytes",
]
