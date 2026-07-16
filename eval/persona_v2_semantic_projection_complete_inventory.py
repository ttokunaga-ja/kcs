"""Complete twelve-class semantic-projection derivation inventory.

Decision 150's v1 artifact remains a frozen, independently useful three-class
checkpoint.  This v2 artifact regenerates those exact 113 projection bodies and
adds the remaining 140 content-only projections.  External bodies remain out of
the descriptor; receipts bind their exact full/direct owner chain and body pin.

The module is deliberately non-authorizing.  A complete projection inventory
makes a future semantic namespace eligible, but it does not issue that namespace
or authorize solving, final identifiers, rendering, filesystem writes, history,
KCS execution, capacity claims, observations, or G0.
"""

from __future__ import annotations

import copy
import functools
import hashlib
import hmac
import json

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_payload_equivalence_rule_catalog as payload_rules
    from . import persona_v2_semantic_projection_corpus_content as corpus_content
    from . import persona_v2_semantic_projection_derivation_inventory as partial
    from . import persona_v2_semantic_projection_global_content as global_content
    from . import (
        persona_v2_semantic_projection_relations_parameters as relations_parameters,
    )
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_payload_equivalence_rule_catalog as payload_rules
    import persona_v2_semantic_projection_corpus_content as corpus_content
    import persona_v2_semantic_projection_derivation_inventory as partial
    import persona_v2_semantic_projection_global_content as global_content
    import persona_v2_semantic_projection_relations_parameters as relations_parameters


ARTIFACT_SCHEMA_VERSION = 2
SUITE_SCHEMA = "kcs.persona.pc-semantic-projection-derivation-inventory/v2"
SUITE_KIND = "persona-pc-v2-complete-semantic-projection-derivation-inventory"
RECEIPT_SCHEMA = "kcs.persona.pc-semantic-projection-derivation-receipt/v2"

PROJECTION_CLASS_ORDER = tuple(partial.PROJECTION_CLASS_ORDER)
COVERED_CLASS_ORDER = PROJECTION_CLASS_ORDER
MISSING_CLASS_ORDER = ()

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

MAX_SUITE_BYTES = 2 * 2**20
TARGET_SUITE_BYTES = 1 * 2**20
MAX_RECEIPT_COUNT = 253
MAX_CUMULATIVE_PROJECTION_BYTES = 256 * 2**20
MAX_JSON_PROJECTION_BYTES = 384 * 2**10
TARGET_JSON_PROJECTION_BYTES = 256 * 2**10
MAX_JSONL_PROJECTION_BYTES = 4 * 2**20
MAX_JSONL_ROWS = 4_096
MAX_BASE_OR_OVERLAY_ROW_BYTES_INCLUDING_LF = 768
MAX_PARAMETER_ROW_BYTES_INCLUDING_LF = 256

# Frozen after two isolated all-253 builds under distinct Python hash seeds.
# These pins attest only this authored, content-only derivation inventory; they
# do not issue a semantic namespace or grant any downstream authority.
EXPECTED_SUITE_CANONICAL_BYTES = 697_466
EXPECTED_SUITE_SHA256 = (
    "6826fb14293e7147159fae1849f93533c35ae76f1beecbd093d190cd6ddd3e69"
)
EXPECTED_CUMULATIVE_EXTERNAL_BODY_BYTES = 155_741_469
EXPECTED_ORDERED_PROJECTION_PINS_SHA256 = (
    "f524ddcccdd89a216b87d2ad8f98076c8eacabbc258e7b68d514162764a3a97c"
)

AUTHORITY_FIELDS = frozenset(partial.AUTHORITY_FIELDS)
RECEIPT_FIELDS = frozenset(partial.RECEIPT_FIELDS)
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
NEW_PROJECTOR_IDS = {
    class_id: f"{class_id}-content-projector"
    for class_id in (
        "topology-path-load",
        "realism-locale-security",
        "route-scores",
        "primary-use-case-corpus-half",
        "recipe-content-filename-policy",
        "fact-graph",
        "concrete-overlay-relations",
        "source-instance-parameters",
        "payload-equivalence-rules",
    )
}
REGISTRY_FIELDS = frozenset(
    {
        "coverage_status",
        "derivation_receipt_count",
        "inventory_ordinal",
        "projection_class_id",
    }
)
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


class PersonaV2SemanticProjectionCompleteInventoryError(ValueError):
    """Raised when the complete content-only inventory is invalid."""


def _fail(message):
    raise PersonaV2SemanticProjectionCompleteInventoryError(message)


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
    elif class_id not in partial.COVERED_CLASS_ORDER:
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
        or not 0 < size <= MAX_CUMULATIVE_PROJECTION_BYTES
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
        if type(class_id) is not str or class_id not in COVERED_CLASS_ORDER:
            _fail("complete receipt class drifted before canonicalization")
        for field in ("receipt_id", "row_kind", "row_schema"):
            _bounded_text(receipt.get(field), label=f"complete receipt {field}")
        projector = receipt.get("projector")
        if (
            type(projector) is not dict
            or len(projector) != 2
            or set(projector) != {"projector_id", "projector_version"}
            or type(projector.get("projector_version")) is not int
            or type(projector.get("projector_version")) is bool
            or projector["projector_version"] != 1
        ):
            _fail("complete receipt projector schema drifted")
        _bounded_text(projector.get("projector_id"), label="complete receipt projector ID")
        validation = receipt.get("validation")
        if (
            type(validation) is not dict
            or len(validation) != 4
            or set(validation)
            != {
                "independent_derivation_validation_required",
                "projection_pin_matches_external_body",
                "upstream_owner_validation_result",
                "upstream_projection_validation_result",
            }
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
            MAX_JSONL_PROJECTION_BYTES
            if framing == "canonical-jsonl-lf"
            else MAX_JSON_PROJECTION_BYTES
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


def _canonical_fragment(value, *, label, max_bytes=MAX_SUITE_BYTES):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label=label,
            max_bytes=max_bytes,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def canonical_json_bytes(value):
    """Return bounded canonical bytes for only the v2 descriptor."""

    _preflight_inventory_shape(value)
    return _canonical_fragment(
        value,
        label="persona v2 complete semantic projection derivation inventory",
    )


def _negative_authority():
    return {field: False for field in sorted(AUTHORITY_FIELDS)}


def _generic_pin(
    *,
    artifact_kind,
    artifact_schema,
    artifact_schema_version,
    body_framing,
    canonical_bytes,
    sha256,
):
    return {
        "artifact_kind": artifact_kind,
        "artifact_schema": artifact_schema,
        "artifact_schema_version": artifact_schema_version,
        "body_framing": body_framing,
        "canonical_bytes": canonical_bytes,
        "sha256": sha256,
    }


def _projection_pin(material):
    body = material["body"]
    return _generic_pin(
        artifact_kind=material["artifact_kind"],
        artifact_schema=material["artifact_schema"],
        artifact_schema_version=material["artifact_schema_version"],
        body_framing=material["body_framing"],
        canonical_bytes=len(body),
        sha256=_sha256(body),
    )


def _receipt_from_material(material):
    if (
        type(material) is not dict
        or len(material) != len(MATERIAL_FIELDS)
        or set(material) != MATERIAL_FIELDS
    ):
        _fail("complete projection material has an invalid schema")
    body_cap = (
        MAX_JSONL_PROJECTION_BYTES
        if material.get("body_framing") == "canonical-jsonl-lf"
        else MAX_JSON_PROJECTION_BYTES
    )
    if (
        type(material["body"]) is not bytes
        or not material["body"]
        or len(material["body"]) > body_cap
    ):
        _fail("complete projection material body must be non-empty exact bytes")
    if (
        material["projection_class_id"] not in COVERED_CLASS_ORDER
        or type(material["coordinates"]) is not dict
        or type(material["receipt_id"]) is not str
        or not material["receipt_id"]
        or type(material["projector_id"]) is not str
        or not material["projector_id"]
        or material["body_framing"] not in {"canonical-json", "canonical-jsonl-lf"}
    ):
        _fail("complete projection material identity is invalid")
    class_id = material["projection_class_id"]
    if class_id in NEW_PROJECTOR_IDS:
        _preflight_coordinates(class_id, material["coordinates"])
        if (
            material["projector_id"] != NEW_PROJECTOR_IDS[class_id]
            or material["receipt_id"]
            != _expected_new_receipt_id(class_id, material["coordinates"])
        ):
            _fail("complete projection material projector/receipt identity drifted")
    full_owner_pins = material["full_owner_pins"]
    direct_body_pins = material["direct_body_pins"]
    if (
        type(full_owner_pins) is not list
        or not full_owner_pins
        or len(full_owner_pins) > MAX_FULL_OWNER_PINS_PER_MATERIAL
        or type(direct_body_pins) is not list
        or not direct_body_pins
        or len(direct_body_pins) > MAX_DIRECT_BODY_PINS_PER_MATERIAL
        or any(
            type(pin) is not dict or set(pin) != FULL_OWNER_PIN_FIELDS
            for pin in full_owner_pins
        )
        or any(
            type(pin) is not dict or set(pin) != DIRECT_PIN_FIELDS
            for pin in direct_body_pins
        )
    ):
        _fail("complete projection material owner chain is invalid")
    return {
        "coordinates": copy.deepcopy(material["coordinates"]),
        "direct_body_pins": copy.deepcopy(direct_body_pins),
        "full_owner_pins": copy.deepcopy(full_owner_pins),
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


def _converted_partial_receipts(partial_inventory):
    receipts = []
    for row in partial_inventory["derivation_receipts"]:
        converted = copy.deepcopy(row)
        converted["row_schema"] = RECEIPT_SCHEMA
        receipts.append(converted)
    return receipts


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
                raise PersonaV2SemanticProjectionCompleteInventoryError(
                    "projection material iterator failed to open"
                ) from error
            materials = []
            for index in range(expected_count + 1):
                try:
                    value = next(iterator)
                except StopIteration:
                    break
                except Exception as error:
                    raise PersonaV2SemanticProjectionCompleteInventoryError(
                        "projection material iterator failed during bounded read"
                    ) from error
                if index == expected_count:
                    _fail("projection material iterator exceeded its exact count")
                material = _normalize_material(value)
                if material["projection_class_id"] not in allowed_classes:
                    _fail("projection material iterator emitted a foreign class")
                if cumulative_state is not None:
                    cumulative_state[0] += len(material["body"])
                    if cumulative_state[0] > MAX_CUMULATIVE_PROJECTION_BYTES:
                        _fail("projection material iterator exceeded its running byte cap")
                materials.append(material)
            if len(materials) != expected_count:
                _fail("projection material iterator ended before its exact count")
            return materials
    _fail(f"projection material iterator is unavailable: {names[0]}")


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
    _fail(f"cannot derive a receipt ID for {class_id} coordinates")


def _normalize_material(value):
    if type(value) is not dict or len(value) not in {9, 10, 11}:
        _fail("projection material must use one exact source schema")
    source_fields = frozenset(value)
    if source_fields not in SOURCE_MATERIAL_FIELD_SETS:
        _fail("projection material must use one exact source schema")
    body = value.get("body", value.get("bytes"))
    framing = value.get("body_framing", value.get("framing"))
    class_id = value.get("projection_class_id", value.get("class_id"))
    coordinates = value.get("coordinates")
    if type(class_id) is not str or class_id not in NEW_PROJECTOR_IDS:
        _fail("projection material class identity drifted")
    _preflight_coordinates(class_id, coordinates)
    body_cap = (
        MAX_JSONL_PROJECTION_BYTES
        if framing == "canonical-jsonl-lf"
        else MAX_JSON_PROJECTION_BYTES
    )
    if (
        framing not in {"canonical-json", "canonical-jsonl-lf"}
        or type(body) is not bytes
        or not body
        or len(body) > body_cap
    ):
        _fail("projection material body exceeds its pre-hash class cap")
    artifact_kind = value.get("artifact_kind")
    artifact_schema = value.get("artifact_schema")
    artifact_version = value.get("artifact_schema_version")
    _bounded_text(artifact_kind, label="projection material artifact kind")
    _bounded_text(artifact_schema, label="projection material artifact schema")
    _bounded_int(
        artifact_version,
        label="projection material artifact version",
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
        _fail("projection material pin cardinality exceeds its pre-copy bound")
    for pin in full_owner_pins:
        _preflight_pin(pin, owner=True)
    for pin in direct_body_pins:
        _preflight_pin(pin, owner=False)
    expected_projector_id = NEW_PROJECTOR_IDS[class_id]
    expected_receipt_id = _expected_new_receipt_id(class_id, coordinates)
    if source_fields == GLOBAL_SOURCE_MATERIAL_FIELDS:
        projector = value.get("projector")
        if type(projector) is not dict or len(projector) != 2 or set(projector) != {
            "projector_id",
            "projector_version",
        }:
            _fail("projection material projector schema drifted")
        projector_id = projector.get("projector_id")
        projector_version = projector.get("projector_version")
        if (
            type(projector_version) is not int
            or type(projector_version) is bool
            or projector_version != 1
        ):
            _fail("projection material projector version drifted")
        receipt_id = expected_receipt_id
    elif source_fields == LEGACY_SOURCE_MATERIAL_FIELDS:
        projector_id = expected_projector_id
        receipt_id = expected_receipt_id
    else:
        projector_id = value.get("projector_id")
        receipt_id = value.get("receipt_id")
        _bounded_text(projector_id, label="explicit projection material projector ID")
        _bounded_text(receipt_id, label="explicit projection material receipt ID")
    if projector_id != expected_projector_id:
        _fail("projection material projector identity drifted")
    if receipt_id != expected_receipt_id:
        _fail("projection material receipt identity drifted")
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
        _fail("normalized projection material schema drifted")
    return normalized


def _new_projection_materials():
    group_specs = (
        (
            global_content,
            (
                "iter_global_content_projection_materials",
                "build_global_content_projection_materials",
            ),
            3,
            {
                "topology-path-load",
                "realism-locale-security",
                "route-scores",
            },
        ),
        (
            corpus_content,
            (
                "iter_corpus_content_projection_materials",
                "build_corpus_content_projection_materials",
            ),
            22,
            {
                "primary-use-case-corpus-half",
                "recipe-content-filename-policy",
                "fact-graph",
            },
        ),
        (
            relations_parameters,
            (
                "iter_relations_parameter_projection_materials",
                "build_relations_parameter_projection_materials",
            ),
            114,
            {
                "concrete-overlay-relations",
                "source-instance-parameters",
            },
        ),
        (
            payload_rules,
            (
                "iter_payload_equivalence_projection_materials",
                "build_payload_equivalence_projection_materials",
            ),
            1,
            {"payload-equivalence-rules"},
        ),
    )
    result = []
    cumulative_state = [partial.EXPECTED_CUMULATIVE_PROJECTION_BYTES]
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
        _fail("new projection material total drifted")
    return result


def _all_receipts(partial_inventory):
    by_class = {class_id: [] for class_id in PROJECTION_CLASS_ORDER}
    for receipt in _converted_partial_receipts(partial_inventory):
        by_class[receipt["projection_class_id"]].append(receipt)
    for material in _new_projection_materials():
        receipt = _receipt_from_material(material)
        by_class[receipt["projection_class_id"]].append(receipt)
    receipts = [
        receipt
        for class_id in PROJECTION_CLASS_ORDER
        for receipt in by_class[class_id]
    ]
    actual_counts = {
        class_id: len(by_class[class_id]) for class_id in PROJECTION_CLASS_ORDER
    }
    if actual_counts != EXPECTED_RECEIPT_COUNTS:
        _fail(
            "complete projection receipt counts drifted: "
            f"expected {EXPECTED_RECEIPT_COUNTS!r}, got {actual_counts!r}"
        )
    if len(receipts) != MAX_RECEIPT_COUNT:
        _fail("complete projection receipt total drifted")
    return receipts


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


def _predecessor_binding(partial_inventory):
    raw = partial.canonical_json_bytes(partial_inventory)
    return {
        "artifact_kind": partial.SUITE_KIND,
        "artifact_schema": partial.SUITE_SCHEMA,
        "artifact_schema_version": partial.ARTIFACT_SCHEMA_VERSION,
        "body_framing": "canonical-json",
        "canonical_bytes": len(raw),
        "sha256": _sha256(raw),
    }


def _build_inventory_value():
    partial_inventory = partial.build_semantic_projection_derivation_inventory()
    partial_raw = partial.canonical_json_bytes(partial_inventory)
    if (
        len(partial_raw) != partial.EXPECTED_SUITE_CANONICAL_BYTES
        or _sha256(partial_raw) != partial.EXPECTED_SUITE_SHA256
    ):
        _fail("frozen partial semantic projection inventory pin drifted")
    receipts = _all_receipts(partial_inventory)
    if len({row["receipt_id"] for row in receipts}) != len(receipts):
        _fail("complete projection receipt IDs must be unique")
    projection_identities = {
        (
            row["projection_pin"]["sha256"],
            row["projection_pin"]["canonical_bytes"],
        )
        for row in receipts
    }
    if len(projection_identities) != len(receipts):
        _fail("complete projection bodies must be unique across coordinates")
    if any(set(row) != RECEIPT_FIELDS for row in receipts):
        _fail("complete projection receipt schema drifted")
    cumulative_bytes = sum(
        row["projection_pin"]["canonical_bytes"] for row in receipts
    )
    if cumulative_bytes > MAX_CUMULATIVE_PROJECTION_BYTES:
        _fail("complete external projection bodies exceed their cumulative cap")
    if cumulative_bytes != EXPECTED_CUMULATIVE_EXTERNAL_BODY_BYTES:
        _fail("complete external projection body bytes drifted from frozen total")
    ordered_pin_rows = [
        {
            "canonical_bytes": row["projection_pin"]["canonical_bytes"],
            "receipt_id": row["receipt_id"],
            "sha256": row["projection_pin"]["sha256"],
        }
        for row in receipts
    ]
    ordered_pin_digest = _sha256(
        _canonical_fragment(
            ordered_pin_rows,
            label="complete ordered semantic projection pin rows",
        )
    )
    if ordered_pin_digest != EXPECTED_ORDERED_PROJECTION_PINS_SHA256:
        _fail("complete ordered projection pin digest drifted")
    counts = {
        class_id: sum(
            receipt["projection_class_id"] == class_id for receipt in receipts
        )
        for class_id in PROJECTION_CLASS_ORDER
    }
    value = {
        "artifact_kind": SUITE_KIND,
        "artifact_schema": SUITE_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": _negative_authority(),
        "canonical_limits": {
            "external_projection_bodies_embedded": False,
            "max_base_or_overlay_jsonl_row_bytes_including_lf": (
                MAX_BASE_OR_OVERLAY_ROW_BYTES_INCLUDING_LF
            ),
            "max_cumulative_external_projection_bytes": (
                MAX_CUMULATIVE_PROJECTION_BYTES
            ),
            "max_json_projection_bytes": MAX_JSON_PROJECTION_BYTES,
            "max_jsonl_projection_bytes": MAX_JSONL_PROJECTION_BYTES,
            "max_jsonl_projection_rows": MAX_JSONL_ROWS,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_parameter_jsonl_row_bytes_including_lf": (
                MAX_PARAMETER_ROW_BYTES_INCLUDING_LF
            ),
            "max_receipt_count": MAX_RECEIPT_COUNT,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "max_suite_bytes": MAX_SUITE_BYTES,
            "self_hash_embedded": False,
            "target_json_projection_bytes": TARGET_JSON_PROJECTION_BYTES,
            "target_suite_bytes": TARGET_SUITE_BYTES,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_253_receipts_bound": True,
            "corpus_semantic_namespace_issued": False,
            "future_source_id_namespace_eligible": True,
            "local_twelve_class_derivation_complete": True,
            "minimum_projection_inventory_complete": True,
            "query_semantics_absence_proved": True,
            "semantic_payload_projection_bound": True,
        },
        "derivation_receipts": receipts,
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "hypothesis_status": (
            "authored-benchmark-complete-content-projection-derivation-"
            "evidence-not-observed-user-data"
        ),
        "missing_projection_class_ledger": [],
        "orders": {
            "derivation_receipts": (
                "minimum-projection-class-order-then-class-specific-canonical-"
                "global-persona-origin-shard-order"
            ),
            "minimum_projection_classes": list(PROJECTION_CLASS_ORDER),
            "persona": list(envelope.PERSONA_IDS),
        },
        "predecessor_inventory_binding": _predecessor_binding(partial_inventory),
        "projection_class_registry": _projection_class_registry(),
        "remaining_blockers": [
            "corpus-semantic-namespace-not-issued",
            "positive-independent-route-and-profile-review-receipts-not-bound",
            "corpus-input-query-history-closures-and-blocker-resolution-ledger-not-complete",
            "joint-solver-solution-proof-and-final-source-plan-not-built",
            "solution-compiled-history-plan-and-g0-descriptor-not-built",
            "physical-materialization-capacity-kcs-history-and-evaluation-not-observed",
        ],
        "summary": {
            "covered_projection_class_count": len(PROJECTION_CLASS_ORDER),
            "cumulative_external_projection_bytes": cumulative_bytes,
            "derivation_receipt_count": len(receipts),
            "external_projection_body_count": len(receipts),
            "json_projection_body_count": sum(
                row["projection_pin"]["body_framing"] == "canonical-json"
                for row in receipts
            ),
            "jsonl_projection_body_count": sum(
                row["projection_pin"]["body_framing"] == "canonical-jsonl-lf"
                for row in receipts
            ),
            "minimum_projection_class_count": len(PROJECTION_CLASS_ORDER),
            "missing_projection_class_count": 0,
            "persona_count": len(envelope.PERSONA_IDS),
            "receipt_counts_by_projection_class": counts,
        },
    }
    if set(value) != TOP_LEVEL_FIELDS:
        _fail("complete projection inventory top-level schema drifted")
    if set(value["authority"]) != AUTHORITY_FIELDS or any(
        value["authority"].values()
    ):
        _fail("complete projection inventory gained authority")
    raw = canonical_json_bytes(value)
    if len(raw) > MAX_SUITE_BYTES:
        _fail("complete projection inventory exceeds its descriptor cap")
    if len(raw) != EXPECTED_SUITE_CANONICAL_BYTES:
        _fail("complete projection inventory byte length drifted")
    if _sha256(raw) != EXPECTED_SUITE_SHA256:
        _fail("complete projection inventory SHA-256 drifted")
    return value


@functools.lru_cache(maxsize=1)
def _canonical_inventory_raw():
    return canonical_json_bytes(_build_inventory_value())


def build_semantic_projection_complete_inventory():
    """Return a detached complete descriptor without embedding external bodies."""

    return json.loads(_canonical_inventory_raw())


def _require_exact_inventory_receipt(receipt):
    if type(receipt) is not dict or set(receipt) != RECEIPT_FIELDS:
        _fail("complete projection provider requires one exact receipt")
    receipt_id = receipt.get("receipt_id")
    if type(receipt_id) is not str or not receipt_id:
        _fail("complete projection provider receipt identity is invalid")
    inventory = build_semantic_projection_complete_inventory()
    matches = [
        row for row in inventory["derivation_receipts"] if row["receipt_id"] == receipt_id
    ]
    if len(matches) != 1:
        _fail("complete projection provider receipt is outside the inventory")
    supplied = _canonical_fragment(receipt, label="supplied complete receipt")
    expected = _canonical_fragment(matches[0], label="expected complete receipt")
    if not hmac.compare_digest(supplied, expected):
        _fail("complete projection provider receipt differs from the inventory")


def _partial_v1_receipt(receipt):
    value = copy.deepcopy(receipt)
    value["row_schema"] = partial.RECEIPT_SCHEMA
    return value


def _dispatch_new_projection_body(module, projection_class_id, coordinates):
    for name in (
        "projection_body_bytes",
        "content_projection_body_bytes",
        "build_projection_body_bytes",
    ):
        function = getattr(module, name, None)
        if callable(function):
            body = function(projection_class_id, copy.deepcopy(coordinates))
            if type(body) is not bytes:
                _fail("content projection body dispatch returned a non-bytes value")
            return body
    _fail(f"content projection body dispatch is unavailable for {projection_class_id}")


def projection_body_provider(receipt):
    """Regenerate one exact external body selected by a v2 receipt."""

    _require_exact_inventory_receipt(receipt)
    class_id = receipt["projection_class_id"]
    coordinates = receipt["coordinates"]
    if class_id in partial.COVERED_CLASS_ORDER:
        body = partial.projection_body_provider(_partial_v1_receipt(receipt))
    elif class_id in {
        "topology-path-load",
        "realism-locale-security",
        "route-scores",
    }:
        body = _dispatch_new_projection_body(global_content, class_id, coordinates)
    elif class_id in {
        "primary-use-case-corpus-half",
        "recipe-content-filename-policy",
        "fact-graph",
    }:
        body = _dispatch_new_projection_body(corpus_content, class_id, coordinates)
    elif class_id in {
        "concrete-overlay-relations",
        "source-instance-parameters",
    }:
        body = _dispatch_new_projection_body(
            relations_parameters, class_id, coordinates
        )
    elif class_id == "payload-equivalence-rules":
        body = _dispatch_new_projection_body(payload_rules, class_id, coordinates)
    else:  # pragma: no cover - guarded by exact receipt authentication.
        _fail("complete projection provider received an unknown class")
    pin = receipt["projection_pin"]
    if (
        type(body) is not bytes
        or len(body) != pin["canonical_bytes"]
        or not hmac.compare_digest(_sha256(body), pin["sha256"])
    ):
        _fail("complete projection provider body differs from its exact pin")
    return body


def _independent_validator():
    try:
        from . import persona_v2_semantic_projection_complete_inventory_validator as independent
    except ImportError:  # pragma: no cover - direct-script compatibility
        try:
            import persona_v2_semantic_projection_complete_inventory_validator as independent
        except ImportError:
            independent = None
    return independent


def validate_semantic_projection_complete_inventory(
    value,
    projection_body_provider=None,
):
    """Validate through the complete producer-independent replay boundary."""

    raw = canonical_json_bytes(value)
    independent = _independent_validator()
    if independent is None:
        _fail("independent complete semantic projection validator is unavailable")
    provider = (
        globals()["projection_body_provider"]
        if projection_body_provider is None
        else projection_body_provider
    )
    try:
        result = independent.validate_semantic_projection_complete_inventory(
            value,
            projection_body_provider=provider,
        )
    except independent.PersonaV2SemanticProjectionCompleteInventoryValidationError as error:
        _fail(str(error))
    finally:
        closing_raw = canonical_json_bytes(value)
        if not hmac.compare_digest(raw, closing_raw):
            _fail("complete projection inventory changed during validation")
    if result is not True:
        _fail("independent complete projection validator did not return exact True")
    return True


def semantic_projection_complete_inventory_sha256(
    value=None,
    projection_body_provider=None,
):
    """Hash exactly the detached opening bytes accepted by validation."""

    if value is None:
        value = build_semantic_projection_complete_inventory()
    raw = canonical_json_bytes(value)
    validate_semantic_projection_complete_inventory(
        value,
        projection_body_provider=projection_body_provider,
    )
    if not hmac.compare_digest(raw, canonical_json_bytes(value)):
        _fail("complete projection inventory changed while hashing")
    return _sha256(raw)


def require_complete_semantic_projection_inventory():
    """Return the independently accepted complete inventory descriptor."""

    value = build_semantic_projection_complete_inventory()
    validate_semantic_projection_complete_inventory(value)
    return value


__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "AUTHORITY_FIELDS",
    "COVERED_CLASS_ORDER",
    "EXPECTED_CUMULATIVE_EXTERNAL_BODY_BYTES",
    "EXPECTED_ORDERED_PROJECTION_PINS_SHA256",
    "EXPECTED_RECEIPT_COUNTS",
    "EXPECTED_SUITE_CANONICAL_BYTES",
    "EXPECTED_SUITE_SHA256",
    "MAX_CUMULATIVE_PROJECTION_BYTES",
    "MAX_JSONL_PROJECTION_BYTES",
    "MAX_JSONL_ROWS",
    "MAX_JSON_PROJECTION_BYTES",
    "MAX_RECEIPT_COUNT",
    "MAX_SUITE_BYTES",
    "MISSING_CLASS_ORDER",
    "PROJECTION_CLASS_ORDER",
    "PersonaV2SemanticProjectionCompleteInventoryError",
    "RECEIPT_SCHEMA",
    "SUITE_KIND",
    "SUITE_SCHEMA",
    "TARGET_JSON_PROJECTION_BYTES",
    "TARGET_SUITE_BYTES",
    "build_semantic_projection_complete_inventory",
    "canonical_json_bytes",
    "projection_body_provider",
    "require_complete_semantic_projection_inventory",
    "semantic_projection_complete_inventory_sha256",
    "validate_semantic_projection_complete_inventory",
]
