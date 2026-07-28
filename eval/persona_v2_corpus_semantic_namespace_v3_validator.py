"""Producer-independent validator for the additive v3 pin-only namespace.

This module never imports the v3 producer.  Its trust source is the frozen
complete-inventory descriptor plus the existing producer-independent complete
inventory validator, including its two-call-per-body replay and owner checks.
"""

from __future__ import annotations

import functools
import hashlib
import hmac
import json

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import (
        persona_v2_semantic_projection_complete_inventory_validator as complete_validator,
    )
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_semantic_projection_complete_inventory_validator as complete_validator


ARTIFACT_SCHEMA_VERSION = 3
NAMESPACE_SCHEMA = "kio.persona.pc-corpus-semantic-namespace/v3"
NAMESPACE_KIND = "persona-pc-v2-projection-pin-corpus-semantic-namespace"
FIXTURE_ID = "kio-persona-pc-v2"
FIXTURE_SCHEMA_VERSION = 2

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
EXPECTED_ENTRY_COUNTS = {
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
PERSONA_IDS = tuple(f"p{ordinal:02d}" for ordinal in range(1, 21))
ORIGIN_ORDER = ("pilot", "full-residual")

MAX_MANIFEST_BYTES = 1 * 2**20
TARGET_MANIFEST_BYTES = 512 * 2**10
MAX_PROJECTION_ENTRY_COUNT = 253
MAX_PROJECTION_CLASS_COUNT = 12
MAX_COORDINATE_FIELDS = 4
MAX_IDENTITY_STRING_BYTES = 4 * 2**10
MAX_CUMULATIVE_EXTERNAL_PROJECTION_BYTES = 256 * 2**20
EXPECTED_CUMULATIVE_EXTERNAL_PROJECTION_BYTES = 155_741_475
MAX_JSON_PROJECTION_BYTES = 384 * 2**10
MAX_JSONL_PROJECTION_BYTES = 4 * 2**20
EXPECTED_JSON_PROJECTION_COUNT = 67
EXPECTED_JSONL_PROJECTION_COUNT = 186

# Independently frozen after the final body shape reproduced under two isolated
# all-253 builds with distinct Python hash seeds.
EXPECTED_NAMESPACE_CANONICAL_BYTES = 161_665
EXPECTED_NAMESPACE_SHA256 = (
    "a8bc67e182ff57b64ae6df0f97bd5be31faf6e5f7b7cfbd0bc3f1ba7bc5cc509"
)

COMPLETE_INVENTORY_CANONICAL_BYTES = 697_466
COMPLETE_INVENTORY_SHA256 = (
    "820c976a930c3f2ed0a54e44c08b01cad8a0879513f1b06012e353fb9bd3fd91"
)
COMPLETE_INVENTORY_SCHEMA = (
    "kio.persona.pc-semantic-projection-derivation-inventory/v2"
)
COMPLETE_INVENTORY_KIND = (
    "persona-pc-v2-complete-semantic-projection-derivation-inventory"
)
MAX_COMPLETE_INVENTORY_BYTES = 2 * 2**20

EXPECTED_PROJECTION_IDENTITIES = {
    "topology-path-load": (
        "persona-pc-v2-topology-path-load-content-projection",
        "kio.persona.pc-topology-path-load-content-projection/v1",
    ),
    "realism-locale-security": (
        "persona-pc-v2-realism-locale-security-content-projection",
        "kio.persona.pc-realism-locale-security-content-projection/v1",
    ),
    "route-scores": (
        "persona-pc-v2-route-scores-content-projection",
        "kio.persona.pc-route-scores-content-projection/v1",
    ),
    "primary-use-case-corpus-half": (
        "persona-pc-v2-primary-use-case-corpus-content-projection",
        "kio.persona.pc-primary-use-case-corpus-content-projection/v1",
    ),
    "recipe-content-filename-policy": (
        "persona-pc-v2-recipe-content-filename-policy-content-projection",
        "kio.persona.pc-recipe-content-filename-policy-content-projection/v1",
    ),
    "fact-graph": (
        "persona-pc-v2-fact-graph-content-projection",
        "kio.persona.pc-fact-graph-content-projection/v1",
    ),
    "base-source-content-context": (
        "persona-pc-v2-base-source-content-context-shard-projection",
        "kio.persona.pc-base-source-content-context-shard-projection/v1",
    ),
    "effective-source-membership": (
        "persona-pc-v2-lifecycle-effective-membership-content-projection",
        "kio.persona.pc-lifecycle-effective-membership-content-projection/v1",
    ),
    "concrete-overlay-relations": (
        "persona-pc-v2-concrete-overlay-relations-origin-projection",
        "kio.persona.pc-concrete-overlay-relations-origin-projection/v1",
    ),
    "query-independent-lifecycle-fact-rendition-rules": (
        "persona-pc-v2-source-matched-lifecycle-content-projection",
        "kio.persona.pc-source-matched-lifecycle-content-projection/v1",
    ),
    "payload-equivalence-rules": (
        "persona-pc-v2-payload-equivalence-rules-projection",
        "kio.persona.pc-payload-equivalence-rules-projection/v1",
    ),
}
PARAMETER_CELL_IDENTITY = (
    "persona-pc-v2-source-parameter-cell-content-projection",
    "kio.persona.pc-source-parameter-cell-content-projection/v1",
)
PARAMETER_ASSIGNMENT_IDENTITY = (
    "persona-pc-v2-source-instance-parameter-assignment-shard-projection",
    "kio.persona.pc-source-instance-parameter-assignment-shard-projection/v1",
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
ENTRY_FIELDS = frozenset(
    {
        "coordinates",
        "namespace_ordinal",
        "projection_class_id",
        "projection_pin",
    }
)
EDGE_FIELDS = frozenset({"from_node_id", "to_namespace_ordinal"})
REGISTRY_FIELDS = frozenset(
    {
        "first_namespace_ordinal",
        "last_namespace_ordinal",
        "namespace_entry_count",
        "projection_class_id",
        "projection_class_ordinal",
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
        "dependency_graph",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
        "hypothesis_status",
        "namespace_contract",
        "orders",
        "projection_class_registry",
        "projection_entries",
        "summary",
    }
)
COMPLETE_TOP_LEVEL_FIELDS = frozenset(
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
COMPLETE_RECEIPT_FIELDS = frozenset(
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
COMPLETE_OWNER_PIN_FIELDS = frozenset(
    {
        *PIN_FIELDS,
        "coordinates",
        "owner_id",
        "owner_role",
    }
)
COMPLETE_DIRECT_PIN_FIELDS = frozenset(
    {
        "body_framing",
        "canonical_bytes",
        "direct_pin_id",
        "direct_pin_role",
        "sha256",
    }
)

NAMESPACE_ROOT_ID = "projection-pin-corpus-semantic-namespace-root"
HYPOTHESIS_STATUS = (
    "authored-benchmark-projection-pin-namespace-candidate-"
    "not-observed-user-data"
)


class PersonaV2CorpusSemanticNamespaceV3ValidationError(ValueError):
    """Raised when the additive v3 namespace fails closed."""


def _fail(message):
    raise PersonaV2CorpusSemanticNamespaceV3ValidationError(message)


def _bounded_text(value, *, label):
    if type(value) is not str or not value or len(value) > MAX_IDENTITY_STRING_BYTES:
        _fail(f"{label} must be one bounded exact string")
    try:
        encoded = value.encode("utf-8", "strict")
    except UnicodeEncodeError:
        _fail(f"{label} must be valid UTF-8")
    if len(encoded) > MAX_IDENTITY_STRING_BYTES:
        _fail(f"{label} exceeds its UTF-8 byte cap")
    return value


def _bounded_int(value, *, label, minimum=0):
    if (
        type(value) is not int
        or type(value) is bool
        or value < minimum
        or value > artifact_common.MAX_INTEGER_MAGNITUDE
    ):
        _fail(f"{label} must be one bounded exact integer")
    return value


def _preflight_plain_tree(
    value,
    *,
    label,
    maximum_bytes,
    depth=0,
    state=None,
):
    """Bound fanout, nodes, and expanded encoded bytes before serialization.

    The byte counter intentionally counts a shared Python container once per
    occurrence.  Reusing one small list from hundreds of schema positions can
    therefore never hide a very large serialized expansion.
    """

    if state is None:
        state = {"nodes": 0, "encoded_bytes": 0}
    state["nodes"] += 1
    if state["nodes"] > 200_000:
        _fail(f"{label} exceeds its preflight node budget")
    if depth > artifact_common.MAX_CANONICAL_DEPTH:
        _fail(f"{label} exceeds its nesting-depth cap")

    def add_encoded(size):
        state["encoded_bytes"] += size
        if state["encoded_bytes"] > maximum_bytes:
            _fail(f"{label} exceeds its expanded encoded-byte budget")

    if type(value) is bool:
        add_encoded(4 if value else 5)
        return
    if type(value) is int:
        _bounded_int(value, label=label)
        add_encoded(len(str(value)))
        return
    if type(value) is str:
        _bounded_text(value, label=label)
        add_encoded(
            len(
                json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode(
                    "utf-8", "strict"
                )
            )
        )
        return
    if type(value) is list:
        if len(value) > 512:
            _fail(f"{label} list exceeds its preflight cardinality cap")
        add_encoded(2 + max(0, len(value) - 1))
        for item in value:
            _preflight_plain_tree(
                item,
                label=label,
                maximum_bytes=maximum_bytes,
                depth=depth + 1,
                state=state,
            )
        return
    if type(value) is dict:
        if len(value) > 512:
            _fail(f"{label} object exceeds its preflight cardinality cap")
        add_encoded(2 + max(0, len(value) - 1))
        for key, item in value.items():
            _bounded_text(key, label=f"{label} key")
            add_encoded(
                len(
                    json.dumps(
                        key, ensure_ascii=False, separators=(",", ":")
                    ).encode("utf-8", "strict")
                )
                + 1
            )
            _preflight_plain_tree(
                item,
                label=label,
                maximum_bytes=maximum_bytes,
                depth=depth + 1,
                state=state,
            )
        return
    _fail(f"{label} contains a forbidden value type")


def _require_coordinates(class_id, coordinates):
    if type(coordinates) is not dict or len(coordinates) > MAX_COORDINATE_FIELDS:
        _fail("projection coordinates exceed the four-field cap")
    for key, item in coordinates.items():
        _bounded_text(key, label="projection coordinate key")
        if type(item) is str:
            _bounded_text(item, label="projection coordinate value")
        else:
            _bounded_int(item, label="projection coordinate value", minimum=1)
    if class_id in {
        "topology-path-load",
        "realism-locale-security",
        "route-scores",
        "payload-equivalence-rules",
    }:
        expected_fields = frozenset()
    elif class_id in {
        "primary-use-case-corpus-half",
        "recipe-content-filename-policy",
    }:
        if coordinates != {"scope": "suite"}:
            _fail("suite projection coordinates drifted")
        return
    elif class_id in {
        "fact-graph",
        "effective-source-membership",
        "query-independent-lifecycle-fact-rendition-rules",
    }:
        expected_fields = frozenset({"persona_id"})
    elif class_id == "concrete-overlay-relations":
        expected_fields = frozenset({"origin", "persona_id"})
    elif class_id in {
        "base-source-content-context",
        "source-instance-parameters",
    }:
        if (
            class_id == "source-instance-parameters"
            and coordinates
            == {"parameter_catalog_id": "global-source-parameter-cells-v1"}
        ):
            return
        expected_fields = frozenset(
            {"origin", "persona_id", "source_shard_id", "source_shard_ordinal"}
        )
    else:
        _fail("projection coordinates use a foreign class")
    if len(coordinates) != len(expected_fields) or set(coordinates) != expected_fields:
        _fail("projection coordinate schema drifted")
    if "persona_id" in coordinates and coordinates["persona_id"] not in PERSONA_IDS:
        _fail("projection coordinates contain a foreign persona")
    if "origin" in coordinates and coordinates["origin"] not in ORIGIN_ORDER:
        _fail("projection coordinates contain a foreign origin")


def _expected_framing(class_id, coordinates):
    if class_id in {
        "base-source-content-context",
        "concrete-overlay-relations",
    }:
        return "canonical-jsonl-lf"
    if class_id == "source-instance-parameters":
        return (
            "canonical-json"
            if coordinates
            == {"parameter_catalog_id": "global-source-parameter-cells-v1"}
            else "canonical-jsonl-lf"
        )
    return "canonical-json"


def _expected_projection_identity(class_id, coordinates):
    if class_id == "source-instance-parameters":
        return (
            PARAMETER_CELL_IDENTITY
            if coordinates
            == {"parameter_catalog_id": "global-source-parameter-cells-v1"}
            else PARAMETER_ASSIGNMENT_IDENTITY
        )
    try:
        return EXPECTED_PROJECTION_IDENTITIES[class_id]
    except KeyError:
        _fail("projection pin uses a foreign class identity")


def _require_projection_pin(pin, *, class_id, coordinates):
    if type(pin) is not dict or len(pin) != len(PIN_FIELDS) or set(pin) != PIN_FIELDS:
        _fail("projection pin must contain exactly six fields")
    for field in ("artifact_kind", "artifact_schema", "body_framing", "sha256"):
        _bounded_text(pin.get(field), label=f"projection pin {field}")
    if pin["artifact_schema_version"] != 1 or type(
        pin["artifact_schema_version"]
    ) is bool:
        _fail("projection pin artifact schema version drifted")
    expected_kind, expected_schema = _expected_projection_identity(
        class_id, coordinates
    )
    if (
        pin["artifact_kind"] != expected_kind
        or pin["artifact_schema"] != expected_schema
    ):
        _fail("projection pin kind/schema differs from its class/coordinates")
    framing = pin["body_framing"]
    if framing != _expected_framing(class_id, coordinates):
        _fail("projection pin framing differs from its class/coordinates")
    maximum = (
        MAX_JSONL_PROJECTION_BYTES
        if framing == "canonical-jsonl-lf"
        else MAX_JSON_PROJECTION_BYTES
    )
    size = pin["canonical_bytes"]
    if type(size) is not int or type(size) is bool or not 0 < size <= maximum:
        _fail("projection pin canonical byte count exceeds its framing cap")
    digest = pin["sha256"]
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        _fail("projection pin SHA-256 must be lowercase hexadecimal")


def _preflight_namespace(value):
    if (
        type(value) is not dict
        or len(value) != len(TOP_LEVEL_FIELDS)
        or set(value) != TOP_LEVEL_FIELDS
    ):
        _fail("v3 namespace top-level schema drifted before canonicalization")
    if value.get("artifact_schema") != NAMESPACE_SCHEMA:
        _fail("v3 namespace schema drifted before canonicalization")
    sections = (
        ("authority", dict, len(AUTHORITY_FIELDS)),
        ("canonical_limits", dict, 16),
        ("completion_claims", dict, 8),
        ("dependency_graph", dict, 7),
        ("namespace_contract", dict, 11),
        ("orders", dict, 3),
        ("projection_class_registry", list, MAX_PROJECTION_CLASS_COUNT),
        ("projection_entries", list, MAX_PROJECTION_ENTRY_COUNT),
        ("summary", dict, 11),
    )
    for field, expected_type, exact_length in sections:
        section = value.get(field)
        if type(section) is not expected_type or len(section) != exact_length:
            _fail(f"v3 namespace {field} cardinality drifted before canonicalization")
    authority = value["authority"]
    if len(authority) != len(AUTHORITY_FIELDS) or set(authority) != AUTHORITY_FIELDS:
        _fail("v3 namespace authority schema drifted before canonicalization")
    if any(type(item) is not bool for item in authority.values()):
        _fail("v3 namespace authority values must be exact booleans")
    graph = value["dependency_graph"]
    edges = graph.get("edges")
    if type(edges) is not list or len(edges) != MAX_PROJECTION_ENTRY_COUNT:
        _fail("v3 namespace edge count drifted before canonicalization")
    for edge in edges:
        if type(edge) is not dict or len(edge) != 2 or set(edge) != EDGE_FIELDS:
            _fail("v3 namespace edge schema drifted before canonicalization")
    registry = value["projection_class_registry"]
    for row in registry:
        if (
            type(row) is not dict
            or len(row) != len(REGISTRY_FIELDS)
            or set(row) != REGISTRY_FIELDS
        ):
            _fail("v3 namespace class registry schema drifted before canonicalization")
    entries = value["projection_entries"]
    for entry in entries:
        if (
            type(entry) is not dict
            or len(entry) != len(ENTRY_FIELDS)
            or set(entry) != ENTRY_FIELDS
        ):
            _fail("v3 namespace entry must contain exactly four fields")
        coordinates = entry.get("coordinates")
        pin = entry.get("projection_pin")
        if type(coordinates) is not dict or len(coordinates) > MAX_COORDINATE_FIELDS:
            _fail("v3 namespace coordinates exceed their shallow cap")
        if type(pin) is not dict or len(pin) != len(PIN_FIELDS) or set(pin) != PIN_FIELDS:
            _fail("v3 namespace pin must contain exactly six fields")
    # Exact semantic checks also force every edge, registry, summary, entry,
    # coordinate, and pin scalar to its required built-in type before the full
    # object can reach the canonical serializer.
    _prevalidate_namespace(value)
    _preflight_plain_tree(
        value,
        label="v3 namespace preflight",
        maximum_bytes=MAX_MANIFEST_BYTES,
    )


def _preflight_complete_inventory(value):
    """Bound the caller-owned descriptor before taking its opening image."""

    if (
        type(value) is not dict
        or len(value) != len(COMPLETE_TOP_LEVEL_FIELDS)
        or set(value) != COMPLETE_TOP_LEVEL_FIELDS
    ):
        _fail("complete inventory top-level schema drifted before namespace validation")
    if value.get("artifact_schema") != COMPLETE_INVENTORY_SCHEMA:
        _fail("complete inventory schema drifted before namespace validation")
    receipts = value.get("derivation_receipts")
    if type(receipts) is not list or len(receipts) != MAX_PROJECTION_ENTRY_COUNT:
        _fail("complete inventory receipt count drifted before namespace validation")
    bounded_root_sections = {
        "authority": 24,
        "canonical_limits": 16,
        "completion_claims": 8,
        "missing_projection_class_ledger": 0,
        "orders": 3,
        "predecessor_inventory_binding": 6,
        "projection_class_registry": 12,
        "remaining_blockers": 8,
        "summary": 12,
    }
    for field, maximum in bounded_root_sections.items():
        section = value.get(field)
        if type(section) not in {dict, list} or len(section) > maximum:
            _fail(f"complete inventory {field} exceeds its namespace opening cap")
    for receipt in receipts:
        if (
            type(receipt) is not dict
            or len(receipt) != len(COMPLETE_RECEIPT_FIELDS)
            or set(receipt) != COMPLETE_RECEIPT_FIELDS
        ):
            _fail("complete inventory receipt schema drifted before namespace validation")
        coordinates = receipt.get("coordinates")
        owners = receipt.get("full_owner_pins")
        direct = receipt.get("direct_body_pins")
        pin = receipt.get("projection_pin")
        projector = receipt.get("projector")
        validation = receipt.get("validation")
        if type(coordinates) is not dict or len(coordinates) > MAX_COORDINATE_FIELDS:
            _fail("complete inventory receipt coordinates exceed the opening cap")
        if type(owners) is not list or not 1 <= len(owners) <= 8:
            _fail("complete inventory owner pins exceed the opening cap")
        if type(direct) is not list or not 1 <= len(direct) <= 12:
            _fail("complete inventory direct pins exceed the opening cap")
        if any(
            type(row) is not dict
            or len(row) != len(COMPLETE_OWNER_PIN_FIELDS)
            or set(row) != COMPLETE_OWNER_PIN_FIELDS
            or type(row.get("coordinates")) is not dict
            or len(row["coordinates"]) > MAX_COORDINATE_FIELDS
            for row in owners
        ):
            _fail("complete inventory owner pin schema exceeds the opening cap")
        if any(
            type(row) is not dict
            or len(row) != len(COMPLETE_DIRECT_PIN_FIELDS)
            or set(row) != COMPLETE_DIRECT_PIN_FIELDS
            for row in direct
        ):
            _fail("complete inventory direct pin schema exceeds the opening cap")
        if type(pin) is not dict or len(pin) != len(PIN_FIELDS) or set(pin) != PIN_FIELDS:
            _fail("complete inventory projection pin schema drifted at opening")
        if type(projector) is not dict or len(projector) != 2:
            _fail("complete inventory projector schema drifted at opening")
        if type(validation) is not dict or len(validation) != 4:
            _fail("complete inventory validation schema drifted at opening")
    preflight = getattr(complete_validator, "_preflight_inventory_shape", None)
    if not callable(preflight):
        _fail("complete trust-source strict shape preflight is unavailable")
    try:
        preflight(value)
    except Exception:
        raise PersonaV2CorpusSemanticNamespaceV3ValidationError(
            "complete inventory strict shape preflight failed"
        ) from None
    _preflight_plain_tree(
        value,
        label="complete inventory namespace opening",
        maximum_bytes=MAX_COMPLETE_INVENTORY_BYTES,
    )


def _canonical_namespace(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="projection-pin corpus semantic namespace v3",
            max_bytes=MAX_MANIFEST_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _canonical_complete(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="complete projection inventory namespace trust source",
            max_bytes=MAX_COMPLETE_INVENTORY_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _reject_duplicate_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("duplicate JSON object key is forbidden")
        result[key] = value
    return result


def _reject_constant(_value):
    _fail("JSON non-finite constants are forbidden")


def _reject_float(_value):
    _fail("JSON floating-point numbers are forbidden")


def _strict_json_loads(raw, *, label, maximum):
    if type(raw) is not bytes:
        _fail(f"{label} must be exact built-in bytes")
    if len(raw) > maximum:
        _fail(f"{label} exceeds its framed byte cap")
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_constant,
            parse_float=_reject_float,
        )
    except PersonaV2CorpusSemanticNamespaceV3ValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
        _fail(f"{label} is not strict UTF-8 JSON")
    try:
        artifact_common.validate_plain_value(value, label=label)
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))
    return value


def _opening_namespace(value):
    _preflight_namespace(value)
    raw = _canonical_namespace(value)
    snapshot = _strict_json_loads(
        raw, label="v3 namespace opening image", maximum=MAX_MANIFEST_BYTES
    )
    if type(snapshot) is not dict or not hmac.compare_digest(
        raw, _canonical_namespace(snapshot)
    ):
        _fail("v3 namespace opening image is not one canonical object")
    _reauth_namespace(value, raw)
    return snapshot, raw


def _opening_complete(value):
    _preflight_complete_inventory(value)
    raw = _canonical_complete(value)
    if (
        len(raw) != COMPLETE_INVENTORY_CANONICAL_BYTES
        or not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), COMPLETE_INVENTORY_SHA256)
    ):
        _fail("complete inventory differs from its frozen opening pin")
    snapshot = _strict_json_loads(
        raw,
        label="complete inventory namespace opening image",
        maximum=MAX_COMPLETE_INVENTORY_BYTES,
    )
    if type(snapshot) is not dict or not hmac.compare_digest(
        raw, _canonical_complete(snapshot)
    ):
        _fail("complete inventory namespace opening image is not canonical")
    _reauth_complete(value, raw)
    return snapshot, raw


def _reauth_namespace(value, opening_raw):
    _preflight_namespace(value)
    if not hmac.compare_digest(opening_raw, _canonical_namespace(value)):
        _fail("caller-owned v3 namespace mutated during validation")


def _reauth_complete(value, opening_raw):
    _preflight_complete_inventory(value)
    if not hmac.compare_digest(opening_raw, _canonical_complete(value)):
        _fail("caller-owned complete inventory mutated during namespace validation")


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


def _canonical_limits():
    return {
        "exact_cumulative_external_projection_bytes": (
            EXPECTED_CUMULATIVE_EXTERNAL_PROJECTION_BYTES
        ),
        "exact_json_projection_body_count": EXPECTED_JSON_PROJECTION_COUNT,
        "exact_jsonl_projection_body_count": EXPECTED_JSONL_PROJECTION_COUNT,
        "external_projection_bodies_embedded": False,
        "max_coordinate_fields_per_entry": MAX_COORDINATE_FIELDS,
        "max_cumulative_external_projection_bytes": (
            MAX_CUMULATIVE_EXTERNAL_PROJECTION_BYTES
        ),
        "max_identity_string_bytes": MAX_IDENTITY_STRING_BYTES,
        "max_json_projection_bytes": MAX_JSON_PROJECTION_BYTES,
        "max_jsonl_projection_bytes": MAX_JSONL_PROJECTION_BYTES,
        "max_manifest_bytes": MAX_MANIFEST_BYTES,
        "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
        "max_projection_class_count": MAX_PROJECTION_CLASS_COUNT,
        "max_projection_entry_count": MAX_PROJECTION_ENTRY_COUNT,
        "self_hash_embedded": False,
        "target_manifest_bytes": TARGET_MANIFEST_BYTES,
        "unicode_normalization": "NFC",
    }


def _completion_claims():
    return {
        "all_253_projection_pins_bound": True,
        "complete_inventory_independently_validated": True,
        "corpus_semantic_namespace_issued": False,
        "namespace_golden_frozen": True,
        "projection_pin_only_namespace_complete": True,
        "query_oracle_review_evidence_ledger_excluded": True,
        "source_identity_namespace_authoritative": False,
        "star_dependency_graph_complete": True,
    }


def _namespace_contract():
    return {
        "complete_inventory_descriptor_embedded": False,
        "dependency_graph_shape": "single-root-direct-star",
        "derivation_receipt_fields_embedded": False,
        "external_projection_bodies_embedded": False,
        "namespace_issuance_authorized": False,
        "projection_pin_only_entries": True,
        "query_oracle_review_evidence_ledger_excluded": True,
        "receipt_projector_owner_validation_fields_excluded": True,
        "source_identity_derivation_authorized": False,
        "source_identity_namespace_authoritative": False,
        "v2_full_body_candidate_accepted_by_v3": False,
    }


def _projection_class_registry():
    result = []
    first = 1
    for class_ordinal, class_id in enumerate(PROJECTION_CLASS_ORDER, start=1):
        count = EXPECTED_ENTRY_COUNTS[class_id]
        last = first + count - 1
        result.append(
            {
                "first_namespace_ordinal": first,
                "last_namespace_ordinal": last,
                "namespace_entry_count": count,
                "projection_class_id": class_id,
                "projection_class_ordinal": class_ordinal,
            }
        )
        first = last + 1
    return result


def _dependency_graph():
    return {
        "edge_count": MAX_PROJECTION_ENTRY_COUNT,
        "edges": [
            {
                "from_node_id": NAMESPACE_ROOT_ID,
                "to_namespace_ordinal": ordinal,
            }
            for ordinal in range(1, MAX_PROJECTION_ENTRY_COUNT + 1)
        ],
        "max_depth": 1,
        "namespace_root_id": NAMESPACE_ROOT_ID,
        "projection_leaf_count": MAX_PROJECTION_ENTRY_COUNT,
        "root_count": 1,
        "unused_projection_leaf_count": 0,
    }


def _projection_entries(receipts):
    if type(receipts) is not list or len(receipts) != MAX_PROJECTION_ENTRY_COUNT:
        _fail("complete inventory must expose exactly 253 receipts")
    expected_classes = [
        class_id
        for class_id in PROJECTION_CLASS_ORDER
        for _ in range(EXPECTED_ENTRY_COUNTS[class_id])
    ]
    entries = []
    seen_coordinates = set()
    seen_digests = set()
    cumulative = 0
    json_count = 0
    jsonl_count = 0
    for ordinal, (receipt, expected_class) in enumerate(
        zip(receipts, expected_classes, strict=True), start=1
    ):
        if type(receipt) is not dict:
            _fail("complete inventory receipt must be an exact object")
        class_id = receipt.get("projection_class_id")
        coordinates = receipt.get("coordinates")
        pin = receipt.get("projection_pin")
        if class_id != expected_class:
            _fail("complete inventory receipt class/order drifted")
        _require_coordinates(class_id, coordinates)
        _require_projection_pin(pin, class_id=class_id, coordinates=coordinates)
        coordinate_key = (
            class_id,
            tuple(sorted(coordinates.items(), key=lambda item: item[0].encode("utf-8"))),
        )
        if coordinate_key in seen_coordinates:
            _fail("projection class/coordinates are duplicated")
        seen_coordinates.add(coordinate_key)
        if pin["sha256"] in seen_digests:
            _fail("projection body pin alias detected")
        seen_digests.add(pin["sha256"])
        cumulative += pin["canonical_bytes"]
        if cumulative > MAX_CUMULATIVE_EXTERNAL_PROJECTION_BYTES:
            _fail("projection pins exceed the cumulative external-body cap")
        if pin["body_framing"] == "canonical-json":
            json_count += 1
        else:
            jsonl_count += 1
        # These containers came from a strict immutable opening byte image.
        entries.append(
            {
                "coordinates": json.loads(
                    artifact_common.canonical_json_bytes(
                        coordinates,
                        label="expected namespace coordinates",
                        max_bytes=MAX_IDENTITY_STRING_BYTES * 8,
                    )
                ),
                "namespace_ordinal": ordinal,
                "projection_class_id": class_id,
                "projection_pin": json.loads(
                    artifact_common.canonical_json_bytes(
                        pin,
                        label="expected namespace projection pin",
                        max_bytes=MAX_IDENTITY_STRING_BYTES * 8,
                    )
                ),
            }
        )
    if cumulative != EXPECTED_CUMULATIVE_EXTERNAL_PROJECTION_BYTES:
        _fail("projection pin cumulative bytes differ from the frozen inventory")
    if (
        json_count != EXPECTED_JSON_PROJECTION_COUNT
        or jsonl_count != EXPECTED_JSONL_PROJECTION_COUNT
    ):
        _fail("projection pin framing counts drifted")
    return entries


def _build_expected_namespace(receipts):
    entries = _projection_entries(receipts)
    return {
        "artifact_kind": NAMESPACE_KIND,
        "artifact_schema": NAMESPACE_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": _negative_authority(),
        "canonical_limits": _canonical_limits(),
        "completion_claims": _completion_claims(),
        "dependency_graph": _dependency_graph(),
        "fixture_id": FIXTURE_ID,
        "fixture_schema_version": FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "hypothesis_status": HYPOTHESIS_STATUS,
        "namespace_contract": _namespace_contract(),
        "orders": {
            "projection_classes": list(PROJECTION_CLASS_ORDER),
            "projection_entries": "complete-inventory-derivation-receipt-order",
            "star_edges": "one-based-namespace-ordinal-order",
        },
        "projection_class_registry": _projection_class_registry(),
        "projection_entries": entries,
        "summary": {
            "covered_projection_class_count": MAX_PROJECTION_CLASS_COUNT,
            "cumulative_external_projection_bytes": (
                EXPECTED_CUMULATIVE_EXTERNAL_PROJECTION_BYTES
            ),
            "dependency_edge_count": MAX_PROJECTION_ENTRY_COUNT,
            "external_projection_body_count": MAX_PROJECTION_ENTRY_COUNT,
            "json_projection_body_count": EXPECTED_JSON_PROJECTION_COUNT,
            "jsonl_projection_body_count": EXPECTED_JSONL_PROJECTION_COUNT,
            "max_dependency_depth": 1,
            "namespace_entry_count": MAX_PROJECTION_ENTRY_COUNT,
            "projection_class_count": MAX_PROJECTION_CLASS_COUNT,
            "unique_projection_pin_count": MAX_PROJECTION_ENTRY_COUNT,
            "unused_projection_leaf_count": 0,
        },
    }


@functools.lru_cache(maxsize=1)
def _expected_namespace_raw_from_complete_raw(complete_raw):
    """Cache only immutable bytes; never expose cached list/dict state."""

    inventory = _strict_json_loads(
        complete_raw,
        label="accepted complete inventory opening bytes",
        maximum=MAX_COMPLETE_INVENTORY_BYTES,
    )
    if type(inventory) is not dict:
        _fail("accepted complete inventory opening bytes are not an object")
    expected = _build_expected_namespace(inventory.get("derivation_receipts"))
    raw = _canonical_namespace(expected)
    if len(raw) > TARGET_MANIFEST_BYTES:
        _fail("independently reconstructed v3 namespace exceeds 512 KiB target")
    if EXPECTED_NAMESPACE_CANONICAL_BYTES is not None and len(raw) != EXPECTED_NAMESPACE_CANONICAL_BYTES:
        _fail("independently reconstructed v3 namespace byte length drifted")
    digest = hashlib.sha256(raw).hexdigest()
    if EXPECTED_NAMESPACE_SHA256 is not None and not hmac.compare_digest(
        digest, EXPECTED_NAMESPACE_SHA256
    ):
        _fail("independently reconstructed v3 namespace SHA-256 drifted")
    return raw


def _prevalidate_namespace(snapshot):
    if type(snapshot) is not dict or set(snapshot) != TOP_LEVEL_FIELDS:
        _fail("v3 namespace top-level schema drifted")
    if (
        snapshot.get("artifact_kind") != NAMESPACE_KIND
        or snapshot.get("artifact_schema") != NAMESPACE_SCHEMA
        or snapshot.get("artifact_schema_version") != ARTIFACT_SCHEMA_VERSION
        or type(snapshot.get("artifact_schema_version")) is bool
        or snapshot.get("fixture_id") != FIXTURE_ID
        or snapshot.get("fixture_schema_version") != FIXTURE_SCHEMA_VERSION
        or type(snapshot.get("fixture_schema_version")) is bool
        or snapshot.get("g0_contract_frozen") is not False
        or snapshot.get("hypothesis_status") != HYPOTHESIS_STATUS
    ):
        _fail("v3 namespace identity/status drifted")
    if not _strict_equal(snapshot.get("authority"), _negative_authority()) or any(
        value is not False for value in snapshot["authority"].values()
    ):
        _fail("v3 namespace authority must be exact all-false")
    exact_sections = (
        ("canonical_limits", _canonical_limits()),
        ("completion_claims", _completion_claims()),
        ("namespace_contract", _namespace_contract()),
        (
            "orders",
            {
                "projection_classes": list(PROJECTION_CLASS_ORDER),
                "projection_entries": "complete-inventory-derivation-receipt-order",
                "star_edges": "one-based-namespace-ordinal-order",
            },
        ),
        ("projection_class_registry", _projection_class_registry()),
    )
    for field, expected in exact_sections:
        if not _strict_equal(snapshot.get(field), expected):
            _fail(f"v3 namespace {field} drifted")

    entries = snapshot["projection_entries"]
    # Re-use the same independent entry validator on a receipt-shaped view.
    receipts = [
        {
            "coordinates": entry.get("coordinates"),
            "projection_class_id": entry.get("projection_class_id"),
            "projection_pin": entry.get("projection_pin"),
        }
        for entry in entries
    ]
    independently_normalized = _projection_entries(receipts)
    if not _strict_equal(entries, independently_normalized):
        _fail("v3 namespace entry ordinals/content drifted")

    graph = snapshot["dependency_graph"]
    if not _strict_equal(graph, _dependency_graph()):
        _fail("v3 namespace dependency graph is not the exact root star")
    edges = graph["edges"]
    targets = [edge["to_namespace_ordinal"] for edge in edges]
    if (
        any(edge["from_node_id"] != NAMESPACE_ROOT_ID for edge in edges)
        or len(set(targets)) != MAX_PROJECTION_ENTRY_COUNT
        or set(targets) != set(range(1, MAX_PROJECTION_ENTRY_COUNT + 1))
    ):
        _fail("v3 namespace star reachability/uniqueness drifted")

    expected_summary = {
        "covered_projection_class_count": MAX_PROJECTION_CLASS_COUNT,
        "cumulative_external_projection_bytes": (
            EXPECTED_CUMULATIVE_EXTERNAL_PROJECTION_BYTES
        ),
        "dependency_edge_count": MAX_PROJECTION_ENTRY_COUNT,
        "external_projection_body_count": MAX_PROJECTION_ENTRY_COUNT,
        "json_projection_body_count": EXPECTED_JSON_PROJECTION_COUNT,
        "jsonl_projection_body_count": EXPECTED_JSONL_PROJECTION_COUNT,
        "max_dependency_depth": 1,
        "namespace_entry_count": MAX_PROJECTION_ENTRY_COUNT,
        "projection_class_count": MAX_PROJECTION_CLASS_COUNT,
        "unique_projection_pin_count": MAX_PROJECTION_ENTRY_COUNT,
        "unused_projection_leaf_count": 0,
    }
    if not _strict_equal(snapshot.get("summary"), expected_summary):
        _fail("v3 namespace summary drifted")


def validate_corpus_semantic_namespace_v3(
    value,
    *,
    complete_inventory,
    projection_body_provider,
):
    """Validate the namespace and its all-253 trust source without authority."""

    namespace_snapshot, namespace_raw = _opening_namespace(value)
    complete_snapshot, complete_raw = _opening_complete(complete_inventory)
    if not callable(projection_body_provider):
        _fail("complete projection body provider must be callable")
    if EXPECTED_NAMESPACE_CANONICAL_BYTES is not None and len(namespace_raw) != EXPECTED_NAMESPACE_CANONICAL_BYTES:
        _fail("v3 namespace differs from its frozen byte length")
    if EXPECTED_NAMESPACE_SHA256 is not None and not hmac.compare_digest(
        hashlib.sha256(namespace_raw).hexdigest(), EXPECTED_NAMESPACE_SHA256
    ):
        _fail("v3 namespace differs from its frozen SHA-256")
    _prevalidate_namespace(namespace_snapshot)

    def guarded_provider(receipt):
        try:
            return projection_body_provider(receipt)
        finally:
            _reauth_namespace(value, namespace_raw)
            _reauth_complete(complete_inventory, complete_raw)

    validation_error = None
    try:
        try:
            result = complete_validator.validate_semantic_projection_complete_inventory(
                complete_inventory,
                projection_body_provider=guarded_provider,
            )
        except Exception:
            raise PersonaV2CorpusSemanticNamespaceV3ValidationError(
                "complete projection trust-source validation failed"
            ) from None
        if result is not True:
            _fail("complete projection trust-source validator did not return exact true")
        _reauth_namespace(value, namespace_raw)
        _reauth_complete(complete_inventory, complete_raw)
        # The independently validated source must be the same immutable opening
        # image used to reconstruct the exact four-field projection.
        if not _strict_equal(
            complete_snapshot,
            _strict_json_loads(
                complete_raw,
                label="complete inventory accepted opening image",
                maximum=MAX_COMPLETE_INVENTORY_BYTES,
            ),
        ):
            _fail("complete inventory detached opening image drifted")
        expected_raw = _expected_namespace_raw_from_complete_raw(complete_raw)
        if not hmac.compare_digest(namespace_raw, expected_raw):
            _fail("v3 namespace differs from independent pin-only reconstruction")
    except Exception as error:
        validation_error = error
    finally:
        postflight_error = None
        try:
            _reauth_namespace(value, namespace_raw)
        except Exception as error:
            postflight_error = error
        try:
            _reauth_complete(complete_inventory, complete_raw)
        except Exception as error:
            if postflight_error is None:
                postflight_error = error
        if postflight_error is not None:
            raise postflight_error
    if validation_error is not None:
        if type(validation_error) is PersonaV2CorpusSemanticNamespaceV3ValidationError:
            raise validation_error
        _fail("v3 namespace validation failed")
    return True


def validate_corpus_semantic_namespace_v3_bytes(
    raw,
    *,
    complete_inventory,
    projection_body_provider,
):
    """Strict duplicate-key-aware loader with cap-before-parse behavior."""

    value = _strict_json_loads(
        raw, label="framed v3 namespace body", maximum=MAX_MANIFEST_BYTES
    )
    if type(value) is not dict:
        _fail("framed v3 namespace body must decode to one object")
    _preflight_namespace(value)
    if not hmac.compare_digest(raw, _canonical_namespace(value)):
        _fail("framed v3 namespace body is not exact canonical JSON")
    return validate_corpus_semantic_namespace_v3(
        value,
        complete_inventory=complete_inventory,
        projection_body_provider=projection_body_provider,
    )


__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "AUTHORITY_FIELDS",
    "COMPLETE_INVENTORY_CANONICAL_BYTES",
    "COMPLETE_INVENTORY_SHA256",
    "EXPECTED_CUMULATIVE_EXTERNAL_PROJECTION_BYTES",
    "EXPECTED_ENTRY_COUNTS",
    "EXPECTED_NAMESPACE_CANONICAL_BYTES",
    "EXPECTED_NAMESPACE_SHA256",
    "MAX_MANIFEST_BYTES",
    "NAMESPACE_KIND",
    "NAMESPACE_SCHEMA",
    "PROJECTION_CLASS_ORDER",
    "PersonaV2CorpusSemanticNamespaceV3ValidationError",
    "validate_corpus_semantic_namespace_v3",
    "validate_corpus_semantic_namespace_v3_bytes",
]
