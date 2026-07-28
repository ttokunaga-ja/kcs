"""Projection-pin-only corpus semantic namespace candidate (additive v3).

The accepted complete 253-body projection inventory is the sole content input.
This artifact deliberately projects only coordinates, class identity, ordinal,
and the six-field external-body pin.  It does not embed bodies, derivation
receipts, projectors, owner evidence, review/evidence, query/oracle material, a
blocker ledger, or an inventory descriptor pin.

The module is non-authorizing.  In particular, producing or validating this
candidate does not issue an authoritative source namespace and does not permit
solver, identifier, rendering, filesystem, history, KIO, capacity, or G0 work.
"""

from __future__ import annotations

import functools
import hashlib
import hmac
import json

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_semantic_projection_complete_inventory as complete
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_semantic_projection_complete_inventory as complete


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

# Frozen only after the final body shape, including its golden-frozen claim,
# reproduced under two isolated all-253 builds with distinct Python hash seeds.
# Issuance and every authority bit remain false regardless of golden state.
EXPECTED_NAMESPACE_CANONICAL_BYTES = 161_665
EXPECTED_NAMESPACE_SHA256 = (
    "a8bc67e182ff57b64ae6df0f97bd5be31faf6e5f7b7cfbd0bc3f1ba7bc5cc509"
)

COMPLETE_INVENTORY_CANONICAL_BYTES = 697_466
COMPLETE_INVENTORY_SHA256 = (
    "820c976a930c3f2ed0a54e44c08b01cad8a0879513f1b06012e353fb9bd3fd91"
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

NAMESPACE_ROOT_ID = "projection-pin-corpus-semantic-namespace-root"
HYPOTHESIS_STATUS = (
    "authored-benchmark-projection-pin-namespace-candidate-"
    "not-observed-user-data"
)


class PersonaV2CorpusSemanticNamespaceV3Error(ValueError):
    """Raised when the additive v3 namespace candidate fails closed."""


def _fail(message):
    raise PersonaV2CorpusSemanticNamespaceV3Error(message)


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
        entries.append(
            {
                "coordinates": json.loads(
                    artifact_common.canonical_json_bytes(
                        coordinates,
                        label="projection namespace coordinates",
                        max_bytes=MAX_IDENTITY_STRING_BYTES * 8,
                    )
                ),
                "namespace_ordinal": ordinal,
                "projection_class_id": class_id,
                "projection_pin": json.loads(
                    artifact_common.canonical_json_bytes(
                        pin,
                        label="projection namespace pin",
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


def _build_namespace_value_from_receipts(receipts):
    """Build from an already authenticated complete-inventory opening image."""

    entries = _projection_entries(receipts)
    value = {
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
    if set(value) != TOP_LEVEL_FIELDS:
        _fail("v3 namespace top-level schema drifted")
    return value


def _canonical(value, *, label="projection-pin corpus semantic namespace v3"):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label=label,
            max_bytes=MAX_MANIFEST_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _strict_detached(raw, *, label):
    if type(raw) is not bytes:
        _fail(f"{label} must be exact bytes")
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
            parse_float=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
        _fail(f"{label} is not strict JSON")
    return value


def _require_independent_complete_preflight(value):
    """Bound a caller-owned complete inventory before producer canonicalization."""

    independent = _independent_validator()
    preflight = (
        None
        if independent is None
        else getattr(independent, "_preflight_complete_inventory", None)
    )
    if not callable(preflight):
        _fail("independent complete-inventory strict preflight is unavailable")
    try:
        preflight(value)
    except Exception:
        raise PersonaV2CorpusSemanticNamespaceV3Error(
            "complete inventory failed strict namespace producer preflight"
        ) from None


def _authenticated_complete_inventory_raw(value):
    _require_independent_complete_preflight(value)
    try:
        raw = complete.canonical_json_bytes(value)
    except complete.PersonaV2SemanticProjectionCompleteInventoryError as error:
        _fail(str(error))
    if (
        len(raw) != COMPLETE_INVENTORY_CANONICAL_BYTES
        or not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), COMPLETE_INVENTORY_SHA256)
    ):
        _fail("complete inventory differs from its frozen descriptor pin")
    return raw


@functools.lru_cache(maxsize=1)
def _namespace_raw_from_complete_inventory_raw(inventory_raw):
    """Cache only immutable canonical bytes, never caller-visible containers."""

    inventory = _strict_detached(inventory_raw, label="complete inventory opening image")
    if type(inventory) is not dict or type(inventory.get("derivation_receipts")) is not list:
        _fail("complete inventory opening image schema drifted")
    value = _build_namespace_value_from_receipts(inventory["derivation_receipts"])
    raw = _canonical(value)
    if len(raw) > TARGET_MANIFEST_BYTES:
        _fail("v3 namespace exceeds its 512 KiB authored target")
    if EXPECTED_NAMESPACE_CANONICAL_BYTES is not None and len(raw) != EXPECTED_NAMESPACE_CANONICAL_BYTES:
        _fail("v3 namespace canonical byte length drifted")
    digest = hashlib.sha256(raw).hexdigest()
    if EXPECTED_NAMESPACE_SHA256 is not None and not hmac.compare_digest(
        digest, EXPECTED_NAMESPACE_SHA256
    ):
        _fail("v3 namespace SHA-256 drifted")
    return raw


def build_corpus_semantic_namespace_v3(complete_inventory=None):
    """Build a detached v3 candidate from the frozen complete inventory."""

    if complete_inventory is None:
        complete_inventory = complete.build_semantic_projection_complete_inventory()
    inventory_raw = _authenticated_complete_inventory_raw(complete_inventory)
    return _strict_detached(
        _namespace_raw_from_complete_inventory_raw(inventory_raw),
        label="projection-pin corpus semantic namespace v3",
    )


def _require_independent_candidate_preflight(value):
    independent = _independent_validator()
    preflight = (
        None if independent is None else getattr(independent, "_preflight_namespace", None)
    )
    if not callable(preflight):
        _fail("independent v3 namespace strict preflight is unavailable")
    try:
        preflight(value)
    except Exception:
        raise PersonaV2CorpusSemanticNamespaceV3Error(
            "v3 namespace candidate failed strict preflight"
        ) from None


def corpus_semantic_namespace_v3_candidate_bytes(value):
    """Canonicalize a candidate only; this helper grants no authority."""

    _require_independent_candidate_preflight(value)
    return _canonical(value)


def _independent_validator():
    try:
        from . import persona_v2_corpus_semantic_namespace_v3_validator as independent
    except ImportError:  # pragma: no cover - direct-script compatibility
        try:
            import persona_v2_corpus_semantic_namespace_v3_validator as independent
        except ImportError:
            independent = None
    return independent


def validate_corpus_semantic_namespace_v3(
    value,
    *,
    complete_inventory=None,
    projection_body_provider=None,
):
    """Validate through the producer-independent complete-inventory boundary."""

    if complete_inventory is None:
        complete_inventory = complete.build_semantic_projection_complete_inventory()
    if projection_body_provider is None:
        projection_body_provider = complete.projection_body_provider
    independent = _independent_validator()
    if independent is None:
        _fail("independent v3 namespace validator is unavailable")
    opening_raw = corpus_semantic_namespace_v3_candidate_bytes(value)
    try:
        result = independent.validate_corpus_semantic_namespace_v3(
            value,
            complete_inventory=complete_inventory,
            projection_body_provider=projection_body_provider,
        )
    except independent.PersonaV2CorpusSemanticNamespaceV3ValidationError as error:
        _fail(str(error))
    finally:
        if not hmac.compare_digest(
            opening_raw, corpus_semantic_namespace_v3_candidate_bytes(value)
        ):
            _fail("caller-owned v3 namespace changed during validation")
    if result is not True:
        _fail("independent v3 namespace validator did not return exact true")
    return True


def accepted_corpus_semantic_namespace_v3_sha256(
    value,
    *,
    complete_inventory,
    projection_body_provider,
):
    """Hash only the immutable opening image accepted by full validation."""

    opening_raw = corpus_semantic_namespace_v3_candidate_bytes(value)
    validate_corpus_semantic_namespace_v3(
        value,
        complete_inventory=complete_inventory,
        projection_body_provider=projection_body_provider,
    )
    if not hmac.compare_digest(
        opening_raw, corpus_semantic_namespace_v3_candidate_bytes(value)
    ):
        _fail("v3 namespace changed while producing its accepted digest")
    return hashlib.sha256(opening_raw).hexdigest()


def require_corpus_semantic_namespace_v3():
    """Return a detached candidate accepted against all 253 bodies twice."""

    inventory = complete.build_semantic_projection_complete_inventory()
    value = build_corpus_semantic_namespace_v3(inventory)
    validate_corpus_semantic_namespace_v3(
        value,
        complete_inventory=inventory,
        projection_body_provider=complete.projection_body_provider,
    )
    return value


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
    "PersonaV2CorpusSemanticNamespaceV3Error",
    "accepted_corpus_semantic_namespace_v3_sha256",
    "build_corpus_semantic_namespace_v3",
    "corpus_semantic_namespace_v3_candidate_bytes",
    "require_corpus_semantic_namespace_v3",
    "validate_corpus_semantic_namespace_v3",
]
