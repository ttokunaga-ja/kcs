"""Content-only relation and source-parameter projections for persona-PC v2.

This module adds two missing semantic-projection classes without changing any
upstream artifact.  Forty persona/origin JSONL bodies reproduce the existing
concrete-overlay draft mapping (19,870 content relations plus 5,690 attachment
memberships).  One shared JSON body owns 363 parameter-cell definitions and
seventy-three JSONL bodies map every one of the 203,000 source intents to one
cell.

Projection bodies contain content only.  Full-owner and direct-fragment pins
are returned beside each body as derivation material; they are deliberately
not embedded in the body that will enter the future semantic namespace.
"""

from __future__ import annotations

import copy
import functools
import hashlib
import hmac
import json

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_concrete_overlay_membership_package as concrete
    from . import persona_v2_concrete_overlay_membership_package_validator as concrete_validator
    from . import persona_v2_contract as envelope
    from . import persona_v2_source_parameter_assignment_package as parameters
    from . import persona_v2_source_parameter_assignment_package_validator as parameters_validator
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_concrete_overlay_membership_package as concrete
    import persona_v2_concrete_overlay_membership_package_validator as concrete_validator
    import persona_v2_contract as envelope
    import persona_v2_source_parameter_assignment_package as parameters
    import persona_v2_source_parameter_assignment_package_validator as parameters_validator


RELATION_CLASS_ID = "concrete-overlay-relations"
PARAMETER_CLASS_ID = "source-instance-parameters"
CLASS_ORDER = (RELATION_CLASS_ID, PARAMETER_CLASS_ID)

RELATION_SCHEMA = (
    "kio.persona.pc-concrete-overlay-relations-origin-projection/v1"
)
RELATION_KIND = "persona-pc-v2-concrete-overlay-relations-origin-projection"
CELL_SCHEMA = "kio.persona.pc-source-parameter-cell-content-projection/v1"
CELL_KIND = "persona-pc-v2-source-parameter-cell-content-projection"
ASSIGNMENT_SCHEMA = (
    "kio.persona.pc-source-instance-parameter-assignment-shard-projection/v1"
)
ASSIGNMENT_KIND = (
    "persona-pc-v2-source-instance-parameter-assignment-shard-projection"
)
ARTIFACT_SCHEMA_VERSION = 1

EXPECTED_RELATION_BODY_COUNT = 40
EXPECTED_RELATION_ROW_COUNT = 25_560
EXPECTED_CELL_BODY_COUNT = 1
EXPECTED_CELL_COUNT = 363
EXPECTED_ASSIGNMENT_BODY_COUNT = 73
EXPECTED_ASSIGNMENT_ROW_COUNT = 203_000
EXPECTED_ASSIGNMENT_BODY_BYTES = 17_527_680
EXPECTED_MATERIAL_COUNT = 114

MAX_RELATION_BODY_BYTES = 4 * 2**20
MAX_RELATION_ROWS = 4_096
MAX_RELATION_ROW_BYTES_INCLUDING_LF = 768
MAX_CELL_BODY_BYTES = 256 * 2**10
MAX_ASSIGNMENT_BODY_BYTES = 1 * 2**20
MAX_ASSIGNMENT_ROWS = 4_096
MAX_ASSIGNMENT_ROW_BYTES_INCLUDING_LF = 256
MAX_FRAGMENT_BYTES = 4 * 2**20
MAX_COORDINATE_BYTES = 4_096
MAX_COORDINATE_FIELD_COUNT = 4
MAX_COORDINATE_KEY_CHARS = 64
MAX_COORDINATE_SCALAR_CHARS = 256
MAX_COORDINATE_SCALAR_BYTES = 512

MATERIAL_FIELDS = frozenset(
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
FULL_OWNER_PIN_FIELDS = GENERIC_PIN_FIELDS | {
    "coordinates",
    "owner_id",
    "owner_role",
}
DIRECT_BODY_PIN_FIELDS = frozenset(
    {
        "body_framing",
        "canonical_bytes",
        "direct_pin_id",
        "direct_pin_role",
        "sha256",
    }
)
CELL_PROJECTION_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "fixture_id",
        "fixture_schema_version",
        "orders",
        "parameter_cells",
    }
)
CELL_FIELDS = frozenset(
    {
        "bin_id",
        "parameter_cell_key",
        "recipe_profile_id",
        "renderer_parameters",
        "size_lane",
        "target_bytes",
        "target_complexity",
        "variant_id",
    }
)
RELATION_CONTENT_FIELDS = frozenset(
    {
        "anchor_intent_key",
        "cluster_key",
        "derivative_intent_key",
        "placement_class",
        "relation_kind",
        "row_kind",
        "search_participation_profile_id",
    }
)
RELATION_ATTACHMENT_FIELDS = frozenset(
    {
        "attachment_key",
        "decoded_payload_equivalence_key",
        "host_intent_key",
        "member_ordinal",
        "row_kind",
        "search_participation_profile_id",
        "standalone_member_intent_key",
    }
)
ASSIGNMENT_ROW_FIELDS = frozenset({"intent_key", "parameter_cell_key"})

CONCRETE_SUITE_PIN = (
    concrete.SUITE_ARTIFACT_KIND,
    concrete.SUITE_ARTIFACT_SCHEMA,
    concrete.ARTIFACT_SCHEMA_VERSION,
    "canonical-json",
    concrete_validator.EXPECTED_SUITE_DESCRIPTOR_BYTES,
    concrete_validator.EXPECTED_SUITE_SHA256,
)
PARAMETER_SUITE_PIN = (
    parameters.SUITE_KIND,
    parameters.SUITE_SCHEMA,
    parameters.ARTIFACT_SCHEMA_VERSION,
    "canonical-json",
    parameters_validator.EXPECTED_SUITE_CANONICAL_BYTES,
    parameters_validator.EXPECTED_SUITE_SHA256,
)


class PersonaV2SemanticProjectionRelationsParametersError(ValueError):
    """Raised when relation/parameter projection derivation is not exact."""


def _fail(message):
    raise PersonaV2SemanticProjectionRelationsParametersError(message)


def _sha256(raw):
    if type(raw) is not bytes:
        _fail("SHA-256 input must be exact built-in bytes")
    return hashlib.sha256(raw).hexdigest()


def _canonical(value, *, label, maximum):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label=label,
            max_bytes=maximum,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _strict_load(raw, *, label):
    if type(raw) is not bytes:
        _fail(f"{label} must be exact built-in bytes")

    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                _fail(f"{label} contains duplicate key {key!r}")
            value[key] = item
        return value

    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=pairs,
            parse_float=lambda _value: _fail(f"{label} contains a float"),
            parse_constant=lambda _value: _fail(
                f"{label} contains a non-finite number"
            ),
        )
    except PersonaV2SemanticProjectionRelationsParametersError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        _fail(f"{label} is not strict UTF-8 JSON: {error}")
    try:
        artifact_common.validate_plain_value(value, label=label)
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))
    return value


def _require_persona(persona_id):
    if type(persona_id) is not str or persona_id not in envelope.PERSONA_IDS:
        _fail("persona_id is outside the exact twenty-person suite")


def _require_origin(origin):
    if type(origin) is not str or origin not in concrete.ORIGIN_ORDER:
        _fail("origin must be pilot or full-residual")


def _require_true(result, *, label):
    if result is not True:
        _fail(f"{label} did not return exact True")


def _generic_pin(value, *, canonicalizer, maximum, framing="canonical-json"):
    raw = canonicalizer(value)
    if type(raw) is not bytes or not raw or len(raw) > maximum:
        _fail("upstream canonicalizer violated its byte contract")
    return {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "body_framing": framing,
        "canonical_bytes": len(raw),
        "sha256": _sha256(raw),
    }


def _owner_pin(pin, *, coordinates, owner_id, owner_role):
    return {
        **copy.deepcopy(pin),
        "coordinates": copy.deepcopy(coordinates),
        "owner_id": owner_id,
        "owner_role": owner_role,
    }


def _suite_pin_value(pin):
    kind, schema, version, framing, canonical_bytes, digest = pin
    return {
        "artifact_kind": kind,
        "artifact_schema": schema,
        "artifact_schema_version": version,
        "body_framing": framing,
        "canonical_bytes": canonical_bytes,
        "sha256": digest,
    }


def _direct_pin(raw, *, direct_pin_id, direct_pin_role, framing):
    if type(raw) is not bytes or not raw or len(raw) > MAX_FRAGMENT_BYTES:
        _fail("direct fragment violates its byte contract")
    return {
        "body_framing": framing,
        "canonical_bytes": len(raw),
        "direct_pin_id": direct_pin_id,
        "direct_pin_role": direct_pin_role,
        "sha256": _sha256(raw),
    }


def _find_one(rows, *, label, predicate):
    matches = [row for row in rows if predicate(row)]
    if len(matches) != 1:
        _fail(f"{label} must resolve exactly one row")
    return matches[0]


def _require_rich_body_descriptor(
    origin_value, rich_body, *, persona_id, origin
):
    descriptors = origin_value.get("shard_descriptors")
    if type(descriptors) is not list or len(descriptors) != 1:
        _fail("concrete relation origin must have exactly one rich shard")
    descriptor = descriptors[0]
    if (
        type(descriptor) is not dict
        or set(descriptor) != concrete.SHARD_DESCRIPTOR_FIELDS
        or descriptor.get("persona_id") != persona_id
        or descriptor.get("origin") != origin
        or descriptor.get("shard_index") != 0
        or descriptor.get("file_name")
        != f"{persona_id}-concrete-overlay-membership-{origin}-0000.jsonl"
        or type(rich_body) is not bytes
        or not rich_body
        or len(rich_body) > concrete.MAX_SHARD_BODY_BYTES
        or not rich_body.endswith(b"\n")
        or b"\r" in rich_body
        or descriptor.get("body_bytes") != len(rich_body)
        or descriptor.get("body_sha256") != _sha256(rich_body)
    ):
        _fail("concrete rich body differs from its exact shard descriptor")
    framed_rows = rich_body.splitlines(keepends=True)
    if (
        descriptor.get("row_count") != len(framed_rows)
        or descriptor.get("maximum_row_bytes_including_lf")
        != max(map(len, framed_rows))
    ):
        _fail("concrete rich body row framing differs from its descriptor")
    return descriptor


@functools.lru_cache(maxsize=1)
def _concrete_suite_raw():
    value = concrete.build_concrete_overlay_membership_suite_descriptor()
    _require_true(
        concrete.validate_concrete_overlay_membership_suite_descriptor(value),
        label="concrete overlay suite validator",
    )
    raw = concrete.canonical_json_bytes(value)
    if (
        len(raw) != CONCRETE_SUITE_PIN[4]
        or _sha256(raw) != CONCRETE_SUITE_PIN[5]
    ):
        _fail("concrete overlay suite frozen pin drifted")
    return bytes(raw)


@functools.lru_cache(maxsize=1)
def _parameter_suite_raw():
    value = parameters.build_source_parameter_assignment_suite_descriptor()
    _require_true(
        parameters.validate_source_parameter_assignment_suite_descriptor(value),
        label="source parameter suite validator",
    )
    raw = parameters.canonical_json_bytes(value)
    if (
        len(raw) != PARAMETER_SUITE_PIN[4]
        or _sha256(raw) != PARAMETER_SUITE_PIN[5]
    ):
        _fail("source parameter suite frozen pin drifted")
    return bytes(raw)


def _concrete_suite():
    return _strict_load(_concrete_suite_raw(), label="concrete overlay suite")


def _parameter_suite():
    return _strict_load(_parameter_suite_raw(), label="source parameter suite")


def _relation_projection_row(row):
    if type(row) is not dict:
        _fail("concrete rich row must be an exact object")
    if row.get("row_kind") == "content-relation-membership":
        if set(row) != concrete.CONTENT_RELATION_ROW_FIELDS:
            _fail("concrete content relation owner row schema drifted")
        value = {
            "anchor_intent_key": row["anchor_intent_key"],
            "cluster_key": row["cluster_key"],
            "derivative_intent_key": row["derivative_intent_key"],
            "placement_class": row["placement_class_requirement"],
            "relation_kind": row["relation_kind"],
            "row_kind": "content-relation",
            "search_participation_profile_id": row[
                "search_participation_requirement_id"
            ],
        }
        expected = RELATION_CONTENT_FIELDS
    elif row.get("row_kind") == "attachment-membership":
        if set(row) != concrete.ATTACHMENT_ROW_FIELDS:
            _fail("concrete attachment owner row schema drifted")
        value = {
            "attachment_key": row["attachment_key"],
            "decoded_payload_equivalence_key": row[
                "decoded_payload_equivalence_key"
            ],
            "host_intent_key": row["host_intent_key"],
            "member_ordinal": row["member_ordinal"],
            "row_kind": "attachment-membership",
            "search_participation_profile_id": row[
                "search_participation_requirement_id"
            ],
            "standalone_member_intent_key": row["standalone_member_intent_key"],
        }
        expected = RELATION_ATTACHMENT_FIELDS
    else:
        _fail("semantic-anchor rows are not concrete relation projections")
    if set(value) != expected:
        _fail("concrete relation projection row schema drifted")
    return value


@functools.lru_cache(maxsize=EXPECTED_RELATION_BODY_COUNT)
def _relation_body_cached(persona_id, origin):
    _require_persona(persona_id)
    _require_origin(origin)
    parts = []
    for row in concrete.iter_concrete_overlay_membership_origin_rows(
        persona_id, origin
    ):
        if (
            type(row) is dict
            and row.get("row_kind") == "semantic-anchor-membership"
        ):
            if set(row) != concrete.SEMANTIC_ANCHOR_ROW_FIELDS:
                _fail("concrete semantic-anchor owner row schema drifted")
            continue
        projected = _relation_projection_row(row)
        raw = _canonical(
            projected,
            label="concrete overlay relation projection row",
            maximum=MAX_RELATION_ROW_BYTES_INCLUDING_LF - 1,
        )
        parts.append(raw + b"\n")
    if not parts or len(parts) > MAX_RELATION_ROWS:
        _fail("concrete relation projection row count violates its cap")
    body = b"".join(parts)
    if len(body) > MAX_RELATION_BODY_BYTES:
        _fail("concrete relation projection exceeds its body cap")
    return bytes(body)


def concrete_overlay_relations_projection_body_bytes(persona_id, origin):
    """Return one exact persona/origin relation-only JSONL projection."""

    return bytes(_relation_body_cached(persona_id, origin))


@functools.lru_cache(maxsize=1)
def _cell_body_cached():
    catalog = parameters.build_source_parameter_cell_catalog()
    _require_true(
        parameters.validate_source_parameter_cell_catalog(catalog),
        label="source parameter cell catalog validator",
    )
    value = {
        "artifact_kind": CELL_KIND,
        "artifact_schema": CELL_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "orders": copy.deepcopy(catalog["orders"]),
        "parameter_cells": copy.deepcopy(catalog["parameter_cells"]),
    }
    if set(value) != CELL_PROJECTION_FIELDS:
        _fail("parameter cell content projection schema drifted")
    if len(value["parameter_cells"]) != EXPECTED_CELL_COUNT or any(
        set(row) != CELL_FIELDS for row in value["parameter_cells"]
    ):
        _fail("parameter cell content projection rows drifted")
    return _canonical(
        value,
        label="source parameter cell content projection",
        maximum=MAX_CELL_BODY_BYTES,
    )


def source_parameter_cell_content_projection_body_bytes():
    """Return the shared 363-cell canonical JSON content projection."""

    return bytes(_cell_body_cached())


@functools.lru_cache(maxsize=EXPECTED_ASSIGNMENT_BODY_COUNT)
def _assignment_body_cached(persona_id, origin, shard_ordinal):
    _require_persona(persona_id)
    _require_origin(origin)
    if type(shard_ordinal) is not int or type(shard_ordinal) is bool or shard_ordinal < 1:
        _fail("assignment shard ordinal must be a positive exact integer")
    body = parameters.source_parameter_assignment_expanded_view_body_bytes(
        persona_id, origin, shard_ordinal
    )
    if type(body) is not bytes or not body or len(body) > MAX_ASSIGNMENT_BODY_BYTES:
        _fail("assignment projection violates its body cap")
    return bytes(body)


def source_parameter_assignment_projection_body_bytes(
    persona_id, origin, shard_ordinal
):
    """Return one exact intent-to-parameter-cell assignment JSONL shard."""

    return bytes(_assignment_body_cached(persona_id, origin, shard_ordinal))


def _concrete_origin(persona_id, origin):
    value = concrete.build_concrete_overlay_membership_origin_manifest(
        persona_id, origin
    )
    _require_true(
        concrete.validate_concrete_overlay_membership_origin_manifest(
            persona_id, origin, value
        ),
        label="concrete overlay origin validator",
    )
    return value


def _parameter_origin(persona_id, origin):
    value = parameters.build_source_parameter_assignment_origin_manifest(
        persona_id, origin
    )
    _require_true(
        parameters.validate_source_parameter_assignment_origin_manifest(
            persona_id, origin, value
        ),
        label="source parameter origin validator",
    )
    return value


def _relation_material(persona_id, origin):
    suite = _concrete_suite()
    origin_value = _concrete_origin(persona_id, origin)
    body = concrete_overlay_relations_projection_body_bytes(persona_id, origin)
    draft = origin_value["draft_membership_projection_receipt"]
    if (
        draft["body_bytes"] != len(body)
        or draft["body_sha256"] != _sha256(body)
    ):
        _fail("relation body differs from the authenticated draft receipt")
    binding = _find_one(
        suite["origin_manifest_bindings"],
        label="concrete suite origin binding",
        predicate=lambda row: row.get("persona_id") == persona_id
        and row.get("origin") == origin,
    )
    origin_pin = _generic_pin(
        origin_value,
        canonicalizer=concrete.canonical_json_bytes,
        maximum=concrete.MAX_ORIGIN_MANIFEST_BYTES,
    )
    if (
        binding.get("canonical_bytes") != origin_pin["canonical_bytes"]
        or binding.get("sha256") != origin_pin["sha256"]
        or binding.get("artifact_schema") != origin_pin["artifact_schema"]
    ):
        _fail("concrete suite-to-origin owner chain drifted")
    rich = concrete.concrete_overlay_membership_shard_body_bytes(
        persona_id, origin, 0
    )
    _require_rich_body_descriptor(
        origin_value, rich, persona_id=persona_id, origin=origin
    )
    coordinates = {"origin": origin, "persona_id": persona_id}
    return {
        "artifact_kind": RELATION_KIND,
        "artifact_schema": RELATION_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "bytes": body,
        "class_id": RELATION_CLASS_ID,
        "coordinates": coordinates,
        "direct_body_pins": [
            _direct_pin(
                _canonical(
                    binding,
                    label="concrete suite origin binding",
                    maximum=MAX_FRAGMENT_BYTES,
                ),
                direct_pin_id=f"concrete-suite-origin-binding-{persona_id}-{origin}",
                direct_pin_role="suite-origin-binding-row",
                framing="canonical-json",
            ),
            _direct_pin(
                _canonical(
                    draft,
                    label="concrete draft projection receipt",
                    maximum=MAX_FRAGMENT_BYTES,
                ),
                direct_pin_id=f"concrete-draft-receipt-{persona_id}-{origin}",
                direct_pin_role="origin-draft-projection-receipt-row",
                framing="canonical-json",
            ),
            _direct_pin(
                rich,
                direct_pin_id=f"concrete-rich-origin-body-{persona_id}-{origin}",
                direct_pin_role="receipt-authenticated-rich-origin-jsonl-body",
                framing="canonical-jsonl-lf",
            ),
        ],
        "framing": "canonical-jsonl-lf",
        "full_owner_pins": [
            _owner_pin(
                _suite_pin_value(CONCRETE_SUITE_PIN),
                coordinates={},
                owner_id="persona-v2-concrete-overlay-membership-suite",
                owner_role="full-suite-owner-pin",
            ),
            _owner_pin(
                origin_pin,
                coordinates=coordinates,
                owner_id=f"persona-v2-concrete-overlay-origin-{persona_id}-{origin}",
                owner_role="full-origin-owner-pin",
            ),
        ],
    }


def _cell_material():
    suite = _parameter_suite()
    catalog = parameters.build_source_parameter_cell_catalog()
    _require_true(
        parameters.validate_source_parameter_cell_catalog(catalog),
        label="source parameter cell catalog validator",
    )
    body = source_parameter_cell_content_projection_body_bytes()
    catalog_pin = _generic_pin(
        catalog,
        canonicalizer=parameters.canonical_json_bytes,
        maximum=parameters.MAX_CELL_CATALOG_BYTES,
    )
    binding = _find_one(
        suite["input_bindings"],
        label="parameter suite cell-catalog binding",
        predicate=lambda row: row.get("name")
        == "persona-v2-source-parameter-cell-catalog",
    )
    if (
        binding.get("canonical_bytes") != catalog_pin["canonical_bytes"]
        or binding.get("sha256") != catalog_pin["sha256"]
        or binding.get("artifact_schema") != catalog_pin["artifact_schema"]
    ):
        _fail("parameter suite-to-cell-catalog owner chain drifted")
    coordinates = {"parameter_catalog_id": "global-source-parameter-cells-v1"}
    return {
        "artifact_kind": CELL_KIND,
        "artifact_schema": CELL_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "bytes": body,
        "class_id": PARAMETER_CLASS_ID,
        "coordinates": coordinates,
        "direct_body_pins": [
            _direct_pin(
                _canonical(
                    binding,
                    label="parameter suite cell binding",
                    maximum=MAX_FRAGMENT_BYTES,
                ),
                direct_pin_id="parameter-suite-cell-catalog-binding",
                direct_pin_role="suite-cell-catalog-binding-row",
                framing="canonical-json",
            ),
            _direct_pin(
                _canonical(
                    catalog["orders"],
                    label="parameter cell order fragment",
                    maximum=MAX_FRAGMENT_BYTES,
                ),
                direct_pin_id="parameter-cell-orders-fragment",
                direct_pin_role="cell-catalog-content-order-fragment",
                framing="canonical-json",
            ),
            _direct_pin(
                _canonical(
                    catalog["parameter_cells"],
                    label="parameter cell definitions fragment",
                    maximum=MAX_FRAGMENT_BYTES,
                ),
                direct_pin_id="parameter-cell-definitions-fragment",
                direct_pin_role="cell-catalog-content-definitions-fragment",
                framing="canonical-json",
            ),
        ],
        "framing": "canonical-json",
        "full_owner_pins": [
            _owner_pin(
                _suite_pin_value(PARAMETER_SUITE_PIN),
                coordinates={},
                owner_id="persona-v2-source-parameter-assignment-suite",
                owner_role="full-suite-owner-pin",
            ),
            _owner_pin(
                catalog_pin,
                coordinates=coordinates,
                owner_id="persona-v2-source-parameter-cell-catalog",
                owner_role="full-cell-catalog-owner-pin",
            ),
        ],
    }


def _assignment_material(persona_id, origin, shard_ordinal):
    suite = _parameter_suite()
    origin_value = _parameter_origin(persona_id, origin)
    receipt = _find_one(
        origin_value["expanded_view_receipts"],
        label="parameter assignment expanded receipt",
        predicate=lambda row: row.get("shard_ordinal") == shard_ordinal,
    )
    body = source_parameter_assignment_projection_body_bytes(
        persona_id, origin, shard_ordinal
    )
    if (
        receipt["expanded_body_bytes"] != len(body)
        or receipt["expanded_body_sha256"] != _sha256(body)
    ):
        _fail("assignment body differs from its authenticated expanded receipt")
    binding = _find_one(
        suite["origin_manifest_bindings"],
        label="parameter suite origin binding",
        predicate=lambda row: row.get("persona_id") == persona_id
        and row.get("origin") == origin,
    )
    origin_pin = _generic_pin(
        origin_value,
        canonicalizer=parameters.canonical_json_bytes,
        maximum=parameters.MAX_ORIGIN_MANIFEST_BYTES,
    )
    if (
        binding.get("canonical_bytes") != origin_pin["canonical_bytes"]
        or binding.get("sha256") != origin_pin["sha256"]
        or binding.get("artifact_schema") != origin_pin["artifact_schema"]
    ):
        _fail("parameter suite-to-origin owner chain drifted")
    coordinates = {
        "origin": origin,
        "persona_id": persona_id,
        "source_shard_id": receipt["source_shard_id"],
        "source_shard_ordinal": shard_ordinal,
    }
    return {
        "artifact_kind": ASSIGNMENT_KIND,
        "artifact_schema": ASSIGNMENT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "bytes": body,
        "class_id": PARAMETER_CLASS_ID,
        "coordinates": coordinates,
        "direct_body_pins": [
            _direct_pin(
                _canonical(
                    binding,
                    label="parameter suite origin binding",
                    maximum=MAX_FRAGMENT_BYTES,
                ),
                direct_pin_id=f"parameter-suite-origin-binding-{persona_id}-{origin}",
                direct_pin_role="suite-origin-binding-row",
                framing="canonical-json",
            ),
            _direct_pin(
                _canonical(
                    receipt,
                    label="parameter assignment expanded receipt",
                    maximum=MAX_FRAGMENT_BYTES,
                ),
                direct_pin_id=(
                    f"parameter-expanded-receipt-{persona_id}-{origin}-"
                    f"{shard_ordinal:03d}"
                ),
                direct_pin_role="origin-expanded-assignment-receipt-row",
                framing="canonical-json",
            ),
        ],
        "framing": "canonical-jsonl-lf",
        "full_owner_pins": [
            _owner_pin(
                _suite_pin_value(PARAMETER_SUITE_PIN),
                coordinates={},
                owner_id="persona-v2-source-parameter-assignment-suite",
                owner_role="full-suite-owner-pin",
            ),
            _owner_pin(
                origin_pin,
                coordinates={"origin": origin, "persona_id": persona_id},
                owner_id=f"persona-v2-source-parameter-origin-{persona_id}-{origin}",
                owner_role="full-origin-owner-pin",
            ),
        ],
    }


def _detached_material(material):
    if type(material) is not dict or set(material) != MATERIAL_FIELDS:
        _fail("projection material field schema drifted")
    body = material["bytes"]
    metadata = {key: value for key, value in material.items() if key != "bytes"}
    raw = _canonical(
        metadata,
        label="relation/parameter projection material metadata",
        maximum=MAX_FRAGMENT_BYTES,
    )
    detached = _strict_load(raw, label="projection material metadata")
    detached["bytes"] = bytes(body)
    return detached


def iter_relations_parameter_projection_materials():
    """Yield 114 detached content bodies and their derivation evidence.

    Consumers should stream the iterator.  Material ``bytes`` are immutable;
    the pin dictionaries are deserialized afresh for each yield.
    """

    relation_count = 0
    relation_rows = 0
    for persona_id in envelope.PERSONA_IDS:
        for origin in concrete.ORIGIN_ORDER:
            material = _relation_material(persona_id, origin)
            relation_count += 1
            relation_rows += material["bytes"].count(b"\n")
            yield _detached_material(material)
    if (
        relation_count != EXPECTED_RELATION_BODY_COUNT
        or relation_rows != EXPECTED_RELATION_ROW_COUNT
    ):
        _fail("concrete relation projection aggregate drifted")

    yield _detached_material(_cell_material())
    assignment_count = 0
    assignment_rows = 0
    assignment_bytes = 0
    for persona_id in envelope.PERSONA_IDS:
        for origin in parameters.ORIGIN_ORDER:
            origin_value = _parameter_origin(persona_id, origin)
            for receipt in origin_value["expanded_view_receipts"]:
                material = _assignment_material(
                    persona_id, origin, receipt["shard_ordinal"]
                )
                assignment_count += 1
                assignment_rows += material["bytes"].count(b"\n")
                assignment_bytes += len(material["bytes"])
                yield _detached_material(material)
    if (
        assignment_count != EXPECTED_ASSIGNMENT_BODY_COUNT
        or assignment_rows != EXPECTED_ASSIGNMENT_ROW_COUNT
        or assignment_bytes != EXPECTED_ASSIGNMENT_BODY_BYTES
    ):
        _fail("source parameter assignment projection aggregate drifted")


def _require_coordinates(class_id, coordinates):
    if (
        type(class_id) is not str
        or len(class_id) > MAX_COORDINATE_KEY_CHARS
        or class_id not in CLASS_ORDER
    ):
        _fail("unknown relation/parameter projection class")
    if (
        type(coordinates) is not dict
        or len(coordinates) > MAX_COORDINATE_FIELD_COUNT
    ):
        _fail("projection coordinates must be an exact object")
    for key in coordinates:
        if type(key) is not str or len(key) > MAX_COORDINATE_KEY_CHARS:
            _fail("projection coordinate key violates its exact scalar cap")
    if class_id == RELATION_CLASS_ID:
        if (
            len(coordinates) != 2
            or "origin" not in coordinates
            or "persona_id" not in coordinates
        ):
            _fail("relation projection coordinate schema drifted")
        _require_persona(coordinates["persona_id"])
        _require_origin(coordinates["origin"])
        return "relation"
    if len(coordinates) == 1 and "parameter_catalog_id" in coordinates:
        if (
            type(coordinates["parameter_catalog_id"]) is not str
            or coordinates["parameter_catalog_id"]
            != "global-source-parameter-cells-v1"
        ):
            _fail("parameter catalog coordinate drifted")
        return "cell"
    if len(coordinates) != 4 or any(
        key not in coordinates
        for key in (
            "origin",
            "persona_id",
            "source_shard_id",
            "source_shard_ordinal",
        )
    ):
        _fail("parameter assignment coordinate schema drifted")
    _require_persona(coordinates["persona_id"])
    _require_origin(coordinates["origin"])
    if (
        type(coordinates["source_shard_id"]) is not str
        or not coordinates["source_shard_id"]
        or len(coordinates["source_shard_id"]) > MAX_COORDINATE_SCALAR_CHARS
        or len(coordinates["source_shard_id"].encode("utf-8"))
        > MAX_COORDINATE_SCALAR_BYTES
        or type(coordinates["source_shard_ordinal"]) is not int
        or type(coordinates["source_shard_ordinal"]) is bool
        or coordinates["source_shard_ordinal"] < 1
    ):
        _fail("parameter assignment shard coordinate is invalid")
    return "assignment"


def projection_body_bytes(class_id, coordinates):
    """Rebuild exactly one projection body from its logical coordinate."""

    kind = _require_coordinates(class_id, coordinates)
    if kind == "relation":
        return concrete_overlay_relations_projection_body_bytes(
            coordinates["persona_id"], coordinates["origin"]
        )
    if kind == "cell":
        return source_parameter_cell_content_projection_body_bytes()
    origin_value = _parameter_origin(
        coordinates["persona_id"], coordinates["origin"]
    )
    receipt = _find_one(
        origin_value["expanded_view_receipts"],
        label="parameter assignment dispatch receipt",
        predicate=lambda row: row.get("shard_ordinal")
        == coordinates["source_shard_ordinal"],
    )
    if receipt["source_shard_id"] != coordinates["source_shard_id"]:
        _fail("parameter assignment source_shard_id differs from its ordinal")
    return source_parameter_assignment_projection_body_bytes(
        coordinates["persona_id"],
        coordinates["origin"],
        coordinates["source_shard_ordinal"],
    )


def _independent_validator():
    try:
        from . import persona_v2_semantic_projection_relations_parameters_validator as independent
    except ImportError:  # pragma: no cover - direct-script compatibility
        try:
            import persona_v2_semantic_projection_relations_parameters_validator as independent
        except ImportError:
            independent = None
    return independent


def validate_projection_body(class_id, coordinates, body):
    """Validate one caller-owned body through the sibling-independent module."""

    if type(body) is not bytes:
        _fail("projection body must be exact built-in bytes")
    independent = _independent_validator()
    if independent is None:
        _fail("independent relation/parameter projection validator is unavailable")
    try:
        result = independent.validate_projection_body(class_id, coordinates, body)
    except independent.PersonaV2SemanticProjectionRelationsParametersValidationError as error:
        _fail(str(error))
    if result is not True:
        _fail("independent relation/parameter validator did not return exact True")
    return True


def projection_body_sha256(class_id, coordinates, body=None):
    if body is None:
        body = projection_body_bytes(class_id, coordinates)
    opening = bytes(body) if type(body) is bytes else body
    validate_projection_body(class_id, coordinates, opening)
    if type(body) is not bytes or not hmac.compare_digest(opening, body):
        _fail("caller-owned projection body changed while hashing")
    return _sha256(opening)


__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "ASSIGNMENT_KIND",
    "ASSIGNMENT_ROW_FIELDS",
    "ASSIGNMENT_SCHEMA",
    "CELL_FIELDS",
    "CELL_KIND",
    "CELL_PROJECTION_FIELDS",
    "CELL_SCHEMA",
    "CLASS_ORDER",
    "CONCRETE_SUITE_PIN",
    "DIRECT_BODY_PIN_FIELDS",
    "EXPECTED_ASSIGNMENT_BODY_BYTES",
    "EXPECTED_ASSIGNMENT_BODY_COUNT",
    "EXPECTED_ASSIGNMENT_ROW_COUNT",
    "EXPECTED_CELL_BODY_COUNT",
    "EXPECTED_CELL_COUNT",
    "EXPECTED_MATERIAL_COUNT",
    "EXPECTED_RELATION_BODY_COUNT",
    "EXPECTED_RELATION_ROW_COUNT",
    "FULL_OWNER_PIN_FIELDS",
    "GENERIC_PIN_FIELDS",
    "MATERIAL_FIELDS",
    "MAX_ASSIGNMENT_BODY_BYTES",
    "MAX_ASSIGNMENT_ROWS",
    "MAX_ASSIGNMENT_ROW_BYTES_INCLUDING_LF",
    "MAX_CELL_BODY_BYTES",
    "MAX_RELATION_BODY_BYTES",
    "MAX_RELATION_ROWS",
    "MAX_RELATION_ROW_BYTES_INCLUDING_LF",
    "PARAMETER_CLASS_ID",
    "PARAMETER_SUITE_PIN",
    "PersonaV2SemanticProjectionRelationsParametersError",
    "RELATION_ATTACHMENT_FIELDS",
    "RELATION_CLASS_ID",
    "RELATION_CONTENT_FIELDS",
    "RELATION_KIND",
    "RELATION_SCHEMA",
    "concrete_overlay_relations_projection_body_bytes",
    "iter_relations_parameter_projection_materials",
    "projection_body_bytes",
    "projection_body_sha256",
    "source_parameter_assignment_projection_body_bytes",
    "source_parameter_cell_content_projection_body_bytes",
    "validate_projection_body",
]
