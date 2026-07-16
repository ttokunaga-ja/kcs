"""Producer-independent validation for relation/parameter projections.

The sibling producer is intentionally not imported.  Expected bodies and
their owner/direct-fragment pins are reconstructed from the already frozen
concrete-overlay and source-parameter packages.  Public validation accepts
only exact built-in bytes, replays every provider twice, and re-authenticates
live owners after callbacks and at final postflight.
"""

from __future__ import annotations

import copy
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
    "kcs.persona.pc-concrete-overlay-relations-origin-projection/v1"
)
RELATION_KIND = "persona-pc-v2-concrete-overlay-relations-origin-projection"
CELL_SCHEMA = "kcs.persona.pc-source-parameter-cell-content-projection/v1"
CELL_KIND = "persona-pc-v2-source-parameter-cell-content-projection"
ASSIGNMENT_SCHEMA = (
    "kcs.persona.pc-source-instance-parameter-assignment-shard-projection/v1"
)
ASSIGNMENT_KIND = (
    "persona-pc-v2-source-instance-parameter-assignment-shard-projection"
)
ARTIFACT_SCHEMA_VERSION = 1

EXPECTED_RELATION_BODY_COUNT = 40
EXPECTED_RELATION_ROW_COUNT = 25_560
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
MAX_FULL_OWNER_PINS = 4
MAX_DIRECT_BODY_PINS = 4

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
    concrete_validator.SUITE_ARTIFACT_KIND,
    concrete_validator.SUITE_ARTIFACT_SCHEMA,
    concrete_validator.ARTIFACT_SCHEMA_VERSION,
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


class PersonaV2SemanticProjectionRelationsParametersValidationError(ValueError):
    """Raised when a relation/parameter content projection is invalid."""


def _fail(message):
    raise PersonaV2SemanticProjectionRelationsParametersValidationError(message)


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
    except PersonaV2SemanticProjectionRelationsParametersValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        _fail(f"{label} is not strict UTF-8 JSON: {error}")
    try:
        artifact_common.validate_plain_value(value, label=label)
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))
    return value


def _snapshot(value, *, label, maximum):
    raw = _canonical(value, label=label, maximum=maximum)
    snapshot = _strict_load(raw, label=label)
    if not hmac.compare_digest(
        raw,
        _canonical(snapshot, label=label, maximum=maximum),
    ):
        _fail(f"{label} opening image is not canonical")
    return snapshot, raw


def _reauth(value, opening, *, label, maximum):
    current = _canonical(value, label=label, maximum=maximum)
    if not hmac.compare_digest(opening, current):
        _fail(f"caller-owned {label} mutated during validation")


def _require_persona(persona_id):
    if type(persona_id) is not str or persona_id not in envelope.PERSONA_IDS:
        _fail("persona_id is outside the exact twenty-person suite")


def _require_origin(origin):
    if type(origin) is not str or origin not in concrete.ORIGIN_ORDER:
        _fail("origin must be pilot or full-residual")


def _require_true(result, *, label):
    if result is not True:
        _fail(f"{label} did not return exact True")


def _generic_pin(value, *, maximum):
    raw = _canonical(
        value,
        label="independently canonicalized full owner",
        maximum=maximum,
    )
    return {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "body_framing": "canonical-json",
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
    if type(rows) is not list:
        _fail(f"{label} owner rows must be a list")
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
        or type(descriptor.get("body_sha256")) is not str
        or not hmac.compare_digest(
            descriptor.get("body_sha256", ""), _sha256(rich_body)
        )
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


def _load_concrete_suite(*, validate=True):
    value = concrete.build_concrete_overlay_membership_suite_descriptor()
    if validate:
        try:
            result = concrete.validate_concrete_overlay_membership_suite_descriptor(
                value
            )
        except Exception as error:
            raise PersonaV2SemanticProjectionRelationsParametersValidationError(
                "concrete overlay suite validation failed"
            ) from error
        _require_true(result, label="concrete overlay suite validator")
    raw = _canonical(
        value,
        label="concrete overlay suite frozen owner",
        maximum=concrete.MAX_SUITE_DESCRIPTOR_BYTES,
    )
    if (
        len(raw) != CONCRETE_SUITE_PIN[4]
        or not hmac.compare_digest(_sha256(raw), CONCRETE_SUITE_PIN[5])
    ):
        _fail("concrete overlay suite frozen pin drifted")
    snapshot, _ = _snapshot(
        value,
        label="concrete overlay suite",
        maximum=concrete.MAX_SUITE_DESCRIPTOR_BYTES,
    )
    return snapshot


def _load_parameter_suite(*, validate=True):
    value = parameters.build_source_parameter_assignment_suite_descriptor()
    if validate:
        try:
            result = parameters.validate_source_parameter_assignment_suite_descriptor(
                value
            )
        except Exception as error:
            raise PersonaV2SemanticProjectionRelationsParametersValidationError(
                "source parameter suite validation failed"
            ) from error
        _require_true(result, label="source parameter suite validator")
    raw = _canonical(
        value,
        label="source parameter suite frozen owner",
        maximum=parameters.MAX_SUITE_BYTES,
    )
    if (
        len(raw) != PARAMETER_SUITE_PIN[4]
        or not hmac.compare_digest(_sha256(raw), PARAMETER_SUITE_PIN[5])
    ):
        _fail("source parameter suite frozen pin drifted")
    snapshot, _ = _snapshot(
        value,
        label="source parameter suite",
        maximum=parameters.MAX_SUITE_BYTES,
    )
    return snapshot


def _load_concrete_origin(persona_id, origin, *, validate=True):
    value = concrete.build_concrete_overlay_membership_origin_manifest(
        persona_id, origin
    )
    if validate:
        try:
            result = concrete.validate_concrete_overlay_membership_origin_manifest(
                persona_id, origin, value
            )
        except Exception as error:
            raise PersonaV2SemanticProjectionRelationsParametersValidationError(
                "concrete overlay origin validation failed"
            ) from error
        _require_true(result, label="concrete overlay origin validator")
    snapshot, _ = _snapshot(
        value,
        label="concrete overlay origin",
        maximum=concrete.MAX_ORIGIN_MANIFEST_BYTES,
    )
    return snapshot


def _load_parameter_origin(persona_id, origin, *, validate=True):
    value = parameters.build_source_parameter_assignment_origin_manifest(
        persona_id, origin
    )
    if validate:
        try:
            result = parameters.validate_source_parameter_assignment_origin_manifest(
                persona_id, origin, value
            )
        except Exception as error:
            raise PersonaV2SemanticProjectionRelationsParametersValidationError(
                "source parameter origin validation failed"
            ) from error
        _require_true(result, label="source parameter origin validator")
    snapshot, _ = _snapshot(
        value,
        label="source parameter origin",
        maximum=parameters.MAX_ORIGIN_MANIFEST_BYTES,
    )
    return snapshot


def _load_cell_catalog(*, validate=True):
    value = parameters.build_source_parameter_cell_catalog()
    if validate:
        try:
            result = parameters.validate_source_parameter_cell_catalog(value)
        except Exception as error:
            raise PersonaV2SemanticProjectionRelationsParametersValidationError(
                "source parameter cell catalog validation failed"
            ) from error
        _require_true(result, label="source parameter cell catalog validator")
    snapshot, _ = _snapshot(
        value,
        label="source parameter cell catalog",
        maximum=parameters.MAX_CELL_CATALOG_BYTES,
    )
    return snapshot


def _project_relation_row(row):
    if type(row) is not dict:
        _fail("concrete rich row must be an object")
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
    elif row.get("row_kind") == "semantic-anchor-membership":
        if set(row) != concrete.SEMANTIC_ANCHOR_ROW_FIELDS:
            _fail("concrete semantic-anchor owner row schema drifted")
        return None
    else:
        _fail("concrete origin contains an unknown rich row kind")
    if set(value) != expected:
        _fail("concrete relation projection row schema drifted")
    return value


def _relation_body(rich_body):
    if (
        type(rich_body) is not bytes
        or not rich_body
        or not rich_body.endswith(b"\n")
        or b"\r" in rich_body
        or len(rich_body) > concrete.MAX_SHARD_BODY_BYTES
    ):
        _fail("concrete rich owner body violates its JSONL framing/cap")
    parts = []
    framed_rows = rich_body.splitlines(keepends=True)
    if len(framed_rows) > concrete.MAX_ROWS_PER_SHARD:
        _fail("concrete rich owner body exceeds its row cap")
    for ordinal, framed in enumerate(framed_rows, start=1):
        if (
            not framed.endswith(b"\n")
            or len(framed) > concrete.MAX_ROW_BYTES_INCLUDING_LF
        ):
            _fail("concrete rich owner row violates its framing/cap")
        raw = framed[:-1]
        row = _strict_load(raw, label=f"concrete rich owner row {ordinal}")
        if not hmac.compare_digest(
            raw,
            _canonical(
                row,
                label="concrete rich owner row",
                maximum=concrete.MAX_ROW_BYTES_INCLUDING_LF - 1,
            ),
        ):
            _fail("concrete rich owner row is not canonical JSON")
        projected = _project_relation_row(row)
        if projected is None:
            continue
        raw = _canonical(
            projected,
            label="independent concrete relation projection row",
            maximum=MAX_RELATION_ROW_BYTES_INCLUDING_LF - 1,
        )
        parts.append(raw + b"\n")
    if not parts or len(parts) > MAX_RELATION_ROWS:
        _fail("concrete relation projection row count violates its cap")
    body = b"".join(parts)
    if len(body) > MAX_RELATION_BODY_BYTES:
        _fail("concrete relation projection body exceeds its cap")
    return body


def _cell_body(catalog):
    value = {
        "artifact_kind": CELL_KIND,
        "artifact_schema": CELL_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "orders": copy.deepcopy(catalog["orders"]),
        "parameter_cells": copy.deepcopy(catalog["parameter_cells"]),
    }
    if (
        set(value) != CELL_PROJECTION_FIELDS
        or len(value["parameter_cells"]) != EXPECTED_CELL_COUNT
        or any(set(row) != CELL_FIELDS for row in value["parameter_cells"])
    ):
        _fail("source parameter cell content projection drifted")
    return _canonical(
        value,
        label="independent source parameter cell content projection",
        maximum=MAX_CELL_BODY_BYTES,
    )


def _assignment_body(persona_id, origin, shard_ordinal):
    try:
        body = parameters.source_parameter_assignment_expanded_view_body_bytes(
            persona_id, origin, shard_ordinal
        )
    except Exception as error:
        raise PersonaV2SemanticProjectionRelationsParametersValidationError(
            "source parameter assignment body reconstruction failed"
        ) from error
    if type(body) is not bytes or not body or len(body) > MAX_ASSIGNMENT_BODY_BYTES:
        _fail("source parameter assignment body violates its cap")
    return body


def _pin_material_metadata(material):
    body = material["bytes"]
    metadata = {key: value for key, value in material.items() if key != "bytes"}
    raw = _canonical(
        metadata,
        label="independent projection material metadata",
        maximum=MAX_FRAGMENT_BYTES,
    )
    return raw, bytes(body)


def _detach_material(metadata_raw, body):
    value = _strict_load(metadata_raw, label="projection material metadata")
    value["bytes"] = bytes(body)
    if set(value) != MATERIAL_FIELDS:
        _fail("projection material field schema drifted")
    return value


def _relation_material(
    persona_id,
    origin,
    *,
    concrete_suite=None,
    origin_value=None,
    validate_owners=True,
):
    _require_persona(persona_id)
    _require_origin(origin)
    suite = (
        _load_concrete_suite(validate=validate_owners)
        if concrete_suite is None
        else concrete_suite
    )
    origin_value = (
        _load_concrete_origin(persona_id, origin, validate=validate_owners)
        if origin_value is None
        else origin_value
    )
    rich = concrete.concrete_overlay_membership_shard_body_bytes(
        persona_id, origin, 0
    )
    _require_rich_body_descriptor(
        origin_value, rich, persona_id=persona_id, origin=origin
    )
    body = _relation_body(rich)
    draft = origin_value["draft_membership_projection_receipt"]
    if (
        draft["body_bytes"] != len(body)
        or not hmac.compare_digest(draft["body_sha256"], _sha256(body))
    ):
        _fail("relation body differs from its authenticated draft receipt")
    binding = _find_one(
        suite["origin_manifest_bindings"],
        label="concrete suite origin binding",
        predicate=lambda row: row.get("persona_id") == persona_id
        and row.get("origin") == origin,
    )
    origin_pin = _generic_pin(
        origin_value,
        maximum=concrete.MAX_ORIGIN_MANIFEST_BYTES,
    )
    if (
        binding.get("canonical_bytes") != origin_pin["canonical_bytes"]
        or binding.get("sha256") != origin_pin["sha256"]
        or binding.get("artifact_schema") != origin_pin["artifact_schema"]
    ):
        _fail("concrete suite-to-origin owner chain drifted")
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


def _cell_material(
    *, parameter_suite=None, catalog=None, validate_owners=True
):
    suite = (
        _load_parameter_suite(validate=validate_owners)
        if parameter_suite is None
        else parameter_suite
    )
    catalog = (
        _load_cell_catalog(validate=validate_owners)
        if catalog is None
        else catalog
    )
    body = _cell_body(catalog)
    catalog_pin = _generic_pin(
        catalog,
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


def _assignment_material(
    persona_id,
    origin,
    shard_ordinal,
    *,
    parameter_suite=None,
    origin_value=None,
    validate_owners=True,
):
    _require_persona(persona_id)
    _require_origin(origin)
    suite = (
        _load_parameter_suite(validate=validate_owners)
        if parameter_suite is None
        else parameter_suite
    )
    origin_value = (
        _load_parameter_origin(persona_id, origin, validate=validate_owners)
        if origin_value is None
        else origin_value
    )
    receipt = _find_one(
        origin_value["expanded_view_receipts"],
        label="parameter assignment expanded receipt",
        predicate=lambda row: row.get("shard_ordinal") == shard_ordinal,
    )
    body = _assignment_body(persona_id, origin, shard_ordinal)
    if (
        receipt["expanded_body_bytes"] != len(body)
        or not hmac.compare_digest(
            receipt["expanded_body_sha256"], _sha256(body)
        )
    ):
        _fail("assignment body differs from its expanded receipt")
    binding = _find_one(
        suite["origin_manifest_bindings"],
        label="parameter suite origin binding",
        predicate=lambda row: row.get("persona_id") == persona_id
        and row.get("origin") == origin,
    )
    origin_pin = _generic_pin(
        origin_value,
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


def _coordinate_key(class_id, coordinates):
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
        _fail("projection coordinates must be an object")
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
        return (class_id, coordinates["persona_id"], coordinates["origin"])
    if len(coordinates) == 1 and "parameter_catalog_id" in coordinates:
        if (
            type(coordinates["parameter_catalog_id"]) is not str
            or coordinates["parameter_catalog_id"]
            != "global-source-parameter-cells-v1"
        ):
            _fail("parameter catalog coordinate drifted")
        return (class_id, "cell-catalog")
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
    return (
        class_id,
        coordinates["persona_id"],
        coordinates["origin"],
        coordinates["source_shard_ordinal"],
        coordinates["source_shard_id"],
    )


def _build_material_for_coordinate(class_id, coordinates, *, validate_owners=True):
    key = _coordinate_key(class_id, coordinates)
    if key[0] == RELATION_CLASS_ID:
        return _relation_material(
            key[1], key[2], validate_owners=validate_owners
        )
    if key == (PARAMETER_CLASS_ID, "cell-catalog"):
        return _cell_material(validate_owners=validate_owners)
    material = _assignment_material(
        key[1], key[2], key[3], validate_owners=validate_owners
    )
    if material["coordinates"]["source_shard_id"] != key[4]:
        _fail("source_shard_id differs from its authenticated ordinal")
    return material


def _body_cap_for_key(key):
    if key[0] == RELATION_CLASS_ID:
        return MAX_RELATION_BODY_BYTES
    if key == (PARAMETER_CLASS_ID, "cell-catalog"):
        return MAX_CELL_BODY_BYTES
    return MAX_ASSIGNMENT_BODY_BYTES


_EXPECTED_MATERIAL_RAW_CACHE = {}
_EXPECTED_COORDINATE_KEYS = None


def _coordinates_from_key(key):
    class_id = key[0]
    if class_id == RELATION_CLASS_ID:
        return {"persona_id": key[1], "origin": key[2]}
    if key == (PARAMETER_CLASS_ID, "cell-catalog"):
        return {"parameter_catalog_id": "global-source-parameter-cells-v1"}
    return {
            "persona_id": key[1],
            "origin": key[2],
            "source_shard_ordinal": key[3],
            "source_shard_id": key[4],
        }


def _remember_expected_material(material):
    key = _coordinate_key(material["class_id"], material["coordinates"])
    metadata_raw, body = _pin_material_metadata(material)
    candidate = (bytes(metadata_raw), bytes(body))
    current = _EXPECTED_MATERIAL_RAW_CACHE.get(key)
    if current is not None:
        if not (
            hmac.compare_digest(current[0], candidate[0])
            and hmac.compare_digest(current[1], candidate[1])
        ):
            _fail("independent reconstruction differs from immutable opening cache")
        return current
    if len(_EXPECTED_MATERIAL_RAW_CACHE) >= EXPECTED_MATERIAL_COUNT:
        _fail("immutable expected-material cache exceeded its exact bound")
    _EXPECTED_MATERIAL_RAW_CACHE[key] = candidate
    return candidate


def _expected_material_raw(key):
    current = _EXPECTED_MATERIAL_RAW_CACHE.get(key)
    if current is not None:
        return current
    coordinates = _coordinates_from_key(key)
    material = _build_material_for_coordinate(key[0], coordinates)
    return _remember_expected_material(material)


def _expected_material(class_id, coordinates):
    key = _coordinate_key(class_id, coordinates)
    metadata_raw, body = _expected_material_raw(key)
    return _detach_material(metadata_raw, body)


def iter_expected_relations_parameter_projection_materials():
    """Yield the independently reconstructed exact 114 material stream."""

    global _EXPECTED_COORDINATE_KEYS
    if _EXPECTED_COORDINATE_KEYS is not None:
        for key in _EXPECTED_COORDINATE_KEYS:
            metadata_raw, body = _expected_material_raw(key)
            yield _detach_material(metadata_raw, body)
        return

    coordinate_keys = []
    concrete_suite = _load_concrete_suite()
    relation_count = 0
    relation_rows = 0
    for persona_id in envelope.PERSONA_IDS:
        for origin in concrete.ORIGIN_ORDER:
            origin_value = _load_concrete_origin(persona_id, origin)
            material = _relation_material(
                persona_id,
                origin,
                concrete_suite=concrete_suite,
                origin_value=origin_value,
            )
            key = _coordinate_key(material["class_id"], material["coordinates"])
            metadata_raw, body = _remember_expected_material(material)
            coordinate_keys.append(key)
            relation_count += 1
            relation_rows += body.count(b"\n")
            yield _detach_material(metadata_raw, body)
    if (
        relation_count != EXPECTED_RELATION_BODY_COUNT
        or relation_rows != EXPECTED_RELATION_ROW_COUNT
    ):
        _fail("independent concrete relation aggregate drifted")

    parameter_suite = _load_parameter_suite()
    catalog = _load_cell_catalog()
    cell = _cell_material(parameter_suite=parameter_suite, catalog=catalog)
    cell_key = _coordinate_key(cell["class_id"], cell["coordinates"])
    cell_raw, cell_body = _remember_expected_material(cell)
    coordinate_keys.append(cell_key)
    yield _detach_material(cell_raw, cell_body)

    assignment_count = 0
    assignment_rows = 0
    assignment_bytes = 0
    for persona_id in envelope.PERSONA_IDS:
        for origin in parameters.ORIGIN_ORDER:
            origin_value = _load_parameter_origin(persona_id, origin)
            for receipt in origin_value["expanded_view_receipts"]:
                material = _assignment_material(
                    persona_id,
                    origin,
                    receipt["shard_ordinal"],
                    parameter_suite=parameter_suite,
                    origin_value=origin_value,
                )
                key = _coordinate_key(
                    material["class_id"], material["coordinates"]
                )
                metadata_raw, body = _remember_expected_material(material)
                coordinate_keys.append(key)
                assignment_count += 1
                assignment_rows += body.count(b"\n")
                assignment_bytes += len(body)
                yield _detach_material(metadata_raw, body)
    if (
        assignment_count != EXPECTED_ASSIGNMENT_BODY_COUNT
        or assignment_rows != EXPECTED_ASSIGNMENT_ROW_COUNT
        or assignment_bytes != EXPECTED_ASSIGNMENT_BODY_BYTES
    ):
        _fail("independent source parameter aggregate drifted")
    if (
        len(coordinate_keys) != EXPECTED_MATERIAL_COUNT
        or len(set(coordinate_keys)) != EXPECTED_MATERIAL_COUNT
        or len(_EXPECTED_MATERIAL_RAW_CACHE) != EXPECTED_MATERIAL_COUNT
    ):
        _fail("independent projection coordinate/cache cardinality drifted")
    _EXPECTED_COORDINATE_KEYS = tuple(coordinate_keys)


def _parse_jsonl(body, *, fields_by_kind, maximum_rows, maximum_row, label):
    if type(body) is not bytes or not body or not body.endswith(b"\n") or b"\r" in body:
        _fail(f"{label} must be nonempty LF-framed JSONL")
    framed_rows = body.splitlines(keepends=True)
    if len(framed_rows) > maximum_rows:
        _fail(f"{label} exceeds its row cap")
    rows = []
    for ordinal, framed in enumerate(framed_rows, start=1):
        if not framed.endswith(b"\n") or len(framed) > maximum_row:
            _fail(f"{label} row framing/cap drifted")
        raw = framed[:-1]
        row = _strict_load(raw, label=f"{label} row {ordinal}")
        if type(row) is not dict:
            _fail(f"{label} row must be an object")
        row_kind = row.get("row_kind")
        expected = fields_by_kind.get(row_kind)
        if expected is None or set(row) != expected:
            _fail(f"{label} row schema drifted")
        if not hmac.compare_digest(
            raw,
            _canonical(row, label=f"{label} row", maximum=maximum_row - 1),
        ):
            _fail(f"{label} row is not canonical JSON")
        rows.append(row)
    return rows


def _validate_body_semantics(material, body):
    if type(body) is not bytes:
        _fail("projection body must be exact built-in bytes")
    cap = {
        RELATION_SCHEMA: MAX_RELATION_BODY_BYTES,
        CELL_SCHEMA: MAX_CELL_BODY_BYTES,
        ASSIGNMENT_SCHEMA: MAX_ASSIGNMENT_BODY_BYTES,
    }.get(material.get("artifact_schema"))
    if cap is None or not body or len(body) > cap:
        _fail("projection body violates its class byte cap")
    expected = material["bytes"]
    if (
        len(body) != len(expected)
        or not hmac.compare_digest(_sha256(body), _sha256(expected))
        or not hmac.compare_digest(body, expected)
    ):
        _fail("projection body differs from independent reconstruction")
    schema = material["artifact_schema"]
    if schema == RELATION_SCHEMA:
        rows = _parse_jsonl(
            body,
            fields_by_kind={
                "content-relation": RELATION_CONTENT_FIELDS,
                "attachment-membership": RELATION_ATTACHMENT_FIELDS,
            },
            maximum_rows=MAX_RELATION_ROWS,
            maximum_row=MAX_RELATION_ROW_BYTES_INCLUDING_LF,
            label="concrete relation projection",
        )
        if any(
            "payload_seed_rule" in row
            or "source_or_shared_payload_seed_rule" in row
            for row in rows
        ):
            _fail("relation projection leaked payload-rule-owned fields")
    elif schema == CELL_SCHEMA:
        value = _strict_load(body, label="source parameter cell projection")
        if (
            type(value) is not dict
            or set(value) != CELL_PROJECTION_FIELDS
            or len(value["parameter_cells"]) != EXPECTED_CELL_COUNT
            or any(set(row) != CELL_FIELDS for row in value["parameter_cells"])
            or not hmac.compare_digest(
                body,
                _canonical(
                    value,
                    label="source parameter cell projection",
                    maximum=MAX_CELL_BODY_BYTES,
                ),
            )
        ):
            _fail("source parameter cell projection schema/canonical form drifted")
    elif schema == ASSIGNMENT_SCHEMA:
        _parse_jsonl(
            body,
            fields_by_kind={None: ASSIGNMENT_ROW_FIELDS},
            maximum_rows=MAX_ASSIGNMENT_ROWS,
            maximum_row=MAX_ASSIGNMENT_ROW_BYTES_INCLUDING_LF,
            label="source parameter assignment projection",
        )
    else:
        _fail("unknown projection body schema")


def _live_material(class_id, coordinates):
    material = _build_material_for_coordinate(
        class_id, coordinates, validate_owners=False
    )
    return _pin_material_metadata(material)


def _compare_live_material(material):
    key = _coordinate_key(material["class_id"], material["coordinates"])
    expected_metadata, expected_body = _expected_material_raw(key)
    live_metadata, live_body = _pin_material_metadata(material)
    if not (
        hmac.compare_digest(expected_metadata, live_metadata)
        and hmac.compare_digest(expected_body, live_body)
    ):
        _fail("projection full owner or direct fragment changed during validation")


def _reauthenticate_material_owners(class_id, coordinates):
    key = _coordinate_key(class_id, coordinates)
    expected_metadata, expected_body = _expected_material_raw(key)
    live_metadata, live_body = _live_material(class_id, coordinates)
    if not (
        hmac.compare_digest(expected_metadata, live_metadata)
        and hmac.compare_digest(expected_body, live_body)
    ):
        _fail("projection full owner or direct fragment changed during validation")


def validate_projection_body(class_id, coordinates, body):
    """Validate one body and re-read its live full/direct owners."""

    if type(body) is not bytes:
        _fail("projection body must be exact built-in bytes")
    opening_key = _coordinate_key(class_id, coordinates)
    if not body or len(body) > _body_cap_for_key(opening_key):
        _fail("projection body violates its class byte cap")
    coordinate_snapshot, coordinate_raw = _snapshot(
        coordinates,
        label="projection coordinates",
        maximum=MAX_COORDINATE_BYTES,
    )
    material = _expected_material(class_id, coordinate_snapshot)
    try:
        _reauthenticate_material_owners(class_id, coordinate_snapshot)
        _validate_body_semantics(material, body)
    finally:
        try:
            _reauthenticate_material_owners(class_id, coordinate_snapshot)
        finally:
            _reauth(
                coordinates,
                coordinate_raw,
                label="projection coordinates",
                maximum=MAX_COORDINATE_BYTES,
            )
    return True


def _default_projection_body_provider(class_id, coordinates):
    return bytes(_expected_material(class_id, coordinates)["bytes"])


def _call_provider(provider, class_id, coordinates, *, replay):
    key = _coordinate_key(class_id, coordinates)
    cap = _body_cap_for_key(key)
    detached, coordinate_raw = _snapshot(
        coordinates,
        label="projection provider coordinates",
        maximum=MAX_COORDINATE_BYTES,
    )
    try:
        try:
            body = provider(class_id, detached)
        except Exception as error:
            raise PersonaV2SemanticProjectionRelationsParametersValidationError(
                "projection provider failed" + (" during replay" if replay else "")
            ) from error
    finally:
        _reauth(
            coordinates,
            coordinate_raw,
            label="projection provider coordinates",
            maximum=MAX_COORDINATE_BYTES,
        )
    if type(body) is not bytes:
        _fail("projection provider must return exact built-in bytes")
    if not body or len(body) > cap:
        _fail("projection provider result exceeds its pre-compare cap")
    material = _expected_material(class_id, coordinates)
    expected = material["bytes"]
    if len(body) != len(expected) or not hmac.compare_digest(
        _sha256(body), _sha256(expected)
    ):
        _fail("projection provider result differs from its authenticated pin")
    return body


def _preflight_generic_coordinates(value, *, label):
    if type(value) is not dict or len(value) > MAX_COORDINATE_FIELD_COUNT:
        _fail(f"{label} coordinates violate their field cap")
    for key, item in value.items():
        if type(key) is not str or len(key) > MAX_COORDINATE_KEY_CHARS:
            _fail(f"{label} coordinate key violates its scalar cap")
        if type(item) is str:
            if (
                not item
                or len(item) > MAX_COORDINATE_SCALAR_CHARS
                or len(item.encode("utf-8")) > MAX_COORDINATE_SCALAR_BYTES
            ):
                _fail(f"{label} coordinate string violates its scalar cap")
        elif type(item) is int:
            if item < 0:
                _fail(f"{label} coordinate integer is negative")
        else:
            _fail(f"{label} coordinate scalar has an invalid exact type")


def _preflight_pin(pin, *, owner):
    fields = FULL_OWNER_PIN_FIELDS if owner else DIRECT_BODY_PIN_FIELDS
    label = "full-owner pin" if owner else "direct-body pin"
    if type(pin) is not dict or len(pin) != len(fields):
        _fail(f"{label} violates its exact field count")
    for key in pin:
        if type(key) is not str or len(key) > MAX_COORDINATE_KEY_CHARS:
            _fail(f"{label} key violates its exact scalar cap")
    if any(key not in pin for key in fields):
        _fail(f"{label} field schema drifted")
    if (
        type(pin["body_framing"]) is not str
        or pin["body_framing"] not in {"canonical-json", "canonical-jsonl-lf"}
        or type(pin["canonical_bytes"]) is not int
        or type(pin["canonical_bytes"]) is bool
        or not 0 < pin["canonical_bytes"] <= MAX_FRAGMENT_BYTES
        or type(pin["sha256"]) is not str
        or len(pin["sha256"]) != 64
        or any(character not in "0123456789abcdef" for character in pin["sha256"])
    ):
        _fail(f"{label} framing/size/digest is invalid")
    if owner:
        for field in (
            "artifact_kind",
            "artifact_schema",
            "owner_id",
            "owner_role",
        ):
            if (
                type(pin[field]) is not str
                or not pin[field]
                or len(pin[field]) > MAX_COORDINATE_SCALAR_CHARS
            ):
                _fail(f"{label} identity violates its scalar cap")
        if (
            type(pin["artifact_schema_version"]) is not int
            or type(pin["artifact_schema_version"]) is bool
            or pin["artifact_schema_version"] != ARTIFACT_SCHEMA_VERSION
        ):
            _fail(f"{label} schema version drifted")
        _preflight_generic_coordinates(pin["coordinates"], label=label)
    else:
        for field in ("direct_pin_id", "direct_pin_role"):
            if (
                type(pin[field]) is not str
                or not pin[field]
                or len(pin[field]) > MAX_COORDINATE_SCALAR_CHARS
            ):
                _fail(f"{label} identity violates its scalar cap")


def _snapshot_expected_material(material):
    if type(material) is not dict or len(material) != len(MATERIAL_FIELDS):
        _fail("independent expected material violates its exact field count")
    for key in material:
        if type(key) is not str or len(key) > MAX_COORDINATE_KEY_CHARS:
            _fail("independent expected material key violates its scalar cap")
    if any(key not in material for key in MATERIAL_FIELDS):
        _fail("independent expected material field schema drifted")
    key = _coordinate_key(material["class_id"], material["coordinates"])
    body = material["bytes"]
    if (
        type(body) is not bytes
        or not body
        or len(body) > _body_cap_for_key(key)
    ):
        _fail("independent expected material body violates its class cap")
    for field in ("artifact_kind", "artifact_schema", "framing"):
        if (
            type(material[field]) is not str
            or not material[field]
            or len(material[field]) > MAX_COORDINATE_SCALAR_CHARS
        ):
            _fail("independent expected material identity violates its cap")
    if (
        type(material["artifact_schema_version"]) is not int
        or type(material["artifact_schema_version"]) is bool
        or material["artifact_schema_version"] != ARTIFACT_SCHEMA_VERSION
    ):
        _fail("independent expected material schema version drifted")
    owners = material["full_owner_pins"]
    direct = material["direct_body_pins"]
    if (
        type(owners) is not list
        or not owners
        or len(owners) > MAX_FULL_OWNER_PINS
        or type(direct) is not list
        or not direct
        or len(direct) > MAX_DIRECT_BODY_PINS
    ):
        _fail("independent expected material pin cardinality is invalid")
    for pin in owners:
        _preflight_pin(pin, owner=True)
    for pin in direct:
        _preflight_pin(pin, owner=False)
    metadata = {name: value for name, value in material.items() if name != "bytes"}
    candidate_raw = _canonical(
        metadata,
        label="independent expected material opening metadata",
        maximum=MAX_FRAGMENT_BYTES,
    )
    expected_raw, expected_body = _expected_material_raw(key)
    if not (
        hmac.compare_digest(candidate_raw, expected_raw)
        and hmac.compare_digest(body, expected_body)
    ):
        _fail("independent expected material differs from its immutable cache")
    return _detach_material(expected_raw, expected_body), key


def _open_expected_materials():
    try:
        iterator = iter(iter_expected_relations_parameter_projection_materials())
    except Exception as error:
        raise PersonaV2SemanticProjectionRelationsParametersValidationError(
            "independent expected material iterator failed"
        ) from error
    materials = []
    keys = []
    for index in range(EXPECTED_MATERIAL_COUNT + 1):
        try:
            material = next(iterator)
        except StopIteration:
            break
        if index == EXPECTED_MATERIAL_COUNT:
            _fail("independent expected material iterator exceeded its exact cap")
        snapshot, key = _snapshot_expected_material(material)
        materials.append(snapshot)
        keys.append(key)
    if len(materials) != EXPECTED_MATERIAL_COUNT:
        _fail("independent expected material iterator cardinality drifted")
    if (
        _EXPECTED_COORDINATE_KEYS is None
        or tuple(keys) != _EXPECTED_COORDINATE_KEYS
        or len(set(keys)) != EXPECTED_MATERIAL_COUNT
    ):
        _fail("independent expected material order/uniqueness drifted")
    return materials


def validate_all_relations_parameter_projection_bodies(
    projection_body_provider=None,
):
    """Replay every one of the 114 bodies twice under live-owner checks."""

    provider = (
        _default_projection_body_provider
        if projection_body_provider is None
        else projection_body_provider
    )
    if not callable(provider):
        _fail("projection body provider must be callable")
    materials = _open_expected_materials()
    material_count = 0
    try:
        if reauthenticate_all_projection_owners() is not True:
            _fail("projection owner opening reauthentication did not return exact True")
        for material in materials:
            class_id = material["class_id"]
            coordinates = material["coordinates"]
            try:
                first = _call_provider(
                    provider, class_id, coordinates, replay=False
                )
            finally:
                _reauthenticate_material_owners(class_id, coordinates)
            _validate_body_semantics(material, first)
            try:
                replay = _call_provider(
                    provider, class_id, coordinates, replay=True
                )
            finally:
                _reauthenticate_material_owners(class_id, coordinates)
            _validate_body_semantics(material, replay)
            if not hmac.compare_digest(first, replay):
                _fail("projection body provider replay is nondeterministic")
            material_count += 1
    finally:
        if reauthenticate_all_projection_owners() is not True:
            _fail("projection owner final postflight did not return exact True")
    if material_count != EXPECTED_MATERIAL_COUNT:
        _fail("projection material cardinality drifted")
    return True


def reauthenticate_all_projection_owners():
    """Re-read deduplicated full owners and every direct fragment once."""

    if _EXPECTED_COORDINATE_KEYS is None:
        expected = list(iter_expected_relations_parameter_projection_materials())
        if len(expected) != EXPECTED_MATERIAL_COUNT:
            _fail("projection opening owner cardinality drifted")

    count = 0
    concrete_suite = _load_concrete_suite(validate=False)
    for persona_id in envelope.PERSONA_IDS:
        for origin in concrete.ORIGIN_ORDER:
            origin_value = _load_concrete_origin(
                persona_id, origin, validate=False
            )
            _compare_live_material(
                _relation_material(
                    persona_id,
                    origin,
                    concrete_suite=concrete_suite,
                    origin_value=origin_value,
                    validate_owners=False,
                )
            )
            count += 1

    parameter_suite = _load_parameter_suite(validate=False)
    catalog = _load_cell_catalog(validate=False)
    _compare_live_material(
        _cell_material(
            parameter_suite=parameter_suite,
            catalog=catalog,
            validate_owners=False,
        )
    )
    count += 1
    for persona_id in envelope.PERSONA_IDS:
        for origin in parameters.ORIGIN_ORDER:
            origin_value = _load_parameter_origin(
                persona_id, origin, validate=False
            )
            for receipt in origin_value["expanded_view_receipts"]:
                _compare_live_material(
                    _assignment_material(
                        persona_id,
                        origin,
                        receipt["shard_ordinal"],
                        parameter_suite=parameter_suite,
                        origin_value=origin_value,
                        validate_owners=False,
                    )
                )
                count += 1
    if count != EXPECTED_MATERIAL_COUNT:
        _fail("projection owner postflight cardinality drifted")
    return True


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
    "DIRECT_BODY_PIN_FIELDS",
    "EXPECTED_ASSIGNMENT_BODY_BYTES",
    "EXPECTED_ASSIGNMENT_BODY_COUNT",
    "EXPECTED_ASSIGNMENT_ROW_COUNT",
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
    "PersonaV2SemanticProjectionRelationsParametersValidationError",
    "RELATION_ATTACHMENT_FIELDS",
    "RELATION_CLASS_ID",
    "RELATION_CONTENT_FIELDS",
    "RELATION_KIND",
    "RELATION_SCHEMA",
    "iter_expected_relations_parameter_projection_materials",
    "reauthenticate_all_projection_owners",
    "validate_all_relations_parameter_projection_bodies",
    "validate_projection_body",
]
