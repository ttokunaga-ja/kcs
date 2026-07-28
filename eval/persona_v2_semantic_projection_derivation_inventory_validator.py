"""Independent validator for the partial semantic-projection inventory.

This module deliberately does not import the sibling inventory producer.  It
reconstructs the accepted 113-receipt inventory from the three already frozen
upstream packages, validates every external projection body twice, and keeps
all namespace/G0/execution authority fail-closed.  The accepted inventory is
useful derivation evidence for three of the twelve required projection
classes; it is not a corpus semantic namespace.
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
    from . import persona_v2_lifecycle_effective_membership_reconciliation as effective
    from . import persona_v2_lifecycle_effective_membership_reconciliation_validator as effective_validator
    from . import persona_v2_source_matched_lifecycle_inventory as matched
    from . import persona_v2_source_matched_lifecycle_inventory_validator as matched_validator
    from . import persona_v2_source_inventory_package as source_inventory
    from . import persona_v2_source_semantic_membership_package as source_semantic
    from . import persona_v2_source_semantic_membership_package_validator as source_semantic_validator
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_lifecycle_effective_membership_reconciliation as effective
    import persona_v2_lifecycle_effective_membership_reconciliation_validator as effective_validator
    import persona_v2_source_matched_lifecycle_inventory as matched
    import persona_v2_source_matched_lifecycle_inventory_validator as matched_validator
    import persona_v2_source_inventory_package as source_inventory
    import persona_v2_source_semantic_membership_package as source_semantic
    import persona_v2_source_semantic_membership_package_validator as source_semantic_validator


SUITE_SCHEMA = "kio.persona.pc-semantic-projection-derivation-inventory/v1"
SUITE_KIND = "persona-pc-v2-semantic-projection-derivation-inventory"
ARTIFACT_SCHEMA_VERSION = 1

BASE_PROJECTION_SCHEMA = (
    "kio.persona.pc-base-source-content-context-shard-projection/v1"
)
BASE_PROJECTION_KIND = (
    "persona-pc-v2-base-source-content-context-shard-projection"
)

BASE_CLASS = "base-source-content-context"
MATCHED_CLASS = "query-independent-lifecycle-fact-rendition-rules"
EFFECTIVE_CLASS = "effective-source-membership"

PROJECTION_CLASS_ORDER = (
    "topology-path-load",
    "realism-locale-security",
    "route-scores",
    "primary-use-case-corpus-half",
    "recipe-content-filename-policy",
    "fact-graph",
    BASE_CLASS,
    EFFECTIVE_CLASS,
    "concrete-overlay-relations",
    "source-instance-parameters",
    MATCHED_CLASS,
    "payload-equivalence-rules",
)
COVERED_CLASS_ORDER = (BASE_CLASS, EFFECTIVE_CLASS, MATCHED_CLASS)
MISSING_CLASS_ORDER = tuple(
    item for item in PROJECTION_CLASS_ORDER if item not in COVERED_CLASS_ORDER
)

EXPECTED_RECEIPT_COUNT = 113
EXPECTED_BASE_RECEIPT_COUNT = 73
EXPECTED_MATCHED_RECEIPT_COUNT = 20
EXPECTED_EFFECTIVE_RECEIPT_COUNT = 20
EXPECTED_BASE_ROW_COUNT = 203_000
EXPECTED_BASE_BODY_BYTES = 121_020_941
EXPECTED_SUITE_CANONICAL_BYTES = 293_285
EXPECTED_SUITE_SHA256 = (
    "e06e66901e24fda63a097dd2a5625cc562ea80008e8e6f5b961ce3c7a792dcdb"
)
EXPECTED_CUMULATIVE_EXTERNAL_BODY_BYTES = 128_144_915
EXPECTED_ORDERED_PROJECTION_PINS_SHA256 = (
    "a909168390dbc7426d5ac21a36a5720c378e0d3281f852dcd90e40344e8cb83d"
)
_EXPECTED_CLASS_MAXIMUM_BODY_BYTES = (
    (BASE_CLASS, 2_484_590),
    (EFFECTIVE_CLASS, 103_840),
    (MATCHED_CLASS, 256_790),
)

MAX_SUITE_BYTES = 1 * 2**20
MAX_CUMULATIVE_EXTERNAL_BODY_BYTES = 144 * 2**20
MAX_BASE_BODY_BYTES = 4 * 2**20
MAX_BASE_ROWS = 4_096
MAX_BASE_ROW_BYTES_INCLUDING_LF = 768
MAX_LIFECYCLE_BODY_BYTES = 384 * 2**10
TARGET_LIFECYCLE_BODY_BYTES = 256 * 2**10

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
        "projection_class_registry",
        "remaining_blockers",
        "summary",
        "upstream_suite_bindings",
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
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "body_framing",
        "canonical_bytes",
        "coordinates",
        "owner_id",
        "owner_role",
        "sha256",
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
PROJECTOR_FIELDS = frozenset({"projector_id", "projector_version"})
VALIDATION_FIELDS = frozenset(
    {
        "independent_derivation_validation_required",
        "projection_pin_matches_external_body",
        "upstream_owner_validation_result",
        "upstream_projection_validation_result",
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
MISSING_LEDGER_FIELDS = frozenset(
    {
        "blocker_id",
        "projection_class_id",
        "required_for_minimum_inventory",
        "status",
    }
)

BASE_ROW_FIELDS = frozenset(source_semantic_validator.EXPANDED_CONTEXT_ROW_FIELDS)
BASE_FORBIDDEN_FIELDS = frozenset(
    {
        "fact_profile_id",
        "present_fact_ids",
        "present_fact_set_key",
        "witness_fact_ids",
    }
)
FORBIDDEN_KEY_TOKENS = frozenset(
    {
        "answer",
        "authority",
        "blocker",
        "chunk",
        "distractor",
        "latency",
        "oracle",
        "query",
        "rank",
        "relevance",
        "review",
        "runtime",
        "solution",
    }
)


class PersonaV2SemanticProjectionDerivationInventoryValidationError(ValueError):
    """Raised when the partial derivation inventory is not exact and safe."""


def _fail(message):
    raise PersonaV2SemanticProjectionDerivationInventoryValidationError(message)


def _sha256(raw):
    if type(raw) is not bytes:
        _fail("SHA-256 input must be exact built-in bytes")
    return hashlib.sha256(raw).hexdigest()


def _require_sha256(value, *, label):
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _fail(f"{label} must be one lowercase SHA-256 hex digest")


def _canonical(value, *, label="semantic projection derivation inventory", maximum=MAX_SUITE_BYTES):
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
            _fail(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_json_constant(_value):
    _fail("non-finite JSON numbers are forbidden")


def _reject_json_float(_value):
    _fail("JSON floating-point numbers are forbidden")


def _strict_json_loads(raw, *, label):
    if type(raw) is not bytes:
        _fail(f"{label} must be exact built-in bytes")
    try:
        text = raw.decode("utf-8", "strict")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
            parse_float=_reject_json_float,
        )
    except PersonaV2SemanticProjectionDerivationInventoryValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        _fail(f"{label} is not strict UTF-8 JSON: {error}")
    try:
        artifact_common.validate_plain_value(value, label=label)
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))
    return value


def _opening_snapshot(value):
    """Authenticate live input, then deserialize that exact opening image."""

    opening_raw = _canonical(value)
    snapshot = _strict_json_loads(opening_raw, label="inventory opening image")
    if type(snapshot) is not dict:
        _fail("semantic projection derivation inventory must be an object")
    if not hmac.compare_digest(opening_raw, _canonical(snapshot)):
        _fail("inventory opening image is not canonical JSON")
    return snapshot, opening_raw


def _reauth_target(value, opening_raw):
    current = _canonical(value)
    if not hmac.compare_digest(opening_raw, current):
        _fail("caller-owned inventory mutated during validation")


def _detached(value, *, label, maximum=MAX_SUITE_BYTES):
    raw = _canonical(value, label=label, maximum=maximum)
    result = _strict_json_loads(raw, label=label)
    if not hmac.compare_digest(raw, _canonical(result, label=label, maximum=maximum)):
        _fail(f"{label} is not canonical JSON")
    return result


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


def _pin(
    *, artifact_kind, artifact_schema, artifact_schema_version, body_framing,
    canonical_bytes, sha256
):
    return {
        "artifact_kind": artifact_kind,
        "artifact_schema": artifact_schema,
        "artifact_schema_version": artifact_schema_version,
        "body_framing": body_framing,
        "canonical_bytes": canonical_bytes,
        "sha256": sha256,
    }


def _owner_pin(
    *, artifact_kind, artifact_schema, artifact_schema_version, body_framing,
    canonical_bytes, coordinates, owner_id, owner_role, sha256
):
    return {
        "artifact_kind": artifact_kind,
        "artifact_schema": artifact_schema,
        "artifact_schema_version": artifact_schema_version,
        "body_framing": body_framing,
        "canonical_bytes": canonical_bytes,
        "coordinates": copy.deepcopy(coordinates),
        "owner_id": owner_id,
        "owner_role": owner_role,
        "sha256": sha256,
    }


def _direct_pin(*, body_framing, canonical_bytes, direct_pin_id, direct_pin_role, sha256):
    return {
        "body_framing": body_framing,
        "canonical_bytes": canonical_bytes,
        "direct_pin_id": direct_pin_id,
        "direct_pin_role": direct_pin_role,
        "sha256": sha256,
    }


def _default_projection_body_provider(receipt):
    """Rebuild one projection from authenticated public upstream builders."""

    if type(receipt) is not dict or set(receipt) != RECEIPT_FIELDS:
        _fail("default provider received an invalid receipt")
    projection_class_id = receipt["projection_class_id"]
    coordinates = receipt["coordinates"]
    if projection_class_id == BASE_CLASS:
        return source_semantic.expanded_content_context_shard_body_bytes(
            coordinates["persona_id"],
            coordinates["origin"],
            coordinates["source_shard_ordinal"],
        )
    if projection_class_id == EFFECTIVE_CLASS:
        value = effective.build_lifecycle_effective_membership_content_projection(
            coordinates["persona_id"]
        )
        return effective.canonical_json_bytes(value)
    if projection_class_id == MATCHED_CLASS:
        value = matched.build_source_matched_lifecycle_content_projection(
            coordinates["persona_id"]
        )
        return matched.canonical_json_bytes(value)
    _fail("default provider received an unknown projection class")


def _json_object_body(raw, *, label, maximum):
    if len(raw) > maximum:
        _fail(f"{label} exceeds its hard byte cap")
    value = _strict_json_loads(raw, label=label)
    if type(value) is not dict:
        _fail(f"{label} must contain one JSON object")
    canonical = _canonical(value, label=label, maximum=maximum)
    if not hmac.compare_digest(raw, canonical):
        _fail(f"{label} is not compact sorted canonical JSON")
    return value


def _reject_forbidden_projection_keys(value, *, allowed_effective_commitments=False, path=()):
    if type(value) is dict:
        for key, item in value.items():
            folded = key.replace("_", "-").lower()
            tokens = frozenset(part for part in folded.split("-") if part)
            if tokens & FORBIDDEN_KEY_TOKENS:
                _fail(
                    "projection leaked forbidden semantic/runtime field at "
                    + ".".join(path + (key,))
                )
            if (
                (key == "sha256" or key.endswith("_sha256"))
                and not (
                    allowed_effective_commitments
                    and len(path) == 3
                    and path[0] == "content_sections"
                    and path[1] == "effective_membership_shard_commitments"
                    and path[2].isdigit()
                    and key == "body_sha256"
                )
            ):
                _fail(
                    "projection leaked a derivation/full-owner digest at "
                    + ".".join(path + (key,))
                )
            _reject_forbidden_projection_keys(
                item,
                allowed_effective_commitments=allowed_effective_commitments,
                path=path + (key,),
            )
    elif type(value) is list:
        for ordinal, item in enumerate(value):
            _reject_forbidden_projection_keys(
                item,
                allowed_effective_commitments=allowed_effective_commitments,
                path=path + (str(ordinal),),
            )


def _parse_base_jsonl(raw, receipt):
    if len(raw) > MAX_BASE_BODY_BYTES:
        _fail("base content-context projection exceeds four MiB")
    if not raw or not raw.endswith(b"\n") or b"\r" in raw:
        _fail("base content-context projection must be nonempty LF-framed JSONL")
    lines = raw.splitlines(keepends=True)
    if len(lines) > MAX_BASE_ROWS:
        _fail("base content-context projection exceeds 4096 rows")
    coordinates = receipt["coordinates"]
    expected_persona = coordinates["persona_id"]
    expected_origin = coordinates["origin"]
    for ordinal, framed in enumerate(lines, start=1):
        if not framed.endswith(b"\n") or len(framed) > MAX_BASE_ROW_BYTES_INCLUDING_LF:
            _fail("base content-context JSONL row framing/cap drifted")
        line = framed[:-1]
        row = _strict_json_loads(
            line,
            label=f"base content-context projection row {ordinal}",
        )
        if type(row) is not dict or set(row) != BASE_ROW_FIELDS:
            _fail("base content-context JSONL row schema drifted")
        if set(row) & BASE_FORBIDDEN_FIELDS:
            _fail("base content-context projection leaked fact membership")
        if (
            row.get("persona_id") != expected_persona
            or row.get("origin") != expected_origin
        ):
            _fail("base content-context projection contains a foreign coordinate")
        intent_key = row.get("intent_key")
        if type(intent_key) is not str or not intent_key:
            _fail("base content-context projection intent key is invalid")
        expected_line = _canonical(
            row,
            label="base content-context projection row",
            maximum=MAX_BASE_ROW_BYTES_INCLUDING_LF - 1,
        )
        if not hmac.compare_digest(line, expected_line):
            _fail("base content-context JSONL row is not canonical JSON")
    return len(lines)


def _validate_projection_body(raw, receipt):
    projection_class_id = receipt["projection_class_id"]
    coordinates = receipt["coordinates"]
    if projection_class_id == BASE_CLASS:
        row_count = _parse_base_jsonl(raw, receipt)
        try:
            expected = source_semantic.expanded_content_context_shard_body_bytes(
                coordinates["persona_id"],
                coordinates["origin"],
                coordinates["source_shard_ordinal"],
            )
        except Exception as error:
            raise PersonaV2SemanticProjectionDerivationInventoryValidationError(
                "independent base projection rebuild failed"
            ) from error
        if not hmac.compare_digest(raw, expected):
            _fail("base content-context projection differs from upstream rebuild")
        return row_count
    if projection_class_id == EFFECTIVE_CLASS:
        if len(raw) > TARGET_LIFECYCLE_BODY_BYTES:
            _fail("effective-membership projection exceeds its current 256-KiB target")
        value = _json_object_body(
            raw,
            label="effective-membership projection",
            maximum=MAX_LIFECYCLE_BODY_BYTES,
        )
        _reject_forbidden_projection_keys(
            value,
            allowed_effective_commitments=True,
        )
        try:
            result = effective_validator.validate_lifecycle_effective_membership_content_projection(
                coordinates["persona_id"], value
            )
        except Exception as error:
            raise PersonaV2SemanticProjectionDerivationInventoryValidationError(
                "independent effective-membership projection validation failed"
            ) from error
        if result is not True:
            _fail("independent effective-membership validator did not return True")
        return None
    if projection_class_id == MATCHED_CLASS:
        if len(raw) > TARGET_LIFECYCLE_BODY_BYTES:
            _fail("source-matched lifecycle projection exceeds its current 256-KiB target")
        value = _json_object_body(
            raw,
            label="source-matched lifecycle projection",
            maximum=MAX_LIFECYCLE_BODY_BYTES,
        )
        _reject_forbidden_projection_keys(value)
        try:
            result = matched_validator.validate_source_matched_lifecycle_content_projection(
                coordinates["persona_id"], value
            )
        except Exception as error:
            raise PersonaV2SemanticProjectionDerivationInventoryValidationError(
                "independent source-matched lifecycle projection validation failed"
            ) from error
        if result is not True:
            _fail("independent source-matched lifecycle validator did not return True")
        return None
    _fail("projection receipt has an unknown class")


def _call_body_provider(provider, receipt, *, replay):
    argument = _detached(
        receipt,
        label="projection derivation receipt provider argument",
    )
    try:
        body = provider(argument)
    except Exception as error:
        raise PersonaV2SemanticProjectionDerivationInventoryValidationError(
            "projection body provider failed" + (" during replay" if replay else "")
        ) from error
    if type(body) is not bytes:
        _fail("projection body provider must return exact built-in bytes")
    projection_class_id = receipt["projection_class_id"]
    hard_cap = (
        MAX_BASE_BODY_BYTES
        if projection_class_id == BASE_CLASS
        else MAX_LIFECYCLE_BODY_BYTES
    )
    if len(body) > hard_cap:
        _fail("projection body provider result exceeds its class hard cap")
    pin = receipt["projection_pin"]
    if (
        len(body) != pin["canonical_bytes"]
        or not hmac.compare_digest(_sha256(body), pin["sha256"])
    ):
        _fail("projection body provider result differs from its receipt pin")
    return body


def _authenticate_projection_body(
    provider, receipt, *, reauthenticate_target=None
):
    if reauthenticate_target is None:
        reauthenticate_target = lambda: None
    elif not callable(reauthenticate_target):
        _fail("target reauthentication callback must be callable")
    try:
        first = _call_body_provider(provider, receipt, replay=False)
    finally:
        reauthenticate_target()
    _validate_projection_body(first, receipt)
    try:
        replay = _call_body_provider(provider, receipt, replay=True)
    finally:
        reauthenticate_target()
    if not hmac.compare_digest(first, replay):
        _fail("projection body provider replay is nondeterministic")
    return len(first)


_SOURCE_SEMANTIC_SUITE_PIN_TUPLE = (
    source_semantic.SUITE_ARTIFACT_KIND,
    source_semantic.SUITE_ARTIFACT_SCHEMA,
    source_semantic.ARTIFACT_SCHEMA_VERSION,
    "canonical-json",
    source_semantic_validator.EXPECTED_SUITE_DESCRIPTOR_BYTES,
    source_semantic_validator.EXPECTED_SUITE_SHA256,
)
_EFFECTIVE_SUITE_PIN_TUPLE = (
    effective.SUITE_KIND,
    effective.SUITE_SCHEMA,
    effective.ARTIFACT_SCHEMA_VERSION,
    "canonical-json",
    effective_validator.EXPECTED_SUITE_CANONICAL_BYTES,
    effective_validator.EXPECTED_SUITE_SHA256,
)
_MATCHED_SUITE_PIN_TUPLE = (
    matched.SUITE_KIND,
    matched.SUITE_SCHEMA,
    matched.ARTIFACT_SCHEMA_VERSION,
    "canonical-json",
    matched_validator.EXPECTED_SUITE_CANONICAL_BYTES,
    matched_validator.EXPECTED_SUITE_SHA256,
)


def _pin_from_frozen_tuple(value):
    kind, schema, version, framing, canonical_bytes, sha256 = value
    return _pin(
        artifact_kind=kind,
        artifact_schema=schema,
        artifact_schema_version=version,
        body_framing=framing,
        canonical_bytes=canonical_bytes,
        sha256=sha256,
    )


def _source_semantic_suite_pin():
    return _pin_from_frozen_tuple(_SOURCE_SEMANTIC_SUITE_PIN_TUPLE)


def _effective_suite_pin():
    return _pin_from_frozen_tuple(_EFFECTIVE_SUITE_PIN_TUPLE)


def _matched_suite_pin():
    return _pin_from_frozen_tuple(_MATCHED_SUITE_PIN_TUPLE)


def _upstream_suite_pins():
    return [
        _source_semantic_suite_pin(),
        _effective_suite_pin(),
        _matched_suite_pin(),
    ]


# Detached convenience exports.  Internal validation never trusts these
# mutable module attributes; it rebuilds fresh dictionaries from tuples above.
SOURCE_SEMANTIC_SUITE_PIN = _source_semantic_suite_pin()
EFFECTIVE_SUITE_PIN = _effective_suite_pin()
MATCHED_SUITE_PIN = _matched_suite_pin()


def _artifact_pin(value, *, canonicalizer, maximum):
    try:
        raw = canonicalizer(value)
    except Exception as error:
        raise PersonaV2SemanticProjectionDerivationInventoryValidationError(
            "upstream artifact canonicalization failed"
        ) from error
    if type(raw) is not bytes or not raw or len(raw) > maximum:
        _fail("upstream artifact canonicalizer violated its byte contract")
    return _pin(
        artifact_kind=value["artifact_kind"],
        artifact_schema=value["artifact_schema"],
        artifact_schema_version=value["artifact_schema_version"],
        body_framing="canonical-json",
        canonical_bytes=len(raw),
        sha256=_sha256(raw),
    )


def _owner_from_generic(pin, *, coordinates, owner_id, owner_role):
    return _owner_pin(
        artifact_kind=pin["artifact_kind"],
        artifact_schema=pin["artifact_schema"],
        artifact_schema_version=pin["artifact_schema_version"],
        body_framing=pin["body_framing"],
        canonical_bytes=pin["canonical_bytes"],
        coordinates=coordinates,
        owner_id=owner_id,
        owner_role=owner_role,
        sha256=pin["sha256"],
    )


def _owner_expected_generic_pin(owner):
    return {key: copy.deepcopy(owner[key]) for key in GENERIC_PIN_FIELDS}


def _current_full_owner_pin(owner):
    """Rebuild one receipt-selected full owner without using local caches."""

    schema = owner["artifact_schema"]
    coordinates = owner["coordinates"]
    try:
        if schema == source_semantic.SUITE_ARTIFACT_SCHEMA:
            value = source_semantic.build_source_semantic_membership_suite_descriptor()
            return _artifact_pin(
                value,
                canonicalizer=source_semantic.canonical_json_bytes,
                maximum=source_semantic.MAX_SUITE_DESCRIPTOR_BYTES,
            )
        if schema == source_semantic.ORIGIN_ARTIFACT_SCHEMA:
            value = source_semantic.build_source_semantic_membership_origin_manifest(
                coordinates["persona_id"], coordinates["origin"]
            )
            return _artifact_pin(
                value,
                canonicalizer=source_semantic.canonical_json_bytes,
                maximum=source_semantic.MAX_ORIGIN_MANIFEST_BYTES,
            )
        if schema == effective.SUITE_SCHEMA:
            value = effective.build_lifecycle_effective_membership_suite_descriptor()
            return _artifact_pin(
                value,
                canonicalizer=effective.canonical_json_bytes,
                maximum=effective.MAX_SUITE_DESCRIPTOR_BYTES,
            )
        if schema == matched.SUITE_SCHEMA:
            value = matched.build_source_matched_lifecycle_suite_descriptor()
            return _artifact_pin(
                value,
                canonicalizer=matched.canonical_json_bytes,
                maximum=matched.MAX_SUITE_BYTES,
            )
        if schema == matched.PERSONA_SCHEMA:
            value = matched.build_source_matched_lifecycle_persona(
                coordinates["persona_id"]
            )
            return _artifact_pin(
                value,
                canonicalizer=matched.canonical_json_bytes,
                maximum=matched.MAX_PERSONA_BYTES,
            )
    except PersonaV2SemanticProjectionDerivationInventoryValidationError:
        raise
    except Exception as error:
        raise PersonaV2SemanticProjectionDerivationInventoryValidationError(
            "full owner closing rebuild failed"
        ) from error
    _fail("full owner closing rebuild received an unknown schema")


def _reauthenticate_receipt_full_owners(receipt):
    for owner in receipt["full_owner_pins"]:
        current = _current_full_owner_pin(owner)
        expected = _owner_expected_generic_pin(owner)
        if not _strict_equal(current, expected):
            _fail("upstream full owner mutated during projection provider callbacks")


def _current_direct_body(receipt, direct_pin):
    """Rebuild one role-dispatched direct owner body from public upstream APIs."""

    role = direct_pin["direct_pin_role"]
    coordinates = receipt["coordinates"]
    persona_id = coordinates["persona_id"]
    try:
        if role == "suite-origin-binding-row":
            suite = source_semantic.build_source_semantic_membership_suite_descriptor()
            row = _only_row(
                suite["origin_manifest_bindings"],
                label="closing source semantic suite origin binding",
                predicate=lambda item: (
                    item.get("persona_id") == persona_id
                    and item.get("origin") == coordinates["origin"]
                ),
            )
            return _canonical(
                row,
                label="closing source semantic suite origin binding",
                maximum=MAX_SUITE_BYTES,
            )
        if role == "compact-origin-owner-body":
            return source_semantic.source_semantic_membership_origin_body_bytes(
                persona_id, coordinates["origin"]
            )
        if role == "matching-shard-total-projection-receipt":
            rows = [
                row
                for row in source_semantic.iter_source_semantic_membership_origin_rows(
                    persona_id, coordinates["origin"]
                )
                if row.get("row_kind") == "source-shard-total-projection"
            ]
            ordinal = coordinates["source_shard_ordinal"]
            if ordinal > len(rows):
                _fail("closing source semantic range row is missing")
            row = rows[ordinal - 1]
            if row.get("source_shard_id") != coordinates["source_shard_id"]:
                _fail("closing source semantic range row coordinate drifted")
            return _canonical(
                row,
                label="closing source semantic shard total-projection receipt",
                maximum=MAX_SUITE_BYTES,
            )
        if role == "suite-direct-projection-binding-row":
            suite = effective.build_lifecycle_effective_membership_suite_descriptor()
            row = _only_row(
                suite["content_projection_bindings"],
                label="closing effective-membership projection binding",
                predicate=lambda item: item.get("persona_id") == persona_id,
            )
            return _canonical(
                row,
                label="closing effective-membership projection binding",
                maximum=MAX_SUITE_BYTES,
            )
        if role == "suite-persona-binding-row":
            suite = matched.build_source_matched_lifecycle_suite_descriptor()
            row = _only_row(
                suite["persona_bindings"],
                label="closing source-matched persona binding",
                predicate=lambda item: item.get("persona_id") == persona_id,
            )
            return _canonical(
                row,
                label="closing source-matched persona binding",
                maximum=MAX_SUITE_BYTES,
            )
        if role == "persona-event-receipt-row":
            persona = matched.build_source_matched_lifecycle_persona(persona_id)
            return _canonical(
                persona["event_receipt"],
                label="closing source-matched persona event receipt",
                maximum=MAX_SUITE_BYTES,
            )
        if role == "receipt-authenticated-event-jsonl-body":
            return matched.source_matched_lifecycle_event_body_bytes(persona_id)
    except PersonaV2SemanticProjectionDerivationInventoryValidationError:
        raise
    except Exception as error:
        raise PersonaV2SemanticProjectionDerivationInventoryValidationError(
            "direct owner closing rebuild failed"
        ) from error
    _fail("direct owner closing rebuild received an unknown role")


def _reauthenticate_receipt_direct_pins(receipt):
    for direct_pin in receipt["direct_body_pins"]:
        raw = _current_direct_body(receipt, direct_pin)
        if type(raw) is not bytes:
            _fail("direct owner closing provider must return exact built-in bytes")
        if (
            len(raw) != direct_pin["canonical_bytes"]
            or not hmac.compare_digest(_sha256(raw), direct_pin["sha256"])
        ):
            _fail("upstream direct owner mutated during projection provider callbacks")


def _reauthenticate_receipt_owner_chain(receipt):
    _reauthenticate_receipt_full_owners(receipt)
    _reauthenticate_receipt_direct_pins(receipt)


def _reauthenticate_all_full_owners(receipts):
    seen = set()
    for receipt in receipts:
        for owner in receipt["full_owner_pins"]:
            key = (
                owner["artifact_schema"],
                json.dumps(
                    owner["coordinates"],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                owner["canonical_bytes"],
                owner["sha256"],
            )
            if key in seen:
                continue
            seen.add(key)
            current = _current_full_owner_pin(owner)
            expected = _owner_expected_generic_pin(owner)
            if not _strict_equal(current, expected):
                _fail("upstream full owner mutated during inventory validation")


def _reauthenticate_all_owner_chains(receipts):
    _reauthenticate_all_full_owners(receipts)
    seen = set()
    for receipt in receipts:
        for direct_pin in receipt["direct_body_pins"]:
            key = (
                direct_pin["direct_pin_id"],
                direct_pin["canonical_bytes"],
                direct_pin["sha256"],
            )
            if key in seen:
                continue
            seen.add(key)
            raw = _current_direct_body(receipt, direct_pin)
            if type(raw) is not bytes:
                _fail("direct owner closing provider must return exact built-in bytes")
            if (
                len(raw) != direct_pin["canonical_bytes"]
                or not hmac.compare_digest(_sha256(raw), direct_pin["sha256"])
            ):
                _fail("upstream direct owner mutated during inventory validation")


def _require_frozen_pin(actual, expected, *, label):
    if not _strict_equal(actual, expected):
        _fail(f"{label} differs from its frozen independently accepted pin")


@functools.lru_cache(maxsize=1)
def _source_semantic_suite_raw():
    value = source_semantic.build_source_semantic_membership_suite_descriptor()
    _require_frozen_pin(
        _artifact_pin(
            value,
            canonicalizer=source_semantic.canonical_json_bytes,
            maximum=source_semantic.MAX_SUITE_DESCRIPTOR_BYTES,
        ),
        _source_semantic_suite_pin(),
        label="source semantic membership suite",
    )
    return source_semantic.canonical_json_bytes(value)


def _source_semantic_suite():
    value = _strict_json_loads(
        _source_semantic_suite_raw(),
        label="source semantic membership suite",
    )
    if type(value) is not dict:
        _fail("source semantic membership suite must be an object")
    return value


def _independently_validate_source_semantic_package(suite, origin_values):
    """Run the existing producer-independent package validator exactly once."""

    catalog = source_semantic.build_source_semantic_membership_catalog()
    profiles = [
        source_semantic.build_source_semantic_membership_profile_manifest(
            persona_id, profile
        )
        for persona_id in envelope.PERSONA_IDS
        for profile in source_semantic.PROFILE_ORDER
    ]
    source_suite = source_inventory.build_source_intent_suite_descriptor()
    source_origins = [
        source_inventory.build_source_intent_origin_manifest(persona_id, origin)
        for persona_id in envelope.PERSONA_IDS
        for origin in source_inventory.ORIGIN_ORDER
    ]
    source_profiles = [
        source_inventory.build_source_intent_profile_manifest(persona_id, profile)
        for persona_id in envelope.PERSONA_IDS
        for profile in source_inventory.PROFILE_ORDER
    ]
    try:
        result = source_semantic_validator.validate_source_semantic_membership_package(
            catalog,
            suite,
            origin_values,
            profiles,
            source_semantic.source_semantic_membership_origin_body_bytes,
            source_semantic.expanded_content_context_shard_body_bytes,
            source_semantic.expanded_fact_membership_shard_body_bytes,
            source_suite=source_suite,
            source_origin_manifests=source_origins,
            source_profile_manifests=source_profiles,
            source_shard_body_provider=source_inventory.source_intent_shard_body_bytes,
        )
    except Exception as error:
        raise PersonaV2SemanticProjectionDerivationInventoryValidationError(
            "independent source semantic package validation failed"
        ) from error
    if result is not True:
        _fail("independent source semantic package validator did not return True")


@functools.lru_cache(maxsize=1)
def _effective_suite_raw():
    value = effective.build_lifecycle_effective_membership_suite_descriptor()
    try:
        result = effective_validator.validate_lifecycle_effective_membership_suite_descriptor(
            value,
            origin_manifest_provider=effective.build_lifecycle_effective_membership_origin_manifest,
            profile_manifest_provider=effective.build_lifecycle_effective_membership_profile_manifest,
            compact_body_provider=effective.lifecycle_effective_membership_origin_body_bytes,
            expanded_w0_body_provider=effective.expanded_effective_w0_membership_shard_body_bytes,
            event_lineage_provider=effective.lifecycle_effective_membership_event_created_lineage_body_bytes,
            inverted_provider=effective.lifecycle_effective_membership_inverted_witness_body_bytes,
            content_projection_provider=effective.build_lifecycle_effective_membership_content_projection,
        )
    except Exception as error:
        raise PersonaV2SemanticProjectionDerivationInventoryValidationError(
            "effective-membership suite validation failed"
        ) from error
    if result is not True:
        _fail("effective-membership suite validator did not return True")
    _require_frozen_pin(
        _artifact_pin(
            value,
            canonicalizer=effective.canonical_json_bytes,
            maximum=effective.MAX_SUITE_DESCRIPTOR_BYTES,
        ),
        _effective_suite_pin(),
        label="effective-membership suite",
    )
    return effective.canonical_json_bytes(value)


def _effective_suite():
    value = _strict_json_loads(
        _effective_suite_raw(),
        label="effective-membership suite",
    )
    if type(value) is not dict:
        _fail("effective-membership suite must be an object")
    return value


@functools.lru_cache(maxsize=1)
def _matched_suite_raw():
    value = matched.build_source_matched_lifecycle_suite_descriptor()
    try:
        result = matched_validator.validate_source_matched_lifecycle_suite_descriptor(
            value
        )
    except Exception as error:
        raise PersonaV2SemanticProjectionDerivationInventoryValidationError(
            "source-matched lifecycle suite validation failed"
        ) from error
    if result is not True:
        _fail("source-matched lifecycle suite validator did not return True")
    _require_frozen_pin(
        _artifact_pin(
            value,
            canonicalizer=matched.canonical_json_bytes,
            maximum=matched.MAX_SUITE_BYTES,
        ),
        _matched_suite_pin(),
        label="source-matched lifecycle suite",
    )
    return matched.canonical_json_bytes(value)


def _matched_suite():
    value = _strict_json_loads(
        _matched_suite_raw(),
        label="source-matched lifecycle suite",
    )
    if type(value) is not dict:
        _fail("source-matched lifecycle suite must be an object")
    return value


def _only_row(rows, *, label, predicate):
    if type(rows) is not list:
        _fail(f"{label} owner rows must be a list")
    matches = [row for row in rows if predicate(row)]
    if len(matches) != 1:
        _fail(f"{label} must resolve exactly one owner row")
    return matches[0]


def _receipt(
    *, coordinates, direct_body_pins, full_owner_pins,
    projection_class_id, projection_pin, projector_id, receipt_id
):
    return {
        "coordinates": copy.deepcopy(coordinates),
        "direct_body_pins": copy.deepcopy(direct_body_pins),
        "full_owner_pins": copy.deepcopy(full_owner_pins),
        "projection_class_id": projection_class_id,
        "projection_pin": copy.deepcopy(projection_pin),
        "projector": {
            "projector_id": projector_id,
            "projector_version": 1,
        },
        "receipt_id": receipt_id,
        "row_kind": "semantic-projection-derivation-receipt",
        "row_schema": "kio.persona.pc-semantic-projection-derivation-receipt/v1",
        "validation": {
            "independent_derivation_validation_required": True,
            "projection_pin_matches_external_body": True,
            "upstream_owner_validation_result": True,
            "upstream_projection_validation_result": True,
        },
    }


def _expected_base_receipts():
    suite_owner = _owner_from_generic(
        _source_semantic_suite_pin(),
        coordinates={},
        owner_id="persona-v2-source-semantic-membership-suite",
        owner_role="full-suite-owner-pin",
    )
    receipts = []
    origin_values = []
    origin_pins = {}
    total_rows = 0
    total_bytes = 0
    for persona_id in envelope.PERSONA_IDS:
        for origin in source_semantic.ORIGIN_ORDER:
            origin_value = source_semantic.build_source_semantic_membership_origin_manifest(
                persona_id, origin
            )
            origin_values.append(origin_value)
            origin_pin = _artifact_pin(
                origin_value,
                canonicalizer=source_semantic.canonical_json_bytes,
                maximum=source_semantic.MAX_ORIGIN_MANIFEST_BYTES,
            )
            origin_pins[(persona_id, origin)] = origin_pin
            origin_owner = _owner_from_generic(
                origin_pin,
                coordinates={"origin": origin, "persona_id": persona_id},
                owner_id=(
                    f"persona-v2-source-semantic-membership-origin-{persona_id}-{origin}"
                ),
                owner_role="full-origin-owner-pin",
            )
            compact_body = source_semantic.source_semantic_membership_origin_body_bytes(
                persona_id, origin
            )
            range_rows = [
                row
                for row in source_semantic.iter_source_semantic_membership_origin_rows(
                    persona_id, origin
                )
                if row["row_kind"] == "source-shard-total-projection"
            ]
            for source_shard_ordinal, range_row in enumerate(range_rows, start=1):
                body = source_semantic.expanded_content_context_shard_body_bytes(
                    persona_id, origin, source_shard_ordinal
                )
                if (
                    len(body) != range_row["expanded_content_context_body_bytes"]
                    or not hmac.compare_digest(
                        _sha256(body),
                        range_row["expanded_content_context_sha256"],
                    )
                ):
                    _fail("base projection differs from authenticated owner receipt")
                total_rows += range_row["row_count"]
                total_bytes += len(body)
                range_raw = _canonical(
                    range_row,
                    label="source semantic shard total-projection receipt",
                    maximum=MAX_SUITE_BYTES,
                )
                receipts.append(
                    _receipt(
                        coordinates={
                            "origin": origin,
                            "persona_id": persona_id,
                            "source_shard_id": range_row["source_shard_id"],
                            "source_shard_ordinal": source_shard_ordinal,
                        },
                        direct_body_pins=[
                            _direct_pin(
                                body_framing="canonical-jsonl-lf",
                                canonical_bytes=len(compact_body),
                                direct_pin_id=(
                                    f"source-semantic-compact-origin-body-{persona_id}-{origin}"
                                ),
                                direct_pin_role="compact-origin-owner-body",
                                sha256=_sha256(compact_body),
                            ),
                            _direct_pin(
                                body_framing="canonical-json",
                                canonical_bytes=len(range_raw),
                                direct_pin_id=(
                                    "source-semantic-total-projection-receipt-"
                                    f"{persona_id}-{origin}-{source_shard_ordinal:03d}"
                                ),
                                direct_pin_role="matching-shard-total-projection-receipt",
                                sha256=_sha256(range_raw),
                            ),
                        ],
                        full_owner_pins=[suite_owner, origin_owner],
                        projection_class_id=BASE_CLASS,
                        projection_pin=_pin(
                            artifact_kind=BASE_PROJECTION_KIND,
                            artifact_schema=BASE_PROJECTION_SCHEMA,
                            artifact_schema_version=ARTIFACT_SCHEMA_VERSION,
                            body_framing="canonical-jsonl-lf",
                            canonical_bytes=len(body),
                            sha256=_sha256(body),
                        ),
                        projector_id="base-source-content-context-shard-projector",
                        receipt_id=(
                            "projection-derivation-base-content-context-"
                            f"{persona_id}-{origin}-{source_shard_ordinal:03d}"
                        ),
                    )
                )
    if (
        len(receipts) != EXPECTED_BASE_RECEIPT_COUNT
        or total_rows != EXPECTED_BASE_ROW_COUNT
        or total_bytes != EXPECTED_BASE_BODY_BYTES
    ):
        _fail("base projection receipt aggregate drifted")
    # Build the suite only after consuming all 73 projections.  Its upstream
    # implementation deliberately releases generation caches, so doing this
    # first would force a second cold origin expansion.
    source_suite = _source_semantic_suite()
    _independently_validate_source_semantic_package(source_suite, origin_values)
    origin_binding_by_coordinate = {
        (row["persona_id"], row["origin"]): row
        for row in source_suite["origin_manifest_bindings"]
    }
    if len(origin_binding_by_coordinate) != 40:
        _fail("source semantic suite origin binding cardinality drifted")
    for receipt in receipts:
        coordinates = receipt["coordinates"]
        persona_id = coordinates["persona_id"]
        origin = coordinates["origin"]
        suite_binding = origin_binding_by_coordinate.get((persona_id, origin))
        origin_pin = origin_pins[(persona_id, origin)]
        if (
            type(suite_binding) is not dict
            or suite_binding.get("artifact_kind") != origin_pin["artifact_kind"]
            or suite_binding.get("artifact_schema") != origin_pin["artifact_schema"]
            or suite_binding.get("artifact_schema_version")
            != origin_pin["artifact_schema_version"]
            or suite_binding.get("canonical_bytes") != origin_pin["canonical_bytes"]
            or suite_binding.get("sha256") != origin_pin["sha256"]
        ):
            _fail("source semantic suite-to-origin owner chain drifted")
        binding_raw = _canonical(
            suite_binding,
            label="source semantic suite origin binding",
            maximum=MAX_SUITE_BYTES,
        )
        receipt["direct_body_pins"].insert(
            0,
            _direct_pin(
                body_framing="canonical-json",
                canonical_bytes=len(binding_raw),
                direct_pin_id=(
                    f"source-semantic-suite-origin-binding-{persona_id}-{origin}"
                ),
                direct_pin_role="suite-origin-binding-row",
                sha256=_sha256(binding_raw),
            ),
        )
    return receipts


def _expected_effective_receipts():
    suite = _effective_suite()
    suite_owner = _owner_from_generic(
        _effective_suite_pin(),
        coordinates={},
        owner_id="persona-v2-lifecycle-effective-membership-suite",
        owner_role="full-suite-and-direct-projection-owner-pin",
    )
    receipts = []
    for persona_id in envelope.PERSONA_IDS:
        projection = effective.build_lifecycle_effective_membership_content_projection(
            persona_id
        )
        try:
            result = effective_validator.validate_lifecycle_effective_membership_content_projection(
                persona_id, projection
            )
        except Exception as error:
            raise PersonaV2SemanticProjectionDerivationInventoryValidationError(
                "independent effective projection reconstruction failed"
            ) from error
        if result is not True:
            _fail("independent effective projection validator did not return True")
        body = effective.canonical_json_bytes(projection)
        binding = _only_row(
            suite["content_projection_bindings"],
            label="effective-membership suite content-projection binding",
            predicate=lambda row, p=persona_id: row.get("persona_id") == p,
        )
        if (
            binding.get("canonical_bytes") != len(body)
            or binding.get("sha256") != _sha256(body)
            or binding.get("artifact_schema") != effective.PROJECTION_SCHEMA
            or binding.get("artifact_kind") != effective.PROJECTION_KIND
            or binding.get("artifact_schema_version")
            != effective.ARTIFACT_SCHEMA_VERSION
        ):
            _fail("effective suite-to-projection owner chain drifted")
        binding_raw = _canonical(
            binding,
            label="effective-membership suite projection binding",
            maximum=MAX_SUITE_BYTES,
        )
        receipts.append(
            _receipt(
                coordinates={"persona_id": persona_id},
                direct_body_pins=[
                    _direct_pin(
                        body_framing="canonical-json",
                        canonical_bytes=len(binding_raw),
                        direct_pin_id=(
                            f"effective-membership-suite-projection-binding-{persona_id}"
                        ),
                        direct_pin_role="suite-direct-projection-binding-row",
                        sha256=_sha256(binding_raw),
                    )
                ],
                full_owner_pins=[suite_owner],
                projection_class_id=EFFECTIVE_CLASS,
                projection_pin=_artifact_pin(
                    projection,
                    canonicalizer=effective.canonical_json_bytes,
                    maximum=MAX_LIFECYCLE_BODY_BYTES,
                ),
                projector_id="lifecycle-effective-membership-content-projector",
                receipt_id=f"projection-derivation-effective-membership-{persona_id}",
            )
        )
    if len(receipts) != EXPECTED_EFFECTIVE_RECEIPT_COUNT:
        _fail("effective-membership receipt cardinality drifted")
    return receipts


def _expected_matched_receipts():
    suite = _matched_suite()
    suite_owner = _owner_from_generic(
        _matched_suite_pin(),
        coordinates={},
        owner_id="persona-v2-source-matched-lifecycle-suite",
        owner_role="full-suite-containing-persona-binding-pin",
    )
    receipts = []
    for persona_id in envelope.PERSONA_IDS:
        persona = matched.build_source_matched_lifecycle_persona(persona_id)
        try:
            result = matched_validator.validate_source_matched_lifecycle_persona(
                persona_id,
                persona,
                event_body_provider=matched.source_matched_lifecycle_event_body_bytes,
            )
        except Exception as error:
            raise PersonaV2SemanticProjectionDerivationInventoryValidationError(
                "independent source-matched persona owner validation failed"
            ) from error
        if result is not True:
            _fail("independent source-matched persona validator did not return True")
        persona_pin = _artifact_pin(
            persona,
            canonicalizer=matched.canonical_json_bytes,
            maximum=matched.MAX_PERSONA_BYTES,
        )
        persona_owner = _owner_from_generic(
            persona_pin,
            coordinates={"persona_id": persona_id},
            owner_id=f"persona-v2-source-matched-lifecycle-persona-{persona_id}",
            owner_role="full-persona-projection-and-event-receipt-owner-pin",
        )
        persona_binding = _only_row(
            suite["persona_bindings"],
            label="source-matched lifecycle suite persona binding",
            predicate=lambda row, p=persona_id: row.get("persona_id") == p,
        )
        if (
            persona_binding.get("canonical_bytes") != persona_pin["canonical_bytes"]
            or persona_binding.get("sha256") != persona_pin["sha256"]
            or persona_binding.get("artifact_schema") != matched.PERSONA_SCHEMA
            or persona_binding.get("artifact_kind") != matched.PERSONA_KIND
            or persona_binding.get("artifact_schema_version")
            != matched.ARTIFACT_SCHEMA_VERSION
        ):
            _fail("source-matched suite-to-persona owner chain drifted")
        persona_binding_raw = _canonical(
            persona_binding,
            label="source-matched lifecycle suite persona binding",
            maximum=MAX_SUITE_BYTES,
        )
        event_receipt_raw = _canonical(
            persona["event_receipt"],
            label="source-matched lifecycle event receipt",
            maximum=MAX_SUITE_BYTES,
        )
        event_body = matched.source_matched_lifecycle_event_body_bytes(persona_id)
        if (
            persona["event_receipt"]["body_bytes"] != len(event_body)
            or not hmac.compare_digest(
                persona["event_receipt"]["body_sha256"],
                _sha256(event_body),
            )
        ):
            _fail("source-matched event body differs from persona owner receipt")
        projection = matched.build_source_matched_lifecycle_content_projection(
            persona_id
        )
        try:
            result = matched_validator.validate_source_matched_lifecycle_content_projection(
                persona_id, projection
            )
        except Exception as error:
            raise PersonaV2SemanticProjectionDerivationInventoryValidationError(
                "independent source-matched projection reconstruction failed"
            ) from error
        if result is not True:
            _fail("independent source-matched projection validator did not return True")
        receipts.append(
            _receipt(
                coordinates={"persona_id": persona_id},
                direct_body_pins=[
                    _direct_pin(
                        body_framing="canonical-json",
                        canonical_bytes=len(persona_binding_raw),
                        direct_pin_id=f"source-matched-suite-persona-binding-{persona_id}",
                        direct_pin_role="suite-persona-binding-row",
                        sha256=_sha256(persona_binding_raw),
                    ),
                    _direct_pin(
                        body_framing="canonical-json",
                        canonical_bytes=len(event_receipt_raw),
                        direct_pin_id=f"source-matched-persona-event-receipt-{persona_id}",
                        direct_pin_role="persona-event-receipt-row",
                        sha256=_sha256(event_receipt_raw),
                    ),
                    _direct_pin(
                        body_framing="canonical-jsonl-lf",
                        canonical_bytes=len(event_body),
                        direct_pin_id=f"source-matched-event-body-{persona_id}",
                        direct_pin_role="receipt-authenticated-event-jsonl-body",
                        sha256=_sha256(event_body),
                    ),
                ],
                full_owner_pins=[suite_owner, persona_owner],
                projection_class_id=MATCHED_CLASS,
                projection_pin=_artifact_pin(
                    projection,
                    canonicalizer=matched.canonical_json_bytes,
                    maximum=MAX_LIFECYCLE_BODY_BYTES,
                ),
                projector_id="source-matched-lifecycle-content-projector",
                receipt_id=f"projection-derivation-lifecycle-rules-{persona_id}",
            )
        )
    if len(receipts) != EXPECTED_MATCHED_RECEIPT_COUNT:
        _fail("source-matched lifecycle receipt cardinality drifted")
    return receipts


def _projection_class_registry():
    counts = {
        BASE_CLASS: EXPECTED_BASE_RECEIPT_COUNT,
        EFFECTIVE_CLASS: EXPECTED_EFFECTIVE_RECEIPT_COUNT,
        MATCHED_CLASS: EXPECTED_MATCHED_RECEIPT_COUNT,
    }
    return [
        {
            "coverage_status": (
                "covered-local-derivation"
                if projection_class_id in counts
                else "missing-required-projection"
            ),
            "derivation_receipt_count": counts.get(projection_class_id, 0),
            "inventory_ordinal": ordinal,
            "projection_class_id": projection_class_id,
        }
        for ordinal, projection_class_id in enumerate(
            PROJECTION_CLASS_ORDER, start=1
        )
    ]


def _missing_projection_class_ledger():
    return [
        {
            "blocker_id": f"missing-semantic-projection-{projection_class_id}",
            "projection_class_id": projection_class_id,
            "required_for_minimum_inventory": True,
            "status": "active-g0",
        }
        for projection_class_id in MISSING_CLASS_ORDER
    ]


EXPECTED_CANONICAL_LIMITS = {
    "external_projection_bodies_embedded": False,
    "max_cumulative_external_projection_bytes": MAX_CUMULATIVE_EXTERNAL_BODY_BYTES,
    "max_json_projection_bytes": MAX_LIFECYCLE_BODY_BYTES,
    "max_jsonl_projection_bytes": MAX_BASE_BODY_BYTES,
    "max_jsonl_projection_row_bytes_including_lf": MAX_BASE_ROW_BYTES_INCLUDING_LF,
    "max_jsonl_projection_rows": MAX_BASE_ROWS,
    "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
    "max_receipt_count": EXPECTED_RECEIPT_COUNT,
    "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
    "max_suite_bytes": MAX_SUITE_BYTES,
    "self_hash_embedded": False,
    "target_json_projection_bytes": TARGET_LIFECYCLE_BODY_BYTES,
    "unicode_normalization": "NFC",
}
EXPECTED_COMPLETION_CLAIMS = {
    "all_113_receipts_bound": True,
    "corpus_semantic_namespace_issued": False,
    "future_source_id_namespace_eligible": False,
    "local_three_class_derivation_complete": True,
    "minimum_projection_inventory_complete": False,
    "query_semantics_absence_proved": False,
    "semantic_payload_projection_bound": False,
}
EXPECTED_ORDERS = {
    "covered_projection_classes": list(COVERED_CLASS_ORDER),
    "derivation_receipts": (
        "base-content-context-persona-origin-shard-then-effective-"
        "membership-persona-then-source-matched-lifecycle-persona"
    ),
    "minimum_projection_classes": list(PROJECTION_CLASS_ORDER),
    "persona": list(envelope.PERSONA_IDS),
    "upstream_suite_bindings": [
        "source-semantic-membership",
        "lifecycle-effective-membership",
        "source-matched-lifecycle",
    ],
}
EXPECTED_REMAINING_BLOCKERS = [
    "nine-minimum-semantic-projection-classes-not-derived",
    "complete-independent-projection-derivation-validation-not-yet-authoritative",
    "corpus-semantic-namespace-not-issued",
    "corpus-input-closure-and-blocker-resolution-ledger-not-complete",
    "joint-solver-solution-proof-and-final-source-plan-not-built",
    "compiled-history-physical-materialization-capacity-kio-and-g0-not-observed",
]


def _validate_pin_shape(pin, *, fields, label):
    if type(pin) is not dict or set(pin) != fields:
        _fail(f"{label} field schema drifted")
    canonical_bytes = pin.get("canonical_bytes")
    if (
        type(canonical_bytes) is not int
        or type(canonical_bytes) is bool
        or canonical_bytes <= 0
    ):
        _fail(f"{label} canonical_bytes must be one positive exact integer")
    _require_sha256(pin.get("sha256"), label=f"{label} sha256")
    if pin.get("body_framing") not in {"canonical-json", "canonical-jsonl-lf"}:
        _fail(f"{label} has an unknown body framing")
    if "artifact_kind" in fields:
        if (
            type(pin.get("artifact_kind")) is not str
            or not pin["artifact_kind"]
            or type(pin.get("artifact_schema")) is not str
            or not pin["artifact_schema"]
            or type(pin.get("artifact_schema_version")) is not int
            or type(pin.get("artifact_schema_version")) is bool
            or pin["artifact_schema_version"] <= 0
        ):
            _fail(f"{label} artifact identity must use exact built-in values")


def _prevalidate_receipts(receipts):
    if type(receipts) is not list or len(receipts) != EXPECTED_RECEIPT_COUNT:
        _fail("inventory must contain exactly 113 derivation receipts")
    expected_classes = (
        [BASE_CLASS] * EXPECTED_BASE_RECEIPT_COUNT
        + [EFFECTIVE_CLASS] * EXPECTED_EFFECTIVE_RECEIPT_COUNT
        + [MATCHED_CLASS] * EXPECTED_MATCHED_RECEIPT_COUNT
    )
    receipt_ids = []
    coordinate_keys = []
    projection_pin_keys = []
    cumulative_bytes = 0
    for ordinal, (receipt, expected_class) in enumerate(
        zip(receipts, expected_classes, strict=True), start=1
    ):
        if type(receipt) is not dict or set(receipt) != RECEIPT_FIELDS:
            _fail("projection derivation receipt field schema drifted")
        if receipt.get("projection_class_id") != expected_class:
            _fail("projection derivation receipt class/order drifted")
        if receipt.get("row_kind") != "semantic-projection-derivation-receipt" or receipt.get(
            "row_schema"
        ) != "kio.persona.pc-semantic-projection-derivation-receipt/v1":
            _fail("projection derivation receipt row identity drifted")
        receipt_id = receipt.get("receipt_id")
        if type(receipt_id) is not str or not receipt_id:
            _fail("projection derivation receipt ID must be a nonempty string")
        receipt_ids.append(receipt_id)
        coordinates = receipt.get("coordinates")
        if type(coordinates) is not dict:
            _fail("projection derivation coordinates must be an object")
        persona_id = coordinates.get("persona_id")
        if persona_id not in envelope.PERSONA_IDS:
            _fail("projection derivation receipt contains a foreign persona")
        if expected_class == BASE_CLASS:
            if set(coordinates) != {
                "origin",
                "persona_id",
                "source_shard_id",
                "source_shard_ordinal",
            }:
                _fail("base projection coordinate schema drifted")
            if coordinates["origin"] not in source_semantic.ORIGIN_ORDER:
                _fail("base projection origin is foreign")
            if (
                type(coordinates["source_shard_id"]) is not str
                or not coordinates["source_shard_id"]
                or type(coordinates["source_shard_ordinal"]) is not int
                or type(coordinates["source_shard_ordinal"]) is bool
                or coordinates["source_shard_ordinal"] <= 0
            ):
                _fail("base projection shard coordinate is invalid")
            expected_receipt_id = (
                "projection-derivation-base-content-context-"
                f"{persona_id}-{coordinates['origin']}-"
                f"{coordinates['source_shard_ordinal']:03d}"
            )
            expected_projector = "base-source-content-context-shard-projector"
            expected_projection_identity = (
                BASE_PROJECTION_KIND,
                BASE_PROJECTION_SCHEMA,
                "canonical-jsonl-lf",
            )
            expected_direct_count = 3
            expected_owner_count = 2
        else:
            if set(coordinates) != {"persona_id"}:
                _fail("lifecycle projection coordinate schema drifted")
            if expected_class == EFFECTIVE_CLASS:
                expected_receipt_id = (
                    f"projection-derivation-effective-membership-{persona_id}"
                )
                expected_projector = (
                    "lifecycle-effective-membership-content-projector"
                )
                expected_projection_identity = (
                    effective.PROJECTION_KIND,
                    effective.PROJECTION_SCHEMA,
                    "canonical-json",
                )
                expected_direct_count = 1
                expected_owner_count = 1
            else:
                expected_receipt_id = (
                    f"projection-derivation-lifecycle-rules-{persona_id}"
                )
                expected_projector = "source-matched-lifecycle-content-projector"
                expected_projection_identity = (
                    matched.PROJECTION_KIND,
                    matched.PROJECTION_SCHEMA,
                    "canonical-json",
                )
                expected_direct_count = 3
                expected_owner_count = 2
        if receipt_id != expected_receipt_id:
            _fail("projection receipt ID differs from its coordinates")
        coordinate_keys.append(
            (expected_class, tuple(sorted(coordinates.items())))
        )
        projector = receipt.get("projector")
        if (
            type(projector) is not dict
            or set(projector) != PROJECTOR_FIELDS
            or projector.get("projector_id") != expected_projector
            or projector.get("projector_version") != 1
            or type(projector.get("projector_version")) is bool
        ):
            _fail("projection derivation projector identity drifted")
        validation = receipt.get("validation")
        if (
            type(validation) is not dict
            or set(validation) != VALIDATION_FIELDS
            or any(type(value) is not bool or value is not True for value in validation.values())
        ):
            _fail("projection derivation validation receipt must be exact all-true evidence")
        projection_pin = receipt.get("projection_pin")
        _validate_pin_shape(
            projection_pin,
            fields=GENERIC_PIN_FIELDS,
            label="projection pin",
        )
        expected_kind, expected_schema, expected_framing = expected_projection_identity
        if (
            projection_pin["artifact_kind"] != expected_kind
            or projection_pin["artifact_schema"] != expected_schema
            or projection_pin["artifact_schema_version"] != ARTIFACT_SCHEMA_VERSION
            or projection_pin["body_framing"] != expected_framing
        ):
            _fail("projection body identity/framing drifted")
        class_cap = (
            MAX_BASE_BODY_BYTES
            if expected_class == BASE_CLASS
            else TARGET_LIFECYCLE_BODY_BYTES
        )
        if projection_pin["canonical_bytes"] > class_cap:
            _fail("projection pin exceeds its current class byte target")
        cumulative_bytes += projection_pin["canonical_bytes"]
        projection_pin_keys.append(
            (projection_pin["sha256"], projection_pin["canonical_bytes"])
        )
        direct_pins = receipt.get("direct_body_pins")
        if type(direct_pins) is not list or len(direct_pins) != expected_direct_count:
            _fail("projection direct-body pin cardinality drifted")
        for direct_pin in direct_pins:
            _validate_pin_shape(
                direct_pin,
                fields=DIRECT_PIN_FIELDS,
                label="direct body pin",
            )
            if (
                type(direct_pin["direct_pin_id"]) is not str
                or not direct_pin["direct_pin_id"]
                or type(direct_pin["direct_pin_role"]) is not str
                or not direct_pin["direct_pin_role"]
            ):
                _fail("direct body pin identity/role is invalid")
        owners = receipt.get("full_owner_pins")
        if type(owners) is not list or len(owners) != expected_owner_count:
            _fail("projection full-owner pin cardinality drifted")
        for owner in owners:
            _validate_pin_shape(
                owner,
                fields=FULL_OWNER_PIN_FIELDS,
                label="full owner pin",
            )
            if (
                type(owner["coordinates"]) is not dict
                or type(owner["owner_id"]) is not str
                or not owner["owner_id"]
                or type(owner["owner_role"]) is not str
                or not owner["owner_role"]
                or owner["artifact_schema"] == SUITE_SCHEMA
            ):
                _fail("full owner pin identity/cycle boundary drifted")
            if (
                owner["artifact_schema"] == projection_pin["artifact_schema"]
                and owner["sha256"] == projection_pin["sha256"]
            ):
                _fail("projection derivation receipt contains an owner/projection cycle")
    if len(set(receipt_ids)) != EXPECTED_RECEIPT_COUNT:
        _fail("projection derivation receipt IDs are not unique")
    if len(set(coordinate_keys)) != EXPECTED_RECEIPT_COUNT:
        _fail("projection derivation coordinates are duplicate")
    if len(set(projection_pin_keys)) != EXPECTED_RECEIPT_COUNT:
        _fail("projection derivation receipts contain a cross-coordinate SHA alias")
    if cumulative_bytes > MAX_CUMULATIVE_EXTERNAL_BODY_BYTES:
        _fail("external projection footprint exceeds 144 MiB")
    return cumulative_bytes


def _prevalidate_inventory(snapshot):
    if set(snapshot) != TOP_LEVEL_FIELDS:
        _fail("semantic projection inventory top-level schema drifted")
    if (
        snapshot.get("artifact_kind") != SUITE_KIND
        or snapshot.get("artifact_schema") != SUITE_SCHEMA
        or snapshot.get("artifact_schema_version") != ARTIFACT_SCHEMA_VERSION
        or snapshot.get("fixture_id") != envelope.FIXTURE_ID
        or snapshot.get("fixture_schema_version") != envelope.FIXTURE_SCHEMA_VERSION
        or snapshot.get("g0_contract_frozen") is not False
        or snapshot.get("hypothesis_status")
        != "authored-benchmark-projection-derivation-evidence-not-observed-user-data"
    ):
        _fail("semantic projection inventory envelope/status drifted")
    authority = snapshot.get("authority")
    if (
        type(authority) is not dict
        or set(authority) != AUTHORITY_FIELDS
        or any(type(value) is not bool or value is not False for value in authority.values())
    ):
        _fail("semantic projection inventory must keep the exact all-false authority")
    exact_sections = (
        ("canonical_limits", EXPECTED_CANONICAL_LIMITS),
        ("completion_claims", EXPECTED_COMPLETION_CLAIMS),
        ("orders", EXPECTED_ORDERS),
        ("projection_class_registry", _projection_class_registry()),
        ("missing_projection_class_ledger", _missing_projection_class_ledger()),
        ("remaining_blockers", EXPECTED_REMAINING_BLOCKERS),
        (
            "upstream_suite_bindings",
            _upstream_suite_pins(),
        ),
    )
    for field, expected in exact_sections:
        if not _strict_equal(snapshot.get(field), expected):
            _fail(f"semantic projection inventory {field} drifted")
    cumulative_bytes = _prevalidate_receipts(snapshot.get("derivation_receipts"))
    expected_counts = {
        BASE_CLASS: EXPECTED_BASE_RECEIPT_COUNT,
        EFFECTIVE_CLASS: EXPECTED_EFFECTIVE_RECEIPT_COUNT,
        MATCHED_CLASS: EXPECTED_MATCHED_RECEIPT_COUNT,
    }
    expected_summary = {
        "covered_projection_class_count": 3,
        "cumulative_external_projection_bytes": cumulative_bytes,
        "derivation_receipt_count": EXPECTED_RECEIPT_COUNT,
        "external_projection_body_count": EXPECTED_RECEIPT_COUNT,
        "json_projection_body_count": 40,
        "jsonl_projection_body_count": 73,
        "minimum_projection_class_count": 12,
        "missing_projection_class_count": 9,
        "persona_count": 20,
        "receipt_counts_by_projection_class": expected_counts,
    }
    if not _strict_equal(snapshot.get("summary"), expected_summary):
        _fail("semantic projection inventory summary drifted")
    return cumulative_bytes


def _build_expected_inventory():
    receipts = [
        *_expected_base_receipts(),
        *_expected_effective_receipts(),
        *_expected_matched_receipts(),
    ]
    cumulative_bytes = sum(
        receipt["projection_pin"]["canonical_bytes"] for receipt in receipts
    )
    if cumulative_bytes != EXPECTED_CUMULATIVE_EXTERNAL_BODY_BYTES:
        _fail("independent external projection byte total drifted")
    class_maximum_body_bytes = {
        projection_class_id: max(
            receipt["projection_pin"]["canonical_bytes"]
            for receipt in receipts
            if receipt["projection_class_id"] == projection_class_id
        )
        for projection_class_id in COVERED_CLASS_ORDER
    }
    if class_maximum_body_bytes != dict(_EXPECTED_CLASS_MAXIMUM_BODY_BYTES):
        _fail("independent projection class maximum body bytes drifted")
    ordered_pin_rows = [
        {
            "canonical_bytes": receipt["projection_pin"]["canonical_bytes"],
            "receipt_id": receipt["receipt_id"],
            "sha256": receipt["projection_pin"]["sha256"],
        }
        for receipt in receipts
    ]
    ordered_pin_raw = _canonical(
        ordered_pin_rows,
        label="independently reconstructed ordered projection pin rows",
        maximum=MAX_SUITE_BYTES,
    )
    if _sha256(ordered_pin_raw) != EXPECTED_ORDERED_PROJECTION_PINS_SHA256:
        _fail("independent ordered projection pin digest drifted")
    counts = {
        BASE_CLASS: EXPECTED_BASE_RECEIPT_COUNT,
        EFFECTIVE_CLASS: EXPECTED_EFFECTIVE_RECEIPT_COUNT,
        MATCHED_CLASS: EXPECTED_MATCHED_RECEIPT_COUNT,
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
            "authored-benchmark-projection-derivation-evidence-not-observed-user-data"
        ),
        "missing_projection_class_ledger": _missing_projection_class_ledger(),
        "orders": copy.deepcopy(EXPECTED_ORDERS),
        "projection_class_registry": _projection_class_registry(),
        "remaining_blockers": copy.deepcopy(EXPECTED_REMAINING_BLOCKERS),
        "summary": {
            "covered_projection_class_count": 3,
            "cumulative_external_projection_bytes": cumulative_bytes,
            "derivation_receipt_count": EXPECTED_RECEIPT_COUNT,
            "external_projection_body_count": EXPECTED_RECEIPT_COUNT,
            "json_projection_body_count": 40,
            "jsonl_projection_body_count": 73,
            "minimum_projection_class_count": 12,
            "missing_projection_class_count": 9,
            "persona_count": 20,
            "receipt_counts_by_projection_class": counts,
        },
        "upstream_suite_bindings": _upstream_suite_pins(),
    }
    _prevalidate_inventory(value)
    raw = _canonical(
        value,
        label="independently reconstructed semantic projection inventory",
        maximum=MAX_SUITE_BYTES,
    )
    if (
        len(raw) != EXPECTED_SUITE_CANONICAL_BYTES
        or _sha256(raw) != EXPECTED_SUITE_SHA256
    ):
        _fail("independently reconstructed inventory canonical pin drifted")
    return value


@functools.lru_cache(maxsize=1)
def _expected_inventory_raw():
    return _canonical(
        _build_expected_inventory(),
        label="independently reconstructed semantic projection inventory",
        maximum=MAX_SUITE_BYTES,
    )


def _expected_inventory():
    raw = _expected_inventory_raw()
    value = _strict_json_loads(raw, label="expected semantic projection inventory")
    if type(value) is not dict:
        _fail("expected semantic projection inventory is not an object")
    return value


def validate_semantic_projection_derivation_inventory(
    value, projection_body_provider=None
):
    """Validate exact metadata, 113 bodies, deterministic replay, and TOCTOU."""

    snapshot, opening_raw = _opening_snapshot(value)
    owners_opened = False
    try:
        if (
            len(opening_raw) != EXPECTED_SUITE_CANONICAL_BYTES
            or _sha256(opening_raw) != EXPECTED_SUITE_SHA256
        ):
            _fail("inventory differs from its frozen canonical pin")
        _prevalidate_inventory(snapshot)
        provider = (
            _default_projection_body_provider
            if projection_body_provider is None
            else projection_body_provider
        )
        if not callable(provider):
            _fail("projection body provider must be callable")
        try:
            expected = _expected_inventory()
        except PersonaV2SemanticProjectionDerivationInventoryValidationError:
            raise
        except Exception as error:
            raise PersonaV2SemanticProjectionDerivationInventoryValidationError(
                "independent inventory reconstruction failed"
            ) from error
        if not hmac.compare_digest(
            _canonical(snapshot),
            _canonical(expected),
        ):
            _fail("inventory differs from complete independent reconstruction")
        _reauthenticate_all_owner_chains(snapshot["derivation_receipts"])
        owners_opened = True
        audited_bytes = 0
        for receipt in snapshot["derivation_receipts"]:
            def reauthenticate_callback(receipt=receipt):
                _reauth_target(value, opening_raw)
                _reauthenticate_receipt_owner_chain(receipt)

            audited_bytes += _authenticate_projection_body(
                provider,
                receipt,
                reauthenticate_target=reauthenticate_callback,
            )
        if (
            audited_bytes
            != snapshot["summary"]["cumulative_external_projection_bytes"]
            or audited_bytes > MAX_CUMULATIVE_EXTERNAL_BODY_BYTES
        ):
            _fail("audited external projection footprint drifted")
    finally:
        postflight_error = None
        if owners_opened:
            try:
                _reauthenticate_all_owner_chains(
                    snapshot["derivation_receipts"]
                )
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
    "BASE_PROJECTION_KIND",
    "BASE_PROJECTION_SCHEMA",
    "COVERED_CLASS_ORDER",
    "EXPECTED_BASE_BODY_BYTES",
    "EXPECTED_BASE_RECEIPT_COUNT",
    "EXPECTED_BASE_ROW_COUNT",
    "EXPECTED_CUMULATIVE_EXTERNAL_BODY_BYTES",
    "EXPECTED_EFFECTIVE_RECEIPT_COUNT",
    "EXPECTED_MATCHED_RECEIPT_COUNT",
    "EXPECTED_ORDERED_PROJECTION_PINS_SHA256",
    "EXPECTED_RECEIPT_COUNT",
    "EXPECTED_SUITE_CANONICAL_BYTES",
    "EXPECTED_SUITE_SHA256",
    "MAX_BASE_BODY_BYTES",
    "MAX_BASE_ROW_BYTES_INCLUDING_LF",
    "MAX_BASE_ROWS",
    "MAX_CUMULATIVE_EXTERNAL_BODY_BYTES",
    "MAX_LIFECYCLE_BODY_BYTES",
    "MAX_SUITE_BYTES",
    "MISSING_CLASS_ORDER",
    "PROJECTION_CLASS_ORDER",
    "PersonaV2SemanticProjectionDerivationInventoryValidationError",
    "SUITE_KIND",
    "SUITE_SCHEMA",
    "TARGET_LIFECYCLE_BODY_BYTES",
    "validate_semantic_projection_derivation_inventory",
]
