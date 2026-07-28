"""Producer-independent validator for the complete 253-body inventory."""

from __future__ import annotations

import copy
import functools
import hashlib
import hmac
import json

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_payload_equivalence_rule_catalog_validator as payload_validator
    from . import persona_v2_semantic_projection_corpus_content_validator as corpus_validator
    from . import (
        persona_v2_semantic_projection_derivation_inventory_validator as partial_validator,
    )
    from . import persona_v2_semantic_projection_global_content_validator as global_validator
    from . import (
        persona_v2_semantic_projection_relations_parameters_validator as relations_validator,
    )
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_payload_equivalence_rule_catalog_validator as payload_validator
    import persona_v2_semantic_projection_corpus_content_validator as corpus_validator
    import persona_v2_semantic_projection_derivation_inventory_validator as partial_validator
    import persona_v2_semantic_projection_global_content_validator as global_validator
    import persona_v2_semantic_projection_relations_parameters_validator as relations_validator


ARTIFACT_SCHEMA_VERSION = 2
SUITE_SCHEMA = "kio.persona.pc-semantic-projection-derivation-inventory/v2"
SUITE_KIND = "persona-pc-v2-complete-semantic-projection-derivation-inventory"
RECEIPT_SCHEMA = "kio.persona.pc-semantic-projection-derivation-receipt/v2"
PARTIAL_V1_RECEIPT_SCHEMA = (
    "kio.persona.pc-semantic-projection-derivation-receipt/v1"
)

PROJECTION_CLASS_ORDER = (
    "topology-path-load",
    "realism-locale-security",
    "route-scores",
    "primary-use-case-corpus-half",
    "recipe-content-filename-policy",
    "fact-graph",
    "base-source-content-context",
    "effective-source-membership",
    "concrete-overlay-relations",
    "source-instance-parameters",
    "query-independent-lifecycle-fact-rendition-rules",
    "payload-equivalence-rules",
)
EXPECTED_RECEIPT_COUNTS = {
    "topology-path-load": 1,
    "realism-locale-security": 1,
    "route-scores": 1,
    "primary-use-case-corpus-half": 1,
    "recipe-content-filename-policy": 1,
    "fact-graph": 20,
    "base-source-content-context": 73,
    "effective-source-membership": 20,
    "concrete-overlay-relations": 40,
    "source-instance-parameters": 74,
    "query-independent-lifecycle-fact-rendition-rules": 20,
    "payload-equivalence-rules": 1,
}
EXPECTED_UNUSED_PARAMETER_CELL_KEYS = frozenset(
    {
        "archive-zip/ordinary-max",
        "lms-ustar/ordinary-max",
        "model-metadata-zip/ordinary-max",
        "npz/ordinary-max",
        "product-export-zip/ordinary-max",
        "session-ustar/ordinary-max",
        "snapshot-ustar/ordinary-max",
        "team-export-ustar/ordinary-max",
        "tiff-ustar/ordinary-max",
    }
)

MAX_SUITE_BYTES = 2 * 2**20
TARGET_SUITE_BYTES = 1 * 2**20
MAX_RECEIPT_COUNT = 253
MAX_CUMULATIVE_EXTERNAL_BODY_BYTES = 256 * 2**20
MAX_JSON_BODY_BYTES = 384 * 2**10
MAX_JSONL_BODY_BYTES = 4 * 2**20
MAX_JSONL_ROWS = 4_096
MAX_BASE_OR_OVERLAY_ROW_BYTES_INCLUDING_LF = 768
MAX_PARAMETER_ROW_BYTES_INCLUDING_LF = 256
TARGET_JSON_BODY_BYTES = 256 * 2**10

EXPECTED_SUITE_CANONICAL_BYTES = 697_466
EXPECTED_SUITE_SHA256 = (
    "6826fb14293e7147159fae1849f93533c35ae76f1beecbd093d190cd6ddd3e69"
)
EXPECTED_CUMULATIVE_EXTERNAL_BODY_BYTES_FROZEN = 155_741_469
EXPECTED_ORDERED_PROJECTION_PINS_SHA256 = (
    "f524ddcccdd89a216b87d2ad8f98076c8eacabbc258e7b68d514162764a3a97c"
)

AUTHORITY_FIELDS = frozenset(
    {
        "actual_chunks_attested",
        "actual_lifecycle_receipts_attested",
        "authorizes_compiled_history_plan",
        "authorizes_corpus_semantic_namespace",
        "authorizes_final_identifiers",
        "authorizes_g0_freeze",
        "authorizes_history_mutation",
        "authorizes_kio_execution",
        "authorizes_namespace_completion",
        "authorizes_physical_write",
        "authorizes_query_rendering",
        "authorizes_renderer_execution",
        "authorizes_solver_execution",
        "authorizes_source_identity_derivation",
        "authorizes_source_plan",
        "compiled_history_plan_available",
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
GENERIC_PIN_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "body_framing",
        "canonical_bytes",
        "sha256",
    }
)
FULL_OWNER_PIN_FIELDS = frozenset(
    {
        *GENERIC_PIN_FIELDS,
        "coordinates",
        "owner_id",
        "owner_role",
    }
)
DIRECT_PIN_FIELDS = frozenset(
    {
        "body_framing",
        "canonical_bytes",
        "direct_pin_id",
        "direct_pin_role",
        "sha256",
    }
)
RECEIPT_FIELDS = frozenset(
    {
        "coordinates",
        "direct_body_pins",
        "full_owner_pins",
        "projection_class_id",
        "projection_pin",
        "projector",
        "receipt_id",
        "row_kind",
        "row_schema",
        "validation",
    }
)
MATERIAL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "body",
        "body_framing",
        "coordinates",
        "direct_body_pins",
        "full_owner_pins",
        "projection_class_id",
        "projector_id",
        "receipt_id",
    }
)
GLOBAL_SOURCE_MATERIAL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "body",
        "body_framing",
        "class_id",
        "coordinates",
        "direct_body_pins",
        "full_owner_pins",
        "projector",
    }
)
LEGACY_SOURCE_MATERIAL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "bytes",
        "class_id",
        "coordinates",
        "direct_body_pins",
        "framing",
        "full_owner_pins",
    }
)
SOURCE_MATERIAL_FIELD_SETS = frozenset(
    {GLOBAL_SOURCE_MATERIAL_FIELDS, LEGACY_SOURCE_MATERIAL_FIELDS, MATERIAL_FIELDS}
)
MAX_FULL_OWNER_PINS_PER_MATERIAL = 8
MAX_DIRECT_BODY_PINS_PER_MATERIAL = 12
MAX_COORDINATE_FIELDS = 4
MAX_IDENTITY_STRING_BYTES = 4 * 2**10
EXPECTED_NEW_PROJECTOR_IDS = {
    "topology-path-load": "topology-path-load-content-projector",
    "realism-locale-security": "realism-locale-security-content-projector",
    "route-scores": "route-scores-content-projector",
    "primary-use-case-corpus-half": (
        "primary-use-case-corpus-half-content-projector"
    ),
    "recipe-content-filename-policy": (
        "recipe-content-filename-policy-content-projector"
    ),
    "fact-graph": "fact-graph-content-projector",
    "concrete-overlay-relations": "concrete-overlay-relations-content-projector",
    "source-instance-parameters": "source-instance-parameters-content-projector",
    "payload-equivalence-rules": "payload-equivalence-rules-content-projector",
}
TOP_LEVEL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "canonical_limits",
        "completion_claims",
        "derivation_receipts",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
        "hypothesis_status",
        "missing_projection_class_ledger",
        "orders",
        "predecessor_inventory_binding",
        "projection_class_registry",
        "remaining_blockers",
        "summary",
    }
)
REGISTRY_FIELDS = frozenset(
    {
        "coverage_status",
        "derivation_receipt_count",
        "inventory_ordinal",
        "projection_class_id",
    }
)
PROJECTOR_FIELDS = frozenset({"projector_id", "projector_version"})
VALIDATION_FIELDS = frozenset(
    {
        "independent_derivation_validation_required",
        "projection_pin_matches_external_body",
        "upstream_owner_validation_result",
        "upstream_projection_validation_result",
    }
)

EXPECTED_CANONICAL_LIMITS = {
    "external_projection_bodies_embedded": False,
    "max_base_or_overlay_jsonl_row_bytes_including_lf": 768,
    "max_cumulative_external_projection_bytes": 256 * 2**20,
    "max_json_projection_bytes": 384 * 2**10,
    "max_jsonl_projection_bytes": 4 * 2**20,
    "max_jsonl_projection_rows": 4_096,
    "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
    "max_parameter_jsonl_row_bytes_including_lf": 256,
    "max_receipt_count": 253,
    "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
    "max_suite_bytes": 2 * 2**20,
    "self_hash_embedded": False,
    "target_json_projection_bytes": 256 * 2**10,
    "target_suite_bytes": 1 * 2**20,
    "unicode_normalization": "NFC",
}
EXPECTED_COMPLETION_CLAIMS = {
    "all_253_receipts_bound": True,
    "corpus_semantic_namespace_issued": False,
    "future_source_id_namespace_eligible": True,
    "local_twelve_class_derivation_complete": True,
    "minimum_projection_inventory_complete": True,
    "query_semantics_absence_proved": True,
    "semantic_payload_projection_bound": True,
}
EXPECTED_REMAINING_BLOCKERS = [
    "corpus-semantic-namespace-not-issued",
    "positive-independent-route-and-profile-review-receipts-not-bound",
    "corpus-input-query-history-closures-and-blocker-resolution-ledger-not-complete",
    "joint-solver-solution-proof-and-final-source-plan-not-built",
    "solution-compiled-history-plan-and-g0-descriptor-not-built",
    "physical-materialization-capacity-kio-history-and-evaluation-not-observed",
]
EXPECTED_ORDERS = {
    "derivation_receipts": (
        "minimum-projection-class-order-then-class-specific-canonical-global-"
        "persona-origin-shard-order"
    ),
    "minimum_projection_classes": list(PROJECTION_CLASS_ORDER),
    "persona": list(envelope.PERSONA_IDS),
}


class PersonaV2SemanticProjectionCompleteInventoryValidationError(ValueError):
    """Raised when complete inventory validation fails closed."""


def _fail(message):
    raise PersonaV2SemanticProjectionCompleteInventoryValidationError(message)


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _bounded_text(value, *, label, allow_empty=False):
    if (
        type(value) is not str
        or (not allow_empty and not value)
        or len(value) > MAX_IDENTITY_STRING_BYTES
    ):
        _fail(f"{label} must be one bounded exact string")
    if len(value.encode("utf-8")) > MAX_IDENTITY_STRING_BYTES:
        _fail(f"{label} must be one bounded exact string")
    return value


def _bounded_int(value, *, label, minimum=0):
    if (
        type(value) is not int
        or type(value) is bool
        or value < minimum
        or abs(value) > artifact_common.MAX_INTEGER_MAGNITUDE
    ):
        _fail(f"{label} must be one bounded exact integer")
    return value


def _preflight_coordinates(class_id, coordinates):
    if type(coordinates) is not dict or len(coordinates) > MAX_COORDINATE_FIELDS:
        _fail("projection coordinates exceed their exact shallow bound")
    for key, value in coordinates.items():
        _bounded_text(key, label="projection coordinate key")
        if type(value) is str:
            _bounded_text(value, label="projection coordinate value")
        else:
            _bounded_int(value, label="projection coordinate value", minimum=1)
    if class_id in {
        "topology-path-load",
        "realism-locale-security",
        "route-scores",
        "payload-equivalence-rules",
    }:
        if coordinates:
            _fail("global projection coordinates must be empty")
    elif class_id in {
        "primary-use-case-corpus-half",
        "recipe-content-filename-policy",
    }:
        if coordinates != {"scope": "suite"}:
            _fail("suite projection coordinates drifted")
    elif class_id == "fact-graph":
        if (
            set(coordinates) != {"persona_id"}
            or coordinates["persona_id"] not in envelope.PERSONA_IDS
        ):
            _fail("fact projection coordinates drifted")
    elif class_id == "concrete-overlay-relations":
        if (
            set(coordinates) != {"origin", "persona_id"}
            or coordinates["persona_id"] not in envelope.PERSONA_IDS
            or coordinates["origin"] not in {"pilot", "full-residual"}
        ):
            _fail("relation projection coordinates drifted")
    elif class_id == "source-instance-parameters":
        if coordinates == {
            "parameter_catalog_id": "global-source-parameter-cells-v1"
        }:
            return
        if (
            set(coordinates)
            != {
                "origin",
                "persona_id",
                "source_shard_id",
                "source_shard_ordinal",
            }
            or coordinates["persona_id"] not in envelope.PERSONA_IDS
            or coordinates["origin"] not in {"pilot", "full-residual"}
            or type(coordinates["source_shard_id"]) is not str
            or type(coordinates["source_shard_ordinal"]) is not int
            or type(coordinates["source_shard_ordinal"]) is bool
        ):
            _fail("source-parameter projection coordinates drifted")
    elif class_id not in partial_validator.COVERED_CLASS_ORDER:
        _fail("projection coordinates use an unknown class")


def _preflight_pin(pin, *, owner):
    fields = FULL_OWNER_PIN_FIELDS if owner else DIRECT_PIN_FIELDS
    if type(pin) is not dict or len(pin) != len(fields) or set(pin) != fields:
        _fail("projection material pin schema drifted")
    framing = pin.get("body_framing")
    size = pin.get("canonical_bytes")
    if (
        framing not in {"canonical-json", "canonical-jsonl-lf"}
        or type(size) is not int
        or type(size) is bool
        or not 0 < size <= MAX_CUMULATIVE_EXTERNAL_BODY_BYTES
        or type(pin.get("sha256")) is not str
        or len(pin["sha256"]) != 64
        or any(character not in "0123456789abcdef" for character in pin["sha256"])
    ):
        _fail("projection material pin scalar boundary drifted")
    identity_fields = (
        ("artifact_kind", "artifact_schema", "owner_id", "owner_role")
        if owner
        else ("direct_pin_id", "direct_pin_role")
    )
    for field in identity_fields:
        _bounded_text(pin.get(field), label=f"projection pin {field}")
    if owner:
        version = pin.get("artifact_schema_version")
        _bounded_int(version, label="full-owner pin schema version", minimum=1)
        owner_coordinates = pin.get("coordinates")
        if type(owner_coordinates) is not dict or len(owner_coordinates) > 4:
            _fail("full-owner pin coordinates exceed their shallow bound")
        for key, value in owner_coordinates.items():
            _bounded_text(key, label="full-owner coordinate key")
            if type(value) is str:
                _bounded_text(value, label="full-owner coordinate value")
            else:
                _bounded_int(value, label="full-owner coordinate value")


def _preflight_inventory_shape(value):
    if (
        type(value) is not dict
        or len(value) != len(TOP_LEVEL_FIELDS)
        or set(value) != TOP_LEVEL_FIELDS
    ):
        _fail("complete inventory top-level schema drifted before canonicalization")
    if value.get("artifact_schema") != SUITE_SCHEMA:
        _fail("complete inventory schema drifted before canonicalization")
    receipts = value.get("derivation_receipts")
    if type(receipts) is not list or len(receipts) != MAX_RECEIPT_COUNT:
        _fail("complete inventory receipt bound drifted before canonicalization")
    bounded_sections = {
        "authority": len(AUTHORITY_FIELDS),
        "canonical_limits": 16,
        "completion_claims": 8,
        "orders": 4,
        "predecessor_inventory_binding": len(GENERIC_PIN_FIELDS),
        "summary": 12,
    }
    for field, maximum in bounded_sections.items():
        section = value.get(field)
        if type(section) is not dict or len(section) > maximum:
            _fail(f"complete inventory {field} exceeds its shallow bound")
    for field in (
        "artifact_kind",
        "artifact_schema",
        "fixture_id",
        "hypothesis_status",
    ):
        _bounded_text(value.get(field), label=f"complete inventory {field}")
    version = value.get("artifact_schema_version")
    if type(version) is not int or type(version) is bool or version != 2:
        _fail("complete inventory artifact version drifted")
    fixture_version = value.get("fixture_schema_version")
    if (
        type(fixture_version) is not int
        or type(fixture_version) is bool
        or fixture_version != envelope.FIXTURE_SCHEMA_VERSION
    ):
        _fail("complete inventory fixture version drifted")
    if value.get("g0_contract_frozen") is not False:
        _fail("complete inventory G0 marker drifted")
    authority = value["authority"]
    if set(authority) != AUTHORITY_FIELDS or any(
        type(item) is not bool for item in authority.values()
    ):
        _fail("complete inventory authority schema drifted")
    for field in ("canonical_limits", "completion_claims"):
        for key, item in value[field].items():
            _bounded_text(key, label=f"complete inventory {field} key")
            if type(item) not in {bool, int, str}:
                _fail(f"complete inventory {field} value type drifted")
            if type(item) is str:
                _bounded_text(item, label=f"complete inventory {field} value")
            elif type(item) is int and type(item) is not bool:
                _bounded_int(item, label=f"complete inventory {field} value")
    orders = value["orders"]
    if len(orders) != 3 or set(orders) != {
        "derivation_receipts",
        "minimum_projection_classes",
        "persona",
    }:
        _fail("complete inventory order schema drifted")
    _bounded_text(orders["derivation_receipts"], label="receipt order contract")
    if (
        type(orders["minimum_projection_classes"]) is not list
        or len(orders["minimum_projection_classes"]) != len(PROJECTION_CLASS_ORDER)
        or any(type(item) is not str for item in orders["minimum_projection_classes"])
        or type(orders["persona"]) is not list
        or len(orders["persona"]) != len(envelope.PERSONA_IDS)
        or any(type(item) is not str for item in orders["persona"])
    ):
        _fail("complete inventory order values exceed their exact bounds")
    for item in orders["minimum_projection_classes"]:
        _bounded_text(item, label="minimum projection class order item")
    for item in orders["persona"]:
        _bounded_text(item, label="persona order item")
    predecessor = value["predecessor_inventory_binding"]
    if (
        len(predecessor) != len(GENERIC_PIN_FIELDS)
        or set(predecessor) != GENERIC_PIN_FIELDS
    ):
        _fail("complete inventory predecessor schema drifted")
    for field in ("artifact_kind", "artifact_schema", "body_framing", "sha256"):
        _bounded_text(predecessor.get(field), label=f"predecessor pin {field}")
    _bounded_int(
        predecessor.get("artifact_schema_version"),
        label="predecessor pin artifact version",
        minimum=1,
    )
    _bounded_int(
        predecessor.get("canonical_bytes"),
        label="predecessor pin byte count",
        minimum=1,
    )
    for field, maximum in (
        ("missing_projection_class_ledger", 0),
        ("projection_class_registry", len(PROJECTION_CLASS_ORDER)),
        ("remaining_blockers", 8),
    ):
        section = value.get(field)
        if type(section) is not list or len(section) > maximum:
            _fail(f"complete inventory {field} exceeds its shallow bound")
    registry = value.get("projection_class_registry")
    if any(
        type(row) is not dict
        or len(row) != len(REGISTRY_FIELDS)
        or set(row) != REGISTRY_FIELDS
        or any(type(item) not in {str, int} for item in row.values())
        for row in registry
    ):
        _fail("complete inventory registry row schema drifted")
    for row in registry:
        for field, item in row.items():
            if type(item) is str:
                _bounded_text(item, label=f"registry {field}")
            else:
                _bounded_int(item, label=f"registry {field}")
    blockers = value.get("remaining_blockers")
    if any(type(item) is not str for item in blockers):
        _fail("complete inventory blocker type drifted")
    for item in blockers:
        _bounded_text(item, label="complete inventory blocker")
    summary = value["summary"]
    for key, item in summary.items():
        _bounded_text(key, label="complete inventory summary key")
        if key == "receipt_counts_by_projection_class":
            if (
                type(item) is not dict
                or len(item) != len(PROJECTION_CLASS_ORDER)
                or any(type(count) is not int or type(count) is bool for count in item.values())
            ):
                _fail("complete inventory summary count map drifted")
            for class_id, count in item.items():
                _bounded_text(class_id, label="summary projection class key")
                _bounded_int(count, label="summary projection class count")
        elif type(item) is not int or type(item) is bool:
            _fail("complete inventory summary scalar type drifted")
        else:
            _bounded_int(item, label=f"complete inventory summary {key}")
    for receipt in receipts:
        if (
            type(receipt) is not dict
            or len(receipt) != len(RECEIPT_FIELDS)
            or set(receipt) != RECEIPT_FIELDS
        ):
            _fail("complete receipt schema drifted before canonicalization")
        class_id = receipt.get("projection_class_id")
        if type(class_id) is not str or class_id not in PROJECTION_CLASS_ORDER:
            _fail("complete receipt class drifted before canonicalization")
        for field in ("receipt_id", "row_kind", "row_schema"):
            _bounded_text(receipt.get(field), label=f"complete receipt {field}")
        projector = receipt.get("projector")
        if (
            type(projector) is not dict
            or len(projector) != len(PROJECTOR_FIELDS)
            or set(projector) != PROJECTOR_FIELDS
            or type(projector.get("projector_version")) is not int
            or type(projector.get("projector_version")) is bool
            or projector["projector_version"] != 1
        ):
            _fail("complete receipt projector schema drifted")
        _bounded_text(projector.get("projector_id"), label="complete receipt projector ID")
        validation = receipt.get("validation")
        if (
            type(validation) is not dict
            or len(validation) != len(VALIDATION_FIELDS)
            or set(validation) != VALIDATION_FIELDS
            or any(type(item) is not bool for item in validation.values())
        ):
            _fail("complete receipt validation schema drifted")
        coordinates = receipt.get("coordinates")
        if type(coordinates) is not dict or len(coordinates) > MAX_COORDINATE_FIELDS:
            _fail("complete receipt coordinates exceed their shallow bound")
        for key, item in coordinates.items():
            _bounded_text(key, label="complete receipt coordinate key")
            if type(item) is str:
                _bounded_text(item, label="complete receipt coordinate value")
            else:
                _bounded_int(item, label="complete receipt coordinate value")
        owners = receipt.get("full_owner_pins")
        direct = receipt.get("direct_body_pins")
        if (
            type(owners) is not list
            or not 1 <= len(owners) <= MAX_FULL_OWNER_PINS_PER_MATERIAL
            or type(direct) is not list
            or not 1 <= len(direct) <= MAX_DIRECT_BODY_PINS_PER_MATERIAL
        ):
            _fail("complete receipt pin cardinality exceeds its shallow bound")
        for pin in owners:
            _preflight_pin(pin, owner=True)
        for pin in direct:
            _preflight_pin(pin, owner=False)
        projection_pin = receipt.get("projection_pin")
        if (
            type(projection_pin) is not dict
            or len(projection_pin) != len(GENERIC_PIN_FIELDS)
            or set(projection_pin) != GENERIC_PIN_FIELDS
        ):
            _fail("complete receipt projection pin schema drifted")
        framing = projection_pin.get("body_framing")
        maximum = (
            MAX_JSONL_BODY_BYTES
            if framing == "canonical-jsonl-lf"
            else MAX_JSON_BODY_BYTES
        )
        size = projection_pin.get("canonical_bytes")
        if type(size) is not int or type(size) is bool or not 0 < size <= maximum:
            _fail("complete receipt projection pin exceeds its body cap")
        for field in ("artifact_kind", "artifact_schema", "body_framing", "sha256"):
            _bounded_text(
                projection_pin.get(field),
                label=f"complete receipt projection pin {field}",
            )
        pin_version = projection_pin.get("artifact_schema_version")
        _bounded_int(
            pin_version,
            label="complete receipt projection pin version",
            minimum=1,
        )


def _canonical(value, *, label="complete semantic projection inventory", maximum=MAX_SUITE_BYTES):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label=label,
            max_bytes=maximum,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _reject_duplicate_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_json_constant(_value):
    _fail("JSON non-finite constants are forbidden")


def _reject_json_float(_value):
    _fail("JSON floating-point numbers are forbidden")


def _strict_json_loads(raw, *, label):
    if type(raw) is not bytes:
        _fail(f"{label} must be exact built-in bytes")
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
            parse_float=_reject_json_float,
        )
    except PersonaV2SemanticProjectionCompleteInventoryValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        _fail(f"{label} is not strict UTF-8 JSON: {error}")
    try:
        artifact_common.validate_plain_value(value, label=label)
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))
    return value


def _opening_snapshot(value):
    _preflight_inventory_shape(value)
    opening_raw = _canonical(value)
    snapshot = _strict_json_loads(opening_raw, label="complete inventory opening image")
    if type(snapshot) is not dict:
        _fail("complete semantic projection inventory must be an object")
    if not hmac.compare_digest(opening_raw, _canonical(snapshot)):
        _fail("complete inventory opening image is not canonical")
    return snapshot, opening_raw


def _reauth_target(value, opening_raw):
    _preflight_inventory_shape(value)
    if not hmac.compare_digest(opening_raw, _canonical(value)):
        _fail("caller-owned complete inventory mutated during validation")


def _strict_equal(left, right):
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return set(left) == set(right) and all(
            _strict_equal(left[key], right[key]) for key in left
        )
    if type(left) is list:
        return len(left) == len(right) and all(
            _strict_equal(a, b) for a, b in zip(left, right, strict=True)
        )
    return left == right


def _negative_authority():
    return {field: False for field in sorted(AUTHORITY_FIELDS)}


def _projection_class_registry():
    return [
        {
            "coverage_status": "covered-complete-local-derivation",
            "derivation_receipt_count": EXPECTED_RECEIPT_COUNTS[class_id],
            "inventory_ordinal": ordinal,
            "projection_class_id": class_id,
        }
        for ordinal, class_id in enumerate(PROJECTION_CLASS_ORDER, start=1)
    ]


def _material_iterator(
    module,
    names,
    *,
    expected_count,
    allowed_classes,
    cumulative_state=None,
):
    for name in names:
        function = getattr(module, name, None)
        if callable(function):
            try:
                iterator = iter(function())
            except Exception as error:
                raise PersonaV2SemanticProjectionCompleteInventoryValidationError(
                    "independent projection material iterator failed to open"
                ) from error
            materials = []
            for index in range(expected_count + 1):
                try:
                    value = next(iterator)
                except StopIteration:
                    break
                except Exception as error:
                    raise PersonaV2SemanticProjectionCompleteInventoryValidationError(
                        "independent projection material iterator failed during bounded read"
                    ) from error
                if index == expected_count:
                    _fail("independent projection material iterator exceeded its exact count")
                material = _normalize_material(value)
                if material["projection_class_id"] not in allowed_classes:
                    _fail("independent projection material iterator emitted a foreign class")
                if cumulative_state is not None:
                    cumulative_state[0] += len(material["body"])
                    if cumulative_state[0] > MAX_CUMULATIVE_EXTERNAL_BODY_BYTES:
                        _fail("independent material iterator exceeded its running byte cap")
                materials.append(material)
            if len(materials) != expected_count:
                _fail("independent projection material iterator ended before its exact count")
            return materials
    _fail(f"independent projection material iterator unavailable: {names[0]}")


def _expected_new_receipt_id(class_id, coordinates):
    if class_id == "payload-equivalence-rules":
        return "payload-equivalence-rules-global"
    fixed = {
        "topology-path-load": "projection-derivation-topology-path-load",
        "realism-locale-security": "projection-derivation-realism-locale-security",
        "route-scores": "projection-derivation-route-scores",
        "primary-use-case-corpus-half": (
            "projection-derivation-primary-use-case-corpus-half"
        ),
        "recipe-content-filename-policy": (
            "projection-derivation-recipe-content-filename-policy"
        ),
    }
    if class_id in fixed:
        return fixed[class_id]
    if class_id == "fact-graph":
        return f"projection-derivation-fact-graph-{coordinates['persona_id']}"
    if class_id == "concrete-overlay-relations":
        return (
            "projection-derivation-concrete-overlay-relations-"
            f"{coordinates['persona_id']}-{coordinates['origin']}"
        )
    if class_id == "source-instance-parameters":
        if set(coordinates) == {"parameter_catalog_id"}:
            return "projection-derivation-source-instance-parameters-cell-catalog"
        return (
            "projection-derivation-source-instance-parameters-"
            f"{coordinates['persona_id']}-{coordinates['origin']}-"
            f"{coordinates['source_shard_ordinal']:03d}"
        )
    _fail(f"cannot derive independent receipt ID for {class_id} coordinates")


def _normalize_material(value):
    if type(value) is not dict or len(value) not in {9, 10, 11}:
        _fail("independent projection material must use one exact source schema")
    source_fields = frozenset(value)
    if source_fields not in SOURCE_MATERIAL_FIELD_SETS:
        _fail("independent projection material must use one exact source schema")
    body = value.get("body", value.get("bytes"))
    framing = value.get("body_framing", value.get("framing"))
    class_id = value.get("projection_class_id", value.get("class_id"))
    coordinates = value.get("coordinates")
    if type(class_id) is not str or class_id not in EXPECTED_NEW_PROJECTOR_IDS:
        _fail("independent projection material class identity drifted")
    _preflight_coordinates(class_id, coordinates)
    body_cap = (
        MAX_JSONL_BODY_BYTES
        if framing == "canonical-jsonl-lf"
        else MAX_JSON_BODY_BYTES
    )
    if (
        framing not in {"canonical-json", "canonical-jsonl-lf"}
        or type(body) is not bytes
        or not body
        or len(body) > body_cap
    ):
        _fail("independent projection material body exceeds its pre-hash class cap")
    artifact_kind = value.get("artifact_kind")
    artifact_schema = value.get("artifact_schema")
    artifact_version = value.get("artifact_schema_version")
    _bounded_text(artifact_kind, label="independent material artifact kind")
    _bounded_text(artifact_schema, label="independent material artifact schema")
    _bounded_int(
        artifact_version,
        label="independent material artifact version",
        minimum=1,
    )
    full_owner_pins = value.get("full_owner_pins")
    direct_body_pins = value.get("direct_body_pins")
    if (
        type(full_owner_pins) is not list
        or not 1 <= len(full_owner_pins) <= MAX_FULL_OWNER_PINS_PER_MATERIAL
        or type(direct_body_pins) is not list
        or not 1 <= len(direct_body_pins) <= MAX_DIRECT_BODY_PINS_PER_MATERIAL
    ):
        _fail("independent material pin cardinality exceeds its pre-copy bound")
    for pin in full_owner_pins:
        _preflight_pin(pin, owner=True)
    for pin in direct_body_pins:
        _preflight_pin(pin, owner=False)
    expected_projector_id = EXPECTED_NEW_PROJECTOR_IDS[class_id]
    expected_receipt_id = _expected_new_receipt_id(class_id, coordinates)
    if source_fields == GLOBAL_SOURCE_MATERIAL_FIELDS:
        projector = value.get("projector")
        if type(projector) is not dict or len(projector) != 2 or set(projector) != {
            "projector_id",
            "projector_version",
        }:
            _fail("independent projection material projector schema drifted")
        projector_id = projector.get("projector_id")
        projector_version = projector.get("projector_version")
        if (
            type(projector_version) is not int
            or type(projector_version) is bool
            or projector_version != 1
        ):
            _fail("independent projection material projector version drifted")
        receipt_id = expected_receipt_id
    elif source_fields == LEGACY_SOURCE_MATERIAL_FIELDS:
        projector_id = expected_projector_id
        receipt_id = expected_receipt_id
    else:
        projector_id = value.get("projector_id")
        receipt_id = value.get("receipt_id")
        _bounded_text(projector_id, label="explicit independent projector ID")
        _bounded_text(receipt_id, label="explicit independent receipt ID")
    if projector_id != expected_projector_id:
        _fail("independent projection material projector identity drifted")
    if receipt_id != expected_receipt_id:
        _fail("independent projection material receipt identity drifted")
    normalized = {
        "artifact_kind": artifact_kind,
        "artifact_schema": artifact_schema,
        "artifact_schema_version": artifact_version,
        "body": body,
        "body_framing": framing,
        "coordinates": copy.deepcopy(coordinates),
        "direct_body_pins": copy.deepcopy(direct_body_pins),
        "full_owner_pins": copy.deepcopy(full_owner_pins),
        "projection_class_id": class_id,
        "projector_id": projector_id,
        "receipt_id": receipt_id,
    }
    if set(normalized) != MATERIAL_FIELDS:
        _fail("normalized independent projection material schema drifted")
    return normalized


def _expected_new_materials():
    group_specs = (
        (
            global_validator,
            (
                "iter_expected_global_content_projection_materials",
                "build_expected_global_content_projection_materials",
            ),
            3,
            {
                "topology-path-load",
                "realism-locale-security",
                "route-scores",
            },
        ),
        (
            corpus_validator,
            (
                "iter_expected_corpus_content_projection_materials",
                "build_expected_corpus_content_projection_materials",
            ),
            22,
            {
                "primary-use-case-corpus-half",
                "recipe-content-filename-policy",
                "fact-graph",
            },
        ),
        (
            relations_validator,
            (
                "iter_expected_relations_parameter_projection_materials",
                "build_expected_relations_parameter_projection_materials",
            ),
            114,
            {
                "concrete-overlay-relations",
                "source-instance-parameters",
            },
        ),
        (
            payload_validator,
            (
                "iter_expected_payload_equivalence_projection_materials",
                "build_expected_payload_equivalence_projection_materials",
            ),
            1,
            {"payload-equivalence-rules"},
        ),
    )
    result = []
    cumulative_state = [partial_validator.EXPECTED_CUMULATIVE_EXTERNAL_BODY_BYTES]
    for module, names, expected_count, allowed_classes in group_specs:
        result.extend(
            _material_iterator(
                module,
                names,
                expected_count=expected_count,
                allowed_classes=allowed_classes,
                cumulative_state=cumulative_state,
            )
        )
    if len(result) != 140:
        _fail("independent new projection material total drifted")
    return result


def _projection_pin(material):
    body = material["body"]
    return {
        "artifact_kind": material["artifact_kind"],
        "artifact_schema": material["artifact_schema"],
        "artifact_schema_version": material["artifact_schema_version"],
        "body_framing": material["body_framing"],
        "canonical_bytes": len(body),
        "sha256": _sha256(body),
    }


def _receipt_from_material(material):
    if (
        type(material) is not dict
        or len(material) != len(MATERIAL_FIELDS)
        or set(material) != MATERIAL_FIELDS
    ):
        _fail("independent projection material schema drifted")
    body_cap = (
        MAX_JSONL_BODY_BYTES
        if material.get("body_framing") == "canonical-jsonl-lf"
        else MAX_JSON_BODY_BYTES
    )
    if (
        type(material["body"]) is not bytes
        or not material["body"]
        or len(material["body"]) > body_cap
    ):
        _fail("independent projection material body must be non-empty bytes")
    if (
        type(material["full_owner_pins"]) is not list
        or not material["full_owner_pins"]
        or len(material["full_owner_pins"]) > MAX_FULL_OWNER_PINS_PER_MATERIAL
        or type(material["direct_body_pins"]) is not list
        or not material["direct_body_pins"]
        or len(material["direct_body_pins"]) > MAX_DIRECT_BODY_PINS_PER_MATERIAL
        or any(
            type(row) is not dict or set(row) != FULL_OWNER_PIN_FIELDS
            for row in material["full_owner_pins"]
        )
        or any(
            type(row) is not dict or set(row) != DIRECT_PIN_FIELDS
            for row in material["direct_body_pins"]
        )
    ):
        _fail("independent projection material owner chain drifted")
    return {
        "coordinates": copy.deepcopy(material["coordinates"]),
        "direct_body_pins": copy.deepcopy(material["direct_body_pins"]),
        "full_owner_pins": copy.deepcopy(material["full_owner_pins"]),
        "projection_class_id": material["projection_class_id"],
        "projection_pin": _projection_pin(material),
        "projector": {
            "projector_id": material["projector_id"],
            "projector_version": 1,
        },
        "receipt_id": material["receipt_id"],
        "row_kind": "semantic-projection-derivation-receipt",
        "row_schema": RECEIPT_SCHEMA,
        "validation": {
            "independent_derivation_validation_required": True,
            "projection_pin_matches_external_body": True,
            "upstream_owner_validation_result": True,
            "upstream_projection_validation_result": True,
        },
    }


def _partial_expected_inventory():
    function = getattr(partial_validator, "_expected_inventory", None)
    if not callable(function):
        _fail("frozen partial independent reconstruction is unavailable")
    value = function()
    raw = partial_validator._canonical(
        value,
        label="frozen partial independent inventory",
        maximum=partial_validator.MAX_SUITE_BYTES,
    )
    if (
        len(raw) != partial_validator.EXPECTED_SUITE_CANONICAL_BYTES
        or _sha256(raw) != partial_validator.EXPECTED_SUITE_SHA256
    ):
        _fail("frozen partial independent inventory pin drifted")
    return value, raw


def _converted_partial_receipts(value):
    result = []
    for receipt in value["derivation_receipts"]:
        row = copy.deepcopy(receipt)
        row["row_schema"] = RECEIPT_SCHEMA
        result.append(row)
    return result


def _expected_receipts(partial_value):
    by_class = {class_id: [] for class_id in PROJECTION_CLASS_ORDER}
    for receipt in _converted_partial_receipts(partial_value):
        by_class[receipt["projection_class_id"]].append(receipt)
    for material in _expected_new_materials():
        receipt = _receipt_from_material(material)
        by_class[receipt["projection_class_id"]].append(receipt)
    counts = {class_id: len(by_class[class_id]) for class_id in PROJECTION_CLASS_ORDER}
    if counts != EXPECTED_RECEIPT_COUNTS:
        _fail("independent complete projection receipt counts drifted")
    return [
        receipt
        for class_id in PROJECTION_CLASS_ORDER
        for receipt in by_class[class_id]
    ]


def _predecessor_binding(partial_value, partial_raw):
    return {
        "artifact_kind": partial_value["artifact_kind"],
        "artifact_schema": partial_value["artifact_schema"],
        "artifact_schema_version": partial_value["artifact_schema_version"],
        "body_framing": "canonical-json",
        "canonical_bytes": len(partial_raw),
        "sha256": _sha256(partial_raw),
    }


def _build_expected_inventory():
    partial_value, partial_raw = _partial_expected_inventory()
    receipts = _expected_receipts(partial_value)
    if (
        len(receipts) != MAX_RECEIPT_COUNT
        or len({row["receipt_id"] for row in receipts}) != len(receipts)
        or any(set(row) != RECEIPT_FIELDS for row in receipts)
    ):
        _fail("independent complete receipt identity/schema drifted")
    identities = {
        (row["projection_pin"]["sha256"], row["projection_pin"]["canonical_bytes"])
        for row in receipts
    }
    if len(identities) != len(receipts):
        _fail("independent complete projection body identities are not unique")
    cumulative = sum(row["projection_pin"]["canonical_bytes"] for row in receipts)
    if cumulative > MAX_CUMULATIVE_EXTERNAL_BODY_BYTES:
        _fail("independent complete projection total exceeds its cap")
    if cumulative != EXPECTED_CUMULATIVE_EXTERNAL_BODY_BYTES_FROZEN:
        _fail("independent complete projection total drifted")
    ordered = [
        {
            "canonical_bytes": row["projection_pin"]["canonical_bytes"],
            "receipt_id": row["receipt_id"],
            "sha256": row["projection_pin"]["sha256"],
        }
        for row in receipts
    ]
    digest = _sha256(
        _canonical(ordered, label="independent complete ordered pin rows")
    )
    if digest != EXPECTED_ORDERED_PROJECTION_PINS_SHA256:
        _fail("independent complete ordered pin digest drifted")
    counts = {
        class_id: sum(row["projection_class_id"] == class_id for row in receipts)
        for class_id in PROJECTION_CLASS_ORDER
    }
    value = {
        "artifact_kind": SUITE_KIND,
        "artifact_schema": SUITE_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": _negative_authority(),
        "canonical_limits": copy.deepcopy(EXPECTED_CANONICAL_LIMITS),
        "completion_claims": copy.deepcopy(EXPECTED_COMPLETION_CLAIMS),
        "derivation_receipts": receipts,
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "hypothesis_status": (
            "authored-benchmark-complete-content-projection-derivation-"
            "evidence-not-observed-user-data"
        ),
        "missing_projection_class_ledger": [],
        "orders": copy.deepcopy(EXPECTED_ORDERS),
        "predecessor_inventory_binding": _predecessor_binding(
            partial_value, partial_raw
        ),
        "projection_class_registry": _projection_class_registry(),
        "remaining_blockers": list(EXPECTED_REMAINING_BLOCKERS),
        "summary": {
            "covered_projection_class_count": 12,
            "cumulative_external_projection_bytes": cumulative,
            "derivation_receipt_count": 253,
            "external_projection_body_count": 253,
            "json_projection_body_count": 67,
            "jsonl_projection_body_count": 186,
            "minimum_projection_class_count": 12,
            "missing_projection_class_count": 0,
            "persona_count": 20,
            "receipt_counts_by_projection_class": counts,
        },
    }
    _prevalidate_inventory(value)
    raw = _canonical(value)
    if len(raw) != EXPECTED_SUITE_CANONICAL_BYTES:
        _fail("independently reconstructed complete inventory bytes drifted")
    if _sha256(raw) != EXPECTED_SUITE_SHA256:
        _fail("independently reconstructed complete inventory SHA drifted")
    return value


@functools.lru_cache(maxsize=1)
def _expected_inventory_raw():
    return _canonical(_build_expected_inventory())


def _expected_inventory():
    value = _strict_json_loads(
        _expected_inventory_raw(), label="expected complete inventory"
    )
    if type(value) is not dict:
        _fail("expected complete inventory is not an object")
    return value


def _prevalidate_receipts(receipts):
    if type(receipts) is not list or len(receipts) != MAX_RECEIPT_COUNT:
        _fail("complete receipt list must contain exactly 253 rows")
    counts = {class_id: 0 for class_id in PROJECTION_CLASS_ORDER}
    seen_ids = set()
    seen_projection_identities = set()
    cumulative = 0
    expected_class_sequence = [
        class_id
        for class_id in PROJECTION_CLASS_ORDER
        for _ in range(EXPECTED_RECEIPT_COUNTS[class_id])
    ]
    if [row.get("projection_class_id") for row in receipts if type(row) is dict] != expected_class_sequence:
        _fail("complete receipt class order drifted")
    for index, receipt in enumerate(receipts):
        if type(receipt) is not dict or set(receipt) != RECEIPT_FIELDS:
            _fail(f"complete receipt {index} schema drifted")
        if (
            receipt["row_kind"] != "semantic-projection-derivation-receipt"
            or receipt["row_schema"] != RECEIPT_SCHEMA
            or type(receipt["coordinates"]) is not dict
            or type(receipt["receipt_id"]) is not str
            or not receipt["receipt_id"]
            or receipt["receipt_id"] in seen_ids
            or receipt["projection_class_id"] not in EXPECTED_RECEIPT_COUNTS
        ):
            _fail(f"complete receipt {index} identity drifted")
        seen_ids.add(receipt["receipt_id"])
        class_id = receipt["projection_class_id"]
        counts[class_id] += 1
        if class_id in EXPECTED_NEW_PROJECTOR_IDS:
            _preflight_coordinates(class_id, receipt["coordinates"])
            if (
                receipt["receipt_id"]
                != _expected_new_receipt_id(class_id, receipt["coordinates"])
                or receipt.get("projector")
                != {
                    "projector_id": EXPECTED_NEW_PROJECTOR_IDS[class_id],
                    "projector_version": 1,
                }
            ):
                _fail(f"complete receipt {index} projector/receipt identity drifted")
        pin = receipt["projection_pin"]
        if (
            type(pin) is not dict
            or set(pin) != GENERIC_PIN_FIELDS
            or pin["body_framing"] not in {"canonical-json", "canonical-jsonl-lf"}
            or type(pin["canonical_bytes"]) is not int
            or type(pin["canonical_bytes"]) is bool
            or pin["canonical_bytes"] <= 0
            or pin["canonical_bytes"] > (
                MAX_JSONL_BODY_BYTES
                if pin["body_framing"] == "canonical-jsonl-lf"
                else MAX_JSON_BODY_BYTES
            )
            or type(pin["sha256"]) is not str
            or len(pin["sha256"]) != 64
        ):
            _fail(f"complete receipt {index} projection pin drifted")
        identity = (pin["sha256"], pin["canonical_bytes"])
        if identity in seen_projection_identities:
            _fail("complete projection body pin alias detected")
        seen_projection_identities.add(identity)
        cumulative += pin["canonical_bytes"]
        if (
            type(receipt["full_owner_pins"]) is not list
            or not receipt["full_owner_pins"]
            or any(
                type(row) is not dict or set(row) != FULL_OWNER_PIN_FIELDS
                for row in receipt["full_owner_pins"]
            )
            or type(receipt["direct_body_pins"]) is not list
            or not receipt["direct_body_pins"]
            or any(
                type(row) is not dict or set(row) != DIRECT_PIN_FIELDS
                for row in receipt["direct_body_pins"]
            )
            or type(receipt["projector"]) is not dict
            or set(receipt["projector"]) != PROJECTOR_FIELDS
            or receipt["projector"]["projector_version"] != 1
            or type(receipt["validation"]) is not dict
            or set(receipt["validation"]) != VALIDATION_FIELDS
            or any(value is not True for value in receipt["validation"].values())
        ):
            _fail(f"complete receipt {index} owner/projector validation drifted")
    if counts != EXPECTED_RECEIPT_COUNTS:
        _fail("complete receipt class counts drifted")
    if cumulative > MAX_CUMULATIVE_EXTERNAL_BODY_BYTES:
        _fail("complete receipt projection pins exceed cumulative cap")
    return cumulative


def _prevalidate_inventory(value):
    if type(value) is not dict or set(value) != TOP_LEVEL_FIELDS:
        _fail("complete inventory top-level schema drifted")
    if (
        value.get("artifact_kind") != SUITE_KIND
        or value.get("artifact_schema") != SUITE_SCHEMA
        or value.get("artifact_schema_version") != 2
        or value.get("fixture_id") != envelope.FIXTURE_ID
        or value.get("fixture_schema_version") != envelope.FIXTURE_SCHEMA_VERSION
        or value.get("g0_contract_frozen") is not False
        or value.get("hypothesis_status")
        != "authored-benchmark-complete-content-projection-derivation-evidence-not-observed-user-data"
    ):
        _fail("complete inventory envelope/status drifted")
    authority = value.get("authority")
    if (
        type(authority) is not dict
        or set(authority) != AUTHORITY_FIELDS
        or any(type(item) is not bool or item is not False for item in authority.values())
    ):
        _fail("complete inventory authority must be exact all-false")
    exact_sections = (
        ("canonical_limits", EXPECTED_CANONICAL_LIMITS),
        ("completion_claims", EXPECTED_COMPLETION_CLAIMS),
        ("missing_projection_class_ledger", []),
        ("orders", EXPECTED_ORDERS),
        ("projection_class_registry", _projection_class_registry()),
        ("remaining_blockers", EXPECTED_REMAINING_BLOCKERS),
    )
    for field, expected in exact_sections:
        if not _strict_equal(value.get(field), expected):
            _fail(f"complete inventory {field} drifted")
    predecessor = value.get("predecessor_inventory_binding")
    if type(predecessor) is not dict or set(predecessor) != GENERIC_PIN_FIELDS:
        _fail("complete inventory predecessor binding schema drifted")
    if (
        predecessor["artifact_schema"]
        != "kio.persona.pc-semantic-projection-derivation-inventory/v1"
        or predecessor["canonical_bytes"]
        != partial_validator.EXPECTED_SUITE_CANONICAL_BYTES
        or predecessor["sha256"] != partial_validator.EXPECTED_SUITE_SHA256
    ):
        _fail("complete inventory predecessor binding drifted")
    cumulative = _prevalidate_receipts(value.get("derivation_receipts"))
    expected_summary = {
        "covered_projection_class_count": 12,
        "cumulative_external_projection_bytes": cumulative,
        "derivation_receipt_count": 253,
        "external_projection_body_count": 253,
        "json_projection_body_count": 67,
        "jsonl_projection_body_count": 186,
        "minimum_projection_class_count": 12,
        "missing_projection_class_count": 0,
        "persona_count": 20,
        "receipt_counts_by_projection_class": EXPECTED_RECEIPT_COUNTS,
    }
    if not _strict_equal(value.get("summary"), expected_summary):
        _fail("complete inventory summary drifted")
    return cumulative


def _detached_receipt(receipt):
    raw = _canonical(receipt, label="complete provider receipt argument")
    value = _strict_json_loads(raw, label="complete provider receipt argument")
    if type(value) is not dict or not hmac.compare_digest(raw, _canonical(value, label="complete provider receipt argument")):
        _fail("complete provider receipt argument is not canonical object")
    return value


def _call_provider(provider, receipt, *, replay):
    try:
        body = provider(_detached_receipt(receipt))
    except Exception as error:
        raise PersonaV2SemanticProjectionCompleteInventoryValidationError(
            "complete projection body provider failed"
            + (" during replay" if replay else "")
        ) from error
    if type(body) is not bytes:
        _fail("complete projection provider must return exact built-in bytes")
    pin = receipt["projection_pin"]
    hard_cap = (
        MAX_JSONL_BODY_BYTES
        if pin["body_framing"] == "canonical-jsonl-lf"
        else MAX_JSON_BODY_BYTES
    )
    if len(body) > hard_cap:
        _fail("complete projection provider result exceeds class framing cap")
    if (
        len(body) != pin["canonical_bytes"]
        or not hmac.compare_digest(_sha256(body), pin["sha256"])
    ):
        _fail("complete projection provider result differs from receipt pin")
    return body


def _partial_v1_receipt(receipt):
    value = copy.deepcopy(receipt)
    value["row_schema"] = PARTIAL_V1_RECEIPT_SCHEMA
    return value


def _module_for_class(class_id):
    if class_id in {
        "topology-path-load",
        "realism-locale-security",
        "route-scores",
    }:
        return global_validator
    if class_id in {
        "primary-use-case-corpus-half",
        "recipe-content-filename-policy",
        "fact-graph",
    }:
        return corpus_validator
    if class_id in {
        "concrete-overlay-relations",
        "source-instance-parameters",
    }:
        return relations_validator
    if class_id == "payload-equivalence-rules":
        return payload_validator
    return None


def _validate_new_projection_body(module, receipt, body):
    for name in (
        "validate_projection_body",
        "validate_content_projection_body",
    ):
        function = getattr(module, name, None)
        if callable(function):
            result = function(
                receipt["projection_class_id"],
                copy.deepcopy(receipt["coordinates"]),
                body,
            )
            if result is not True:
                _fail("independent content projection validator did not return True")
            return
    _fail("independent content projection validator dispatch is unavailable")


def _validate_and_reauthenticate_receipt(receipt, body):
    class_id = receipt["projection_class_id"]
    if class_id in partial_validator.COVERED_CLASS_ORDER:
        v1 = _partial_v1_receipt(receipt)
        partial_validator._reauthenticate_receipt_owner_chain(v1)
        partial_validator._validate_projection_body(body, v1)
        return
    module = _module_for_class(class_id)
    if module is None:
        _fail("complete projection class has no independent validator")
    _validate_new_projection_body(module, receipt, body)


def _reauthenticate_all_new_owners(module):
    for name in (
        "reauthenticate_all_projection_owners",
        "reauthenticate_all_content_projection_owners",
    ):
        function = getattr(module, name, None)
        if callable(function):
            if function() is not True:
                _fail("content projection all-owner reauthentication failed")
            return
    _fail("content projection all-owner reauthentication is unavailable")


def _reauthenticate_all_owners(receipts):
    partial_receipts = [
        _partial_v1_receipt(row)
        for row in receipts
        if row["projection_class_id"] in partial_validator.COVERED_CLASS_ORDER
    ]
    partial_validator._reauthenticate_all_owner_chains(partial_receipts)
    for module in (
        global_validator,
        corpus_validator,
        relations_validator,
        payload_validator,
    ):
        _reauthenticate_all_new_owners(module)


def _strict_json_body(body, *, label):
    value = _strict_json_loads(body, label=label)
    if not hmac.compare_digest(
        body,
        _canonical(value, label=label, maximum=MAX_JSON_BODY_BYTES),
    ):
        _fail(f"{label} is not canonical JSON")
    return value


def _strict_jsonl_rows(body, *, label, row_cap):
    if not body.endswith(b"\n"):
        _fail(f"{label} must end every row with LF")
    framed_rows = body.splitlines(keepends=True)
    if not framed_rows or len(framed_rows) > MAX_JSONL_ROWS:
        _fail(f"{label} row count is outside its cap")
    rows = []
    for index, framed in enumerate(framed_rows):
        if not framed.endswith(b"\n") or len(framed) > row_cap:
            _fail(f"{label} row {index} framing/cap drifted")
        raw = framed[:-1]
        row = _strict_json_loads(raw, label=f"{label} row {index}")
        if not hmac.compare_digest(
            raw,
            _canonical(row, label=f"{label} row {index}", maximum=row_cap - 1),
        ):
            _fail(f"{label} row {index} is not canonical JSON")
        rows.append(row)
    return rows


def _new_audit_state():
    return {
        "assignment_cell_by_intent": {},
        "assignment_cell_keys": set(),
        "assignment_intent_keys": set(),
        "base_by_coordinate": {},
        "base_intent_keys": set(),
        "cell_by_key": {},
        "cell_keys": set(),
        "class_body_counts": {class_id: 0 for class_id in PROJECTION_CLASS_ORDER},
        "class_body_bytes": {class_id: 0 for class_id in PROJECTION_CLASS_ORDER},
        "concrete_attachment_rows": [],
        "concrete_content_rows": [],
        "fact_graphs": 0,
        "fact_personas": set(),
        "payload_rule_body_count": 0,
        "primary_use_case_rows": None,
        "recipe_rows": None,
        "route_rows": None,
        "route_score_cells": None,
        "topology_scope_rows": None,
    }


def _find_list(value, keys):
    if type(value) is not dict:
        return None
    for key in keys:
        rows = value.get(key)
        if type(rows) is list:
            return rows
    return None


def _audit_body(receipt, body, state):
    class_id = receipt["projection_class_id"]
    state["class_body_counts"][class_id] += 1
    state["class_body_bytes"][class_id] += len(body)
    if receipt["projection_pin"]["body_framing"] == "canonical-json":
        value = _strict_json_body(body, label=f"{class_id} projection")
        if class_id == "topology-path-load":
            summary = value.get("summary") if type(value) is dict else None
            state["topology_scope_rows"] = (
                summary.get("scope_count") if type(summary) is dict else None
            )
        elif class_id == "route-scores":
            summary = value.get("summary") if type(value) is dict else None
            state["route_rows"] = (
                summary.get("route_score_row_count")
                if type(summary) is dict
                else None
            )
            state["route_score_cells"] = (
                summary.get("route_score_cell_count")
                if type(summary) is dict
                else None
            )
        elif class_id == "primary-use-case-corpus-half":
            rows = _find_list(
                value,
                ("primary_use_case_rows", "primary_use_cases", "rows"),
            )
            state["primary_use_case_rows"] = None if rows is None else len(rows)
        elif class_id == "recipe-content-filename-policy":
            rows = _find_list(value, ("recipe_profile_rows", "rows"))
            state["recipe_rows"] = None if rows is None else len(rows)
        elif class_id == "fact-graph":
            graphs = _find_list(value, ("graphs",))
            persona_id = value.get("persona_id") if type(value) is dict else None
            if graphs is None or persona_id in state["fact_personas"]:
                _fail("fact projection persona/graphs drifted")
            state["fact_personas"].add(persona_id)
            state["fact_graphs"] += len(graphs)
        elif class_id == "source-instance-parameters":
            cells = _find_list(value, ("parameter_cells", "cells"))
            if cells is None:
                _fail("source-parameter JSON body is not the shared cell catalog")
            for row in cells:
                key = row.get("parameter_cell_key") if type(row) is dict else None
                if type(key) is not str or not key or key in state["cell_keys"]:
                    _fail("source-parameter cell identity drifted")
                state["cell_keys"].add(key)
                state["cell_by_key"][key] = copy.deepcopy(row)
        elif class_id == "payload-equivalence-rules":
            state["payload_rule_body_count"] += 1
        return

    row_cap = (
        MAX_PARAMETER_ROW_BYTES_INCLUDING_LF
        if class_id == "source-instance-parameters"
        else MAX_BASE_OR_OVERLAY_ROW_BYTES_INCLUDING_LF
    )
    rows = _strict_jsonl_rows(body, label=f"{class_id} projection", row_cap=row_cap)
    if class_id == "base-source-content-context":
        for row in rows:
            if type(row) is not dict:
                _fail("base content-context row is not an object")
            key = row.get("intent_key")
            coordinate = (row.get("persona_id"), row.get("origin"), key)
            if (
                type(key) is not str
                or not key
                or coordinate in state["base_by_coordinate"]
            ):
                _fail("base content-context intent coordinate duplicated")
            state["base_by_coordinate"][coordinate] = (
                row.get("payload_equivalence_key"),
                row.get("deterministic_payload_seed"),
                row.get("semantic_version"),
            )
            if key in state["base_intent_keys"]:
                _fail("base intent key is not suite-global unique")
            state["base_intent_keys"].add(key)
    elif class_id == "concrete-overlay-relations":
        for row in rows:
            kind = row.get("row_kind") if type(row) is dict else None
            coordinate_row = {
                **copy.deepcopy(row),
                "origin": receipt["coordinates"].get("origin"),
                "persona_id": receipt["coordinates"].get("persona_id"),
            }
            if kind == "content-relation":
                state["concrete_content_rows"].append(coordinate_row)
            elif kind == "attachment-membership":
                state["concrete_attachment_rows"].append(coordinate_row)
            else:
                _fail("concrete overlay projection contains an unknown row kind")
    elif class_id == "source-instance-parameters":
        for row in rows:
            if type(row) is not dict or set(row) != {
                "intent_key",
                "parameter_cell_key",
            }:
                _fail("source-parameter assignment row schema drifted")
            intent_key = row["intent_key"]
            parameter_cell_key = row["parameter_cell_key"]
            if (
                type(intent_key) is not str
                or not intent_key
                or type(parameter_cell_key) is not str
                or not parameter_cell_key
                or intent_key in state["assignment_intent_keys"]
            ):
                _fail("source-parameter assignment duplicated an intent")
            state["assignment_intent_keys"].add(intent_key)
            state["assignment_cell_keys"].add(parameter_cell_key)
            state["assignment_cell_by_intent"][intent_key] = parameter_cell_key


def _base_identity(state, row, field):
    coordinate = (row["persona_id"], row["origin"], row[field])
    if coordinate not in state["base_by_coordinate"]:
        _fail("concrete relation endpoint is missing its base source row")
    return coordinate, state["base_by_coordinate"][coordinate]


def _assigned_cell(state, intent_key):
    cell_key = state["assignment_cell_by_intent"].get(intent_key)
    cell = state["cell_by_key"].get(cell_key)
    if type(cell_key) is not str or type(cell) is not dict:
        _fail("overlay endpoint is missing its source-parameter cell")
    return cell_key, cell


def _validate_parameter_cell_usage(state):
    cell_keys = state["cell_keys"]
    assignment_cell_keys = state["assignment_cell_keys"]
    if len(cell_keys) != 363:
        _fail("source parameter catalog must contain exactly 363 cells")
    if not assignment_cell_keys.issubset(cell_keys):
        _fail("source parameter assignments reference a foreign cell")
    if len(assignment_cell_keys) != 354:
        _fail("source parameter assignments must use exactly 354 active cells")
    if cell_keys - assignment_cell_keys != EXPECTED_UNUSED_PARAMETER_CELL_KEYS:
        _fail("source parameter active/inactive cell partition drifted")


def _validate_cross_class_closure(state):
    if state["class_body_counts"] != EXPECTED_RECEIPT_COUNTS:
        _fail("audited complete body counts drifted")
    if state["topology_scope_rows"] != 400:
        _fail("topology projection must contain exactly 400 scopes")
    if state["route_rows"] != 541 or state["route_score_cells"] != 10_820:
        _fail("route projection logical totals drifted")
    if state["primary_use_case_rows"] != 20 or state["recipe_rows"] != 71:
        _fail("use-case or recipe projection logical totals drifted")
    if len(state["fact_personas"]) != 20 or state["fact_graphs"] != 80:
        _fail("fact projection persona/graph totals drifted")
    if len(state["base_intent_keys"]) != 203_000:
        _fail("base projection must cover exactly 203,000 source intents")
    _validate_parameter_cell_usage(state)
    if state["assignment_intent_keys"] != state["base_intent_keys"]:
        _fail("source parameter assignments differ from the exact base intent domain")
    if (
        len(state["concrete_content_rows"]) != 19_870
        or len(state["concrete_attachment_rows"]) != 5_690
    ):
        _fail("concrete overlay relation totals drifted")
    if state["payload_rule_body_count"] != 1:
        _fail("payload equivalence rule catalog must appear exactly once")

    overlay_coordinates = set()
    endpoint_roles = {}
    relation_clusters = set()
    relation_counts = {
        "exact-duplicate": 0,
        "near-revision": 0,
        "conflict-copy": 0,
    }
    for row in state["concrete_content_rows"]:
        relation = row.get("relation_kind")
        if relation not in relation_counts:
            _fail("concrete content relation kind drifted")
        anchor_coordinate, (anchor_payload, anchor_seed, anchor_version) = _base_identity(
            state, row, "anchor_intent_key"
        )
        derivative_coordinate, (
            derivative_payload,
            derivative_seed,
            derivative_version,
        ) = (
            _base_identity(state, row, "derivative_intent_key")
        )
        cluster_coordinate = (
            row["persona_id"],
            row["origin"],
            row.get("cluster_key"),
        )
        if (
            anchor_coordinate == derivative_coordinate
            or anchor_seed == derivative_seed
            or cluster_coordinate in relation_clusters
            or anchor_coordinate in endpoint_roles
            or derivative_coordinate in endpoint_roles
        ):
            _fail("concrete relation identity/endpoint ownership drifted")
        relation_clusters.add(cluster_coordinate)
        endpoint_roles[anchor_coordinate] = (relation, "anchor")
        endpoint_roles[derivative_coordinate] = (relation, "derivative")
        anchor_cell_key, anchor_cell = _assigned_cell(
            state, row["anchor_intent_key"]
        )
        derivative_cell_key, derivative_cell = _assigned_cell(
            state, row["derivative_intent_key"]
        )
        if relation == "exact-duplicate" and anchor_payload != derivative_payload:
            _fail("exact duplicate endpoints have different payload equivalence keys")
        if relation == "exact-duplicate" and (
            anchor_cell_key != derivative_cell_key
            or anchor_cell.get("variant_id") == "eml"
            or derivative_cell.get("variant_id") == "eml"
            or (anchor_version, derivative_version) != ("v1", "v1")
        ):
            _fail("exact duplicate endpoints do not share one non-EML parameter cell")
        if relation != "exact-duplicate" and anchor_payload == derivative_payload:
            _fail("near/conflict endpoints share a forbidden payload equivalence key")
        expected_versions = (
            ("v1", "v2") if relation == "near-revision" else ("v1", "v1")
        )
        if (anchor_version, derivative_version) != expected_versions:
            _fail("content relation semantic-version pairing drifted")
        relation_counts[relation] += 1
        overlay_coordinates.add(anchor_coordinate)
        overlay_coordinates.add(derivative_coordinate)
    if relation_counts != {
        "exact-duplicate": 5_080,
        "near-revision": 13_230,
        "conflict-copy": 1_560,
    }:
        _fail("concrete content relation-kind totals drifted")
    attachment_rows_by_host = {}
    attachment_keys = set()
    attachment_members = set()
    attachment_overlap_count = 0
    for row in state["concrete_attachment_rows"]:
        host_coordinate, (host_payload, host_seed, host_version) = _base_identity(
            state, row, "host_intent_key"
        )
        member_coordinate, (member_payload, member_seed, member_version) = (
            _base_identity(state, row, "standalone_member_intent_key")
        )
        attachment_coordinate = (
            row["persona_id"],
            row["origin"],
            row.get("attachment_key"),
        )
        if (
            host_coordinate == member_coordinate
            or host_seed == member_seed
            or host_payload == member_payload
            or attachment_coordinate in attachment_keys
            or member_coordinate in attachment_members
            or host_coordinate in attachment_members
            or member_coordinate in attachment_rows_by_host
            or host_coordinate in endpoint_roles
            or (host_version, member_version) != ("v1", "v1")
        ):
            _fail("attachment identity/endpoint ownership drifted")
        attachment_keys.add(attachment_coordinate)
        attachment_members.add(member_coordinate)
        role = endpoint_roles.get(member_coordinate)
        if role is not None:
            if role != ("exact-duplicate", "derivative") or row.get(
                "member_ordinal"
            ) != 1:
                _fail("attachment overlap is not one exact derivative at ordinal one")
            attachment_overlap_count += 1
        host_cell_key, host_cell = _assigned_cell(state, row["host_intent_key"])
        _member_cell_key, member_cell = _assigned_cell(
            state, row["standalone_member_intent_key"]
        )
        if (
            host_cell.get("variant_id") != "eml"
            or member_cell.get("variant_id") == "eml"
            or not host_cell_key.startswith("eml/")
        ):
            _fail("attachment host/member parameter-cell variants drifted")
        if row.get("decoded_payload_equivalence_key") != member_payload:
            _fail("decoded attachment payload differs from standalone member")
        attachment_rows_by_host.setdefault(host_coordinate, []).append(row)
        overlay_coordinates.add(host_coordinate)
        overlay_coordinates.add(member_coordinate)
    if (
        len(attachment_rows_by_host) != 2_800
        or len(attachment_members) != 5_690
        or attachment_overlap_count != 1_390
    ):
        _fail("attachment host/member/overlap totals drifted")
    for host_coordinate, rows in attachment_rows_by_host.items():
        ordinals = sorted(row.get("member_ordinal") for row in rows)
        if ordinals != list(range(1, len(rows) + 1)) or not 1 <= len(rows) <= 5:
            _fail("attachment member ordinals are not contiguous one through five")
        host_intent_key = host_coordinate[2]
        _host_cell_key, host_cell = _assigned_cell(state, host_intent_key)
        if host_cell.get("bin_id") != f"attachment-{len(rows)}":
            _fail("attachment host parameter cell does not encode its member count")
    if len(overlay_coordinates) != 46_840:
        _fail("unique concrete overlay source coverage drifted")
    if len({value[0] for value in state["base_by_coordinate"].values()}) != 197_920:
        _fail("unique source payload-equivalence-key total drifted")
    for coordinate, (payload_key, deterministic_seed, semantic_version) in state[
        "base_by_coordinate"
    ].items():
        if coordinate not in overlay_coordinates and (
            payload_key != deterministic_seed or semantic_version != "v1"
        ):
            _fail("default source payload key/version differs from its local rule")


def validate_semantic_projection_complete_inventory(
    value,
    projection_body_provider=None,
):
    """Validate exact metadata, all bodies twice, owners, and cross-class joins."""

    snapshot, opening_raw = _opening_snapshot(value)
    owners_opened = False
    try:
        if (
            len(opening_raw) != EXPECTED_SUITE_CANONICAL_BYTES
            or _sha256(opening_raw) != EXPECTED_SUITE_SHA256
        ):
            _fail("complete inventory differs from its frozen opening pin")
        _prevalidate_inventory(snapshot)
        if not callable(projection_body_provider):
            _fail("complete projection body provider must be callable")
        expected = _expected_inventory()
        if not hmac.compare_digest(_canonical(snapshot), _canonical(expected)):
            _fail("complete inventory differs from independent reconstruction")
        _reauthenticate_all_owners(snapshot["derivation_receipts"])
        owners_opened = True
        state = _new_audit_state()
        audited_bytes = 0
        for receipt in snapshot["derivation_receipts"]:
            first = None
            try:
                first = _call_provider(
                    projection_body_provider, receipt, replay=False
                )
            finally:
                _reauth_target(value, opening_raw)
                if first is not None:
                    _validate_and_reauthenticate_receipt(receipt, first)
            _audit_body(receipt, first, state)
            replay = None
            try:
                replay = _call_provider(
                    projection_body_provider, receipt, replay=True
                )
            finally:
                _reauth_target(value, opening_raw)
                if replay is not None:
                    _validate_and_reauthenticate_receipt(receipt, replay)
            if not hmac.compare_digest(first, replay):
                _fail("complete projection body provider replay is nondeterministic")
            audited_bytes += len(first)
        if (
            audited_bytes
            != snapshot["summary"]["cumulative_external_projection_bytes"]
            or audited_bytes > MAX_CUMULATIVE_EXTERNAL_BODY_BYTES
        ):
            _fail("audited complete projection footprint drifted")
        _validate_cross_class_closure(state)
    finally:
        postflight_error = None
        if owners_opened:
            try:
                _reauthenticate_all_owners(snapshot["derivation_receipts"])
            except Exception as error:
                postflight_error = error
        try:
            _reauth_target(value, opening_raw)
        except Exception as error:
            if postflight_error is None:
                postflight_error = error
        if postflight_error is not None:
            raise postflight_error
    return True


__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "AUTHORITY_FIELDS",
    "EXPECTED_CUMULATIVE_EXTERNAL_BODY_BYTES_FROZEN",
    "EXPECTED_ORDERED_PROJECTION_PINS_SHA256",
    "EXPECTED_RECEIPT_COUNTS",
    "EXPECTED_SUITE_CANONICAL_BYTES",
    "EXPECTED_SUITE_SHA256",
    "MAX_CUMULATIVE_EXTERNAL_BODY_BYTES",
    "MAX_RECEIPT_COUNT",
    "MAX_SUITE_BYTES",
    "PROJECTION_CLASS_ORDER",
    "PersonaV2SemanticProjectionCompleteInventoryValidationError",
    "RECEIPT_SCHEMA",
    "SUITE_KIND",
    "SUITE_SCHEMA",
    "validate_semantic_projection_complete_inventory",
]
