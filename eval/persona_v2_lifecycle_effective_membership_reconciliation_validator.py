"""Independent validator for lifecycle effective-membership reconciliation.

This module intentionally does not import the reconciliation producer.  It
reconstructs the sparse persisted rows and all three bounded expanded views
from the authenticated source-semantic, lifecycle-coverage, and source-matched
lifecycle inputs.  Validation remains pre-solver and non-authorizing.
"""

from __future__ import annotations

import copy
import functools
import hashlib
import hmac
import json
from collections import Counter, defaultdict

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_fact_graph as fact_graph
    from . import persona_v2_fact_graph_data as fact_graph_data
    from . import persona_v2_lifecycle_coverage_catalog as lifecycle_coverage
    from . import persona_v2_source_inventory_package as source_package
    from . import persona_v2_source_matched_lifecycle_inventory as matched_lifecycle
    from . import persona_v2_source_semantic_membership_package as source_semantic
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_fact_graph as fact_graph
    import persona_v2_fact_graph_data as fact_graph_data
    import persona_v2_lifecycle_coverage_catalog as lifecycle_coverage
    import persona_v2_source_inventory_package as source_package
    import persona_v2_source_matched_lifecycle_inventory as matched_lifecycle
    import persona_v2_source_semantic_membership_package as source_semantic


ORIGIN_SCHEMA = (
    "kio.persona.pc-lifecycle-effective-membership-origin-manifest/v1"
)
PROFILE_SCHEMA = (
    "kio.persona.pc-lifecycle-effective-membership-profile-manifest/v1"
)
SUITE_SCHEMA = "kio.persona.pc-lifecycle-effective-membership-reconciliation/v1"
PROJECTION_SCHEMA = (
    "kio.persona.pc-lifecycle-effective-membership-content-projection/v1"
)
ARTIFACT_SCHEMA_VERSION = 1

ORIGIN_KIND = "persona-pc-v2-lifecycle-effective-membership-origin-manifest"
PROFILE_KIND = "persona-pc-v2-lifecycle-effective-membership-profile-manifest"
SUITE_KIND = "persona-pc-v2-lifecycle-effective-membership-reconciliation"
PROJECTION_KIND = (
    "persona-pc-v2-lifecycle-effective-membership-content-projection"
)

ORIGIN_ORDER = ("pilot", "full-residual")
PROFILE_ORDER = ("pilot", "full")

EXPECTED_SOURCE_COUNT = 203_000
EXPECTED_SHARD_RECEIPT_COUNT = 73
EXPECTED_PRIMARY_OVERRIDE_COUNT = 2_000
EXPECTED_COMPANION_MIRROR_COUNT = 200
EXPECTED_TYPED_WITNESS_COUNT = 300
EXPECTED_COMPACT_ROW_COUNT = 2_573
EXPECTED_EVENT_CREATED_LINEAGE_COUNT = 3_630
EXPECTED_INVERTED_WITNESS_COUNT = 300
EXPECTED_INVERTED_CONSUMER_REFERENCE_COUNT = 600
EXPECTED_PRESENT_FACT_REFERENCE_COUNT = 1_033_680
EXPECTED_SUITE_CANONICAL_BYTES = 69_195
EXPECTED_SUITE_SHA256 = (
    "a624066396a534308c58cffe4f827160ea6d5f726c9507d9115e0ddb18752a29"
)
EXPECTED_MAX_ORIGIN_MANIFEST_BYTES = 5_592
EXPECTED_MAX_PROFILE_MANIFEST_BYTES = 3_301
EXPECTED_MAX_CONTENT_PROJECTION_BYTES = 103_840
EXPECTED_MAX_COMPACT_ROW_BYTES_INCLUDING_LF = 1_136
EXPECTED_MAX_EXPANDED_ROW_BYTES_INCLUDING_LF = 913
EXPECTED_MAX_EVENT_LINEAGE_ROW_BYTES_INCLUDING_LF = 571
EXPECTED_MAX_INVERTED_ROW_BYTES_INCLUDING_LF = 600
EXPECTED_P01_PILOT_COMPACT_BODY_BYTES = 127_252
EXPECTED_P01_PILOT_COMPACT_BODY_SHA256 = (
    "b4dc476b51916e67d2e6c021f9a50a319611fe3840719c5de10ba4fd26f0404d"
)
EXPECTED_P12_FULL_RESIDUAL_COMPACT_BODY_BYTES = 2_460
EXPECTED_P12_FULL_RESIDUAL_COMPACT_BODY_SHA256 = (
    "aefbfd79351fce4cd369e7fbf548db1734882e14f14ec524bb4499acc036234d"
)
EXPECTED_P01_CONTENT_PROJECTION_BYTES = 103_439
EXPECTED_P01_CONTENT_PROJECTION_SHA256 = (
    "d620a63b9762cf6119d795845c5b1533207ced29ae97fbb6ab3765a966d07f5e"
)
EXPECTED_W0_MODE_COUNTS = {
    "base-inheritance": 200_800,
    "companion-mirror": 200,
    "graph-normal-plus-witness": 300,
    "graph-normal": 1_700,
}
EXPECTED_W0_FACT_DISTRIBUTION = {
    "conflict-branch": 3_120,
    "empty": 73_350,
    "graph-normal-only": 126_130,
    "graph-normal-plus-witness": 300,
    "singleton": 100,
}

MAX_ORIGIN_BODY_BYTES = 4 * 2**20
MAX_ORIGIN_ROWS = 4_096
MAX_ORIGIN_MANIFEST_BYTES = 256 * 1024
MAX_PROFILE_MANIFEST_BYTES = 256 * 1024
MAX_SUITE_DESCRIPTOR_BYTES = 512 * 1024
MAX_CONTENT_PROJECTION_BYTES = 384 * 1024
TARGET_CONTENT_PROJECTION_BYTES = 256 * 1024
MAX_COMPACT_ROW_BYTES_INCLUDING_LF = 2_048
MAX_EXPANDED_ROW_BYTES_INCLUDING_LF = 1_024
MAX_EXPANDED_SHARD_BODY_BYTES = 4 * 2**20
MAX_EXPANDED_ROWS_PER_SHARD = 4_096
MAX_EVENT_LINEAGE_BODY_BYTES = 4 * 2**20
MAX_EVENT_LINEAGE_ROW_BYTES_INCLUDING_LF = 1_024
MAX_INVERTED_BODY_BYTES = 2 * 2**20
MAX_INVERTED_ROW_BYTES_INCLUDING_LF = 1_024

AUTHORITY_FIELDS = frozenset(
    {
        "actual_chunks_attested",
        "actual_lifecycle_receipts_attested",
        "authorizes_compiled_history_plan",
        "authorizes_final_identifiers",
        "authorizes_g0_freeze",
        "authorizes_history_mutation",
        "authorizes_kio_execution",
        "authorizes_namespace_completion",
        "authorizes_physical_write",
        "authorizes_renderer_execution",
        "authorizes_solver_execution",
        "authorizes_source_plan",
        "compiled_history_plan_available",
        "filesystem_writer_available",
        "formal_capacity_gate_satisfied",
        "history_executor_available",
        "kio_execution_available",
        "physical_materialization_observed",
        "solver_solution_available",
    }
)

SHARD_RECEIPT_ROW_FIELDS = frozenset(
    {
        "expanded_body_bytes",
        "expanded_body_persisted",
        "expanded_body_sha256",
        "expanded_maximum_row_bytes_including_lf",
        "first_intent_key",
        "last_intent_key",
        "origin",
        "persona_id",
        "row_count",
        "row_kind",
        "source_semantic_expanded_body_sha256",
        "source_shard_id",
        "source_shard_ordinal",
    }
)
PRIMARY_OVERRIDE_ROW_FIELDS = frozenset(
    {
        "base_fact_profile_id",
        "capability_class_key",
        "capability_key",
        "effective_fact_profile_id",
        "effective_membership_mode",
        "graph_id",
        "intent_key",
        "lifecycle_branch_key",
        "lifecycle_logical_document_key",
        "lifecycle_revision_chain_key",
        "logical_revision_key",
        "origin",
        "persona_id",
        "present_fact_ids",
        "row_kind",
        "semantic_section_key",
        "topic_id",
        "witness_fact_ids",
    }
)
COMPANION_MIRROR_ROW_FIELDS = frozenset(
    {
        "base_fact_profile_id",
        "companion_requirement_key",
        "effective_fact_profile_id",
        "effective_membership_mode",
        "graph_id",
        "intent_key",
        "lifecycle_branch_key",
        "lifecycle_logical_document_key",
        "lifecycle_revision_chain_key",
        "logical_revision_key",
        "origin",
        "persona_id",
        "present_fact_ids",
        "primary_capability_key",
        "primary_intent_key",
        "rendition_group_key",
        "row_kind",
        "semantic_section_key",
        "topic_id",
        "witness_fact_ids",
    }
)
TYPED_WITNESS_ROW_FIELDS = frozenset(
    {
        "capability_key",
        "fact_id",
        "graph_id",
        "origin",
        "persona_id",
        "predicate_id",
        "project_or_case_id",
        "purge_witness_key",
        "row_kind",
        "subject_entity_id",
        "suite_global_uniqueness_required",
        "typed_value",
        "visibility_by_checkpoint",
    }
)
EXPANDED_W0_ROW_FIELDS = frozenset(
    {
        "effective_membership_mode",
        "intent_key",
        "lifecycle_branch_key",
        "lifecycle_logical_document_key",
        "lifecycle_revision_chain_key",
        "logical_revision_key",
        "origin",
        "persona_id",
        "present_fact_ids",
        "present_fact_set_key",
        "projection_mode",
        "row_kind",
        "semantic_section_key",
        "witness_fact_ids",
    }
)
EVENT_LINEAGE_ROW_FIELDS = frozenset(
    {
        "after_source_intent_key",
        "capability_key",
        "consumer_role",
        "dependency_group_key",
        "event_intent_key",
        "event_profile_key",
        "event_sequence_ordinal",
        "fact_transition_rule",
        "persona_id",
        "present_purge_witness_fact_ids",
        "row_kind",
        "source_intent_key",
        "wave",
    }
)
INVERTED_WITNESS_ROW_FIELDS = frozenset(
    {
        "capability_key",
        "consumer_count",
        "consumer_refs",
        "persona_id",
        "purge_witness_key",
        "row_kind",
        "witness_fact_id",
    }
)
CONTENT_PRIMARY_ROW_FIELDS = frozenset(
    {
        "capability_key",
        "effective_membership_mode",
        "graph_id",
        "intent_key",
        "lifecycle_branch_key",
        "lifecycle_logical_document_key",
        "lifecycle_revision_chain_key",
        "logical_revision_key",
        "present_fact_ids",
        "row_kind",
        "semantic_section_key",
        "topic_id",
        "witness_fact_ids",
    }
)
CONTENT_COMPANION_ROW_FIELDS = frozenset(
    {
        "effective_membership_mode",
        "graph_id",
        "intent_key",
        "lifecycle_branch_key",
        "lifecycle_logical_document_key",
        "lifecycle_revision_chain_key",
        "logical_revision_key",
        "present_fact_ids",
        "primary_capability_key",
        "primary_intent_key",
        "rendition_group_key",
        "row_kind",
        "semantic_section_key",
        "topic_id",
        "witness_fact_ids",
    }
)
CONTENT_WITNESS_ROW_FIELDS = frozenset(
    {
        "capability_key",
        "fact_id",
        "graph_id",
        "predicate_id",
        "purge_witness_key",
        "row_kind",
        "subject_entity_id",
        "typed_value",
        "visibility_by_checkpoint",
    }
)
CONTENT_SHARD_COMMITMENT_FIELDS = frozenset(
    {
        "body_bytes",
        "body_sha256",
        "first_intent_key",
        "last_intent_key",
        "origin",
        "row_count",
        "row_kind",
        "source_shard_id",
    }
)

PROHIBITED_KEY_TOKENS = frozenset(
    {
        "answer",
        "distractor",
        "final",
        "materialization",
        "oracle",
        "path",
        "physical",
        "query",
        "quota",
        "rank",
        "raw_hash",
        "relevance",
        "retrieval",
        "scope",
        "solution",
    }
)


class PersonaV2LifecycleEffectiveMembershipReconciliationValidationError(
    ValueError
):
    """Raised when reconciliation validation fails."""


def _fail(message):
    raise PersonaV2LifecycleEffectiveMembershipReconciliationValidationError(
        message
    )


def _freeze_cached_value(value):
    """Convert cache state to a recursively immutable tuple representation."""

    if value is None or type(value) in {bool, int, float, str, bytes}:
        return ("atom", value)
    if isinstance(value, dict):
        return (
            "dict",
            tuple(
                (_freeze_cached_value(key), _freeze_cached_value(item))
                for key, item in value.items()
            ),
        )
    if type(value) is list:
        return ("list", tuple(_freeze_cached_value(item) for item in value))
    if type(value) is tuple:
        return ("tuple", tuple(_freeze_cached_value(item) for item in value))
    if type(value) in {set, frozenset}:
        frozen_items = tuple(
            sorted(
                (_freeze_cached_value(item) for item in value),
                key=repr,
            )
        )
        return (
            "set" if type(value) is set else "frozenset",
            frozen_items,
        )
    _fail(f"cache state contains an unsupported value: {type(value).__name__}")


def _thaw_cached_value(value):
    """Return a fully detached value from an immutable cache representation."""

    tag = value[0]
    if tag == "atom":
        return value[1]
    if tag == "dict":
        return {
            _thaw_cached_value(key): _thaw_cached_value(item)
            for key, item in value[1]
        }
    if tag == "list":
        return [_thaw_cached_value(item) for item in value[1]]
    if tag == "tuple":
        return tuple(_thaw_cached_value(item) for item in value[1])
    if tag == "set":
        return {_thaw_cached_value(item) for item in value[1]}
    if tag == "frozenset":
        return frozenset(_thaw_cached_value(item) for item in value[1])
    _fail("immutable cache state has an unknown tag")


def _detached_lru_cache(*, maxsize):
    """Cache immutable tuples while exposing a fresh detached value per call."""

    def decorate(builder):
        @functools.lru_cache(maxsize=maxsize)
        def immutable_cache(*args, **kwargs):
            return _freeze_cached_value(builder(*args, **kwargs))

        @functools.wraps(builder)
        def detached(*args, **kwargs):
            return _thaw_cached_value(immutable_cache(*args, **kwargs))

        detached.cache_clear = immutable_cache.cache_clear
        detached.cache_info = immutable_cache.cache_info
        detached.immutable_cache_only = True
        if hasattr(immutable_cache, "cache_parameters"):
            detached.cache_parameters = immutable_cache.cache_parameters
        return detached

    return decorate


def _ascii(value):
    return value.encode("ascii")


def _require_persona_id(persona_id):
    if type(persona_id) is not str or persona_id not in envelope.PERSONA_IDS:
        _fail(f"unknown persona ID: {persona_id!r}")


def _require_origin(origin):
    if type(origin) is not str or origin not in ORIGIN_ORDER:
        _fail(f"unknown source origin: {origin!r}")


def _require_profile(profile):
    if type(profile) is not str or profile not in PROFILE_ORDER:
        _fail(f"unknown source profile: {profile!r}")


def _strict_json_domain(value, *, path="$"):
    if value is None or type(value) is bool or type(value) is int or type(value) is str:
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _strict_json_domain(item, path=f"{path}[{index}]")
        return
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            _fail(f"{path} contains a non-string key")
        for key, item in value.items():
            _strict_json_domain(item, path=f"{path}.{key}")
        return
    _fail(f"{path} contains a non-canonical JSON value")


def _canonical(value, *, label, maximum):
    _strict_json_domain(value)
    try:
        return artifact_common.canonical_json_bytes(
            value, label=label, max_bytes=maximum
        )
    except Exception as error:
        _fail(str(error))


def _require_all_false_authority(value, *, label):
    if type(value) is not dict or value.get("g0_contract_frozen") is not False:
        _fail(f"{label} must remain non-G0")
    authority = value.get("authority")
    if set(authority or {}) != AUTHORITY_FIELDS or any(
        type(flag) is not bool or flag is not False
        for flag in (authority or {}).values()
    ):
        _fail(f"{label} authority must be the exact all-false schema")


def _require_sha256_pin(value, *, label):
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _fail(f"{label} must be an exact lowercase SHA-256 pin")


def _require_artifact_identity(
    value,
    *,
    artifact_kind,
    artifact_schema,
    label,
    expected_persona_id=None,
    expected_origin=None,
    expected_profile=None,
):
    if (
        type(value) is not dict
        or value.get("artifact_kind") != artifact_kind
        or value.get("artifact_schema") != artifact_schema
        or type(value.get("artifact_schema_version")) is not int
        or value.get("artifact_schema_version") != ARTIFACT_SCHEMA_VERSION
        or value.get("fixture_id") != envelope.FIXTURE_ID
        or type(value.get("fixture_schema_version")) is not int
        or value.get("fixture_schema_version")
        != envelope.FIXTURE_SCHEMA_VERSION
    ):
        _fail(f"{label} artifact identity drifted")
    if (
        expected_persona_id is not None
        and value.get("persona_id") != expected_persona_id
    ):
        _fail(f"{label} persona coordinate differs from validator argument")
    if expected_origin is not None and value.get("origin") != expected_origin:
        _fail(f"{label} origin coordinate differs from validator argument")
    if expected_profile is not None and value.get("profile") != expected_profile:
        _fail(f"{label} profile coordinate differs from validator argument")


def _require_binding_pin_shapes(
    value, field, coordinate_fields, *, label
):
    bindings = value.get(field) if type(value) is dict else None
    if type(bindings) is not list or len(bindings) != len(coordinate_fields):
        _fail(f"{label} binding cardinality drifted")
    base_fields = {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "canonical_bytes",
        "dependency_role",
        "fixture_id",
        "fixture_schema_version",
        "name",
        "sha256",
    }
    for index, (binding, coordinates) in enumerate(
        zip(bindings, coordinate_fields, strict=True)
    ):
        expected_fields = base_fields | set(coordinates)
        if type(binding) is not dict or set(binding) != expected_fields:
            _fail(f"{label} binding {index} schema drifted")
        if (
            type(binding["canonical_bytes"]) is not int
            or binding["canonical_bytes"] <= 0
            or type(binding["artifact_schema_version"]) is not int
            or binding["artifact_schema_version"] <= 0
            or binding["fixture_id"] != envelope.FIXTURE_ID
            or binding["fixture_schema_version"]
            != envelope.FIXTURE_SCHEMA_VERSION
            or any(
                type(binding[field_name]) is not str
                or not binding[field_name]
                for field_name in (
                    "artifact_kind",
                    "artifact_schema",
                    "dependency_role",
                    "name",
                )
            )
            or any(
                type(binding[coordinate]) is not str
                or not binding[coordinate]
                for coordinate in coordinates
            )
        ):
            _fail(f"{label} binding {index} pin metadata drifted")
        _require_sha256_pin(
            binding["sha256"], label=f"{label} binding {index}"
        )


def _require_actual_origin_security_invariants(
    value, *, expected_persona_id, expected_origin
):
    _require_artifact_identity(
        value,
        artifact_kind=ORIGIN_KIND,
        artifact_schema=ORIGIN_SCHEMA,
        label="effective origin manifest",
        expected_persona_id=expected_persona_id,
        expected_origin=expected_origin,
    )
    _require_all_false_authority(value, label="effective origin manifest")
    descriptor = value.get("body_descriptor")
    descriptor_fields = {
        "body_bytes",
        "body_persisted",
        "body_sha256",
        "file_name",
        "maximum_row_bytes_including_lf",
        "row_count",
    }
    if type(descriptor) is not dict or set(descriptor) != descriptor_fields:
        _fail("effective origin body descriptor schema drifted")
    if (
        descriptor["body_persisted"] is not True
        or type(descriptor["body_bytes"]) is not int
        or not 1 <= descriptor["body_bytes"] <= MAX_ORIGIN_BODY_BYTES
        or type(descriptor["row_count"]) is not int
        or not 1 <= descriptor["row_count"] <= MAX_ORIGIN_ROWS
        or type(descriptor["maximum_row_bytes_including_lf"]) is not int
        or not 1
        <= descriptor["maximum_row_bytes_including_lf"]
        <= MAX_COMPACT_ROW_BYTES_INCLUDING_LF
        or type(descriptor["file_name"]) is not str
        or not descriptor["file_name"]
    ):
        _fail("effective origin body descriptor pin metadata drifted")
    _require_sha256_pin(
        descriptor["body_sha256"], label="effective origin body"
    )
    representative_pin = {
        ("p01", "pilot"): (
            EXPECTED_P01_PILOT_COMPACT_BODY_BYTES,
            EXPECTED_P01_PILOT_COMPACT_BODY_SHA256,
        ),
        ("p12", "full-residual"): (
            EXPECTED_P12_FULL_RESIDUAL_COMPACT_BODY_BYTES,
            EXPECTED_P12_FULL_RESIDUAL_COMPACT_BODY_SHA256,
        ),
    }.get((expected_persona_id, expected_origin))
    if representative_pin is not None and (
        descriptor["body_bytes"] != representative_pin[0]
        or descriptor["body_sha256"] != representative_pin[1]
    ):
        _fail("effective origin representative frozen body pin drifted")
    _require_binding_pin_shapes(
        value,
        "input_bindings",
        ((), (), ("persona_id", "origin"), ("persona_id",), ("persona_id",)),
        label="effective origin input",
    )
    bindings = value["input_bindings"]
    if (
        bindings[2]["persona_id"] != expected_persona_id
        or bindings[2]["origin"] != expected_origin
        or any(
            binding["persona_id"] != expected_persona_id
            for binding in bindings[3:]
        )
    ):
        _fail("effective origin input binding coordinates drifted")


def _require_actual_profile_security_invariants(
    value, *, expected_persona_id, expected_profile
):
    _require_artifact_identity(
        value,
        artifact_kind=PROFILE_KIND,
        artifact_schema=PROFILE_SCHEMA,
        label="effective profile manifest",
        expected_persona_id=expected_persona_id,
        expected_profile=expected_profile,
    )
    _require_all_false_authority(value, label="effective profile manifest")
    bindings = value.get("origin_manifest_bindings")
    expected_origins = _profile_origins(expected_profile)
    _require_binding_pin_shapes(
        value,
        "origin_manifest_bindings",
        tuple(("persona_id", "origin") for _ in expected_origins),
        label="effective profile origin",
    )
    if any(
        binding["persona_id"] != expected_persona_id
        or binding["origin"] != expected_origin
        for binding, expected_origin in zip(
            bindings, expected_origins, strict=True
        )
    ):
        _fail("effective profile origin binding coordinates drifted")


def _require_actual_projection_pin_shapes(
    value, *, expected_persona_id, opening_raw
):
    _require_artifact_identity(
        value,
        artifact_kind=PROJECTION_KIND,
        artifact_schema=PROJECTION_SCHEMA,
        label="effective content projection",
        expected_persona_id=expected_persona_id,
    )
    sections = value.get("content_sections") if type(value) is dict else None
    commitments = (
        sections.get("effective_membership_shard_commitments")
        if type(sections) is dict
        else None
    )
    if type(commitments) is not list or not commitments:
        _fail("effective content projection commitments are missing")
    for index, commitment in enumerate(commitments):
        if type(commitment) is not dict or set(commitment) != CONTENT_SHARD_COMMITMENT_FIELDS:
            _fail(f"effective content projection commitment {index} schema drifted")
        if (
            type(commitment["body_bytes"]) is not int
            or not 1 <= commitment["body_bytes"] <= MAX_EXPANDED_SHARD_BODY_BYTES
            or type(commitment["row_count"]) is not int
            or not 1 <= commitment["row_count"] <= MAX_EXPANDED_ROWS_PER_SHARD
        ):
            _fail(f"effective content projection commitment {index} metadata drifted")
        _require_sha256_pin(
            commitment["body_sha256"],
            label=f"effective content projection commitment {index}",
        )
    if expected_persona_id == "p01" and (
        len(opening_raw) != EXPECTED_P01_CONTENT_PROJECTION_BYTES
        or _sha256(opening_raw) != EXPECTED_P01_CONTENT_PROJECTION_SHA256
    ):
        _fail("p01 effective content projection frozen pin drifted")


def _require_actual_suite_security_invariants(value, *, opening_raw):
    _require_artifact_identity(
        value,
        artifact_kind=SUITE_KIND,
        artifact_schema=SUITE_SCHEMA,
        label="effective suite descriptor",
    )
    _require_all_false_authority(value, label="effective suite descriptor")
    if (
        len(opening_raw) != EXPECTED_SUITE_CANONICAL_BYTES
        or _sha256(opening_raw) != EXPECTED_SUITE_SHA256
    ):
        _fail("effective-membership suite frozen production pin drifted")
    _require_binding_pin_shapes(
        value,
        "input_bindings",
        ((), (), (), ()),
        label="effective suite input",
    )
    _require_binding_pin_shapes(
        value,
        "origin_manifest_bindings",
        tuple(("persona_id", "origin") for _ in range(40)),
        label="effective suite origin",
    )
    _require_binding_pin_shapes(
        value,
        "profile_manifest_bindings",
        tuple(("persona_id", "profile") for _ in range(40)),
        label="effective suite profile",
    )
    _require_binding_pin_shapes(
        value,
        "content_projection_bindings",
        tuple(("persona_id",) for _ in range(20)),
        label="effective suite content projection",
    )


def _reject_prohibited_keys(value, *, path="$"):
    if type(value) is list:
        for index, item in enumerate(value):
            _reject_prohibited_keys(item, path=f"{path}[{index}]")
        return
    if type(value) is not dict:
        return
    for key, item in value.items():
        lowered = key.lower()
        if any(token in lowered for token in PROHIBITED_KEY_TOKENS):
            _fail(f"prohibited content key at {path}.{key}")
        _reject_prohibited_keys(item, path=f"{path}.{key}")


def _snapshot(value, *, label, maximum):
    raw = _canonical(value, label=label, maximum=maximum)
    return json.loads(raw), raw


def _reauthenticate(value, opening_raw, *, label, maximum):
    try:
        closing = _canonical(value, label=label, maximum=maximum)
    except PersonaV2LifecycleEffectiveMembershipReconciliationValidationError:
        _fail(f"caller-owned {label} changed during validation")
    if closing != opening_raw:
        _fail(f"caller-owned {label} changed during validation")


def _jsonl_row_bytes(row, *, label, maximum_row_bytes):
    raw = _canonical(row, label=label, maximum=maximum_row_bytes - 1) + b"\n"
    if len(raw) > maximum_row_bytes:
        _fail(f"{label} exceeds its LF-inclusive row cap")
    return raw


def _parse_jsonl(body, *, label, maximum_row_bytes, maximum_rows):
    if type(body) is not bytes:
        _fail(f"{label} provider must return exact bytes")
    if body and not body.endswith(b"\n"):
        _fail(f"{label} must end every row with LF")
    rows = []
    for raw in body.splitlines(keepends=True):
        if not raw.endswith(b"\n") or raw.endswith(b"\r\n"):
            _fail(f"{label} uses a noncanonical record terminator")
        if len(raw) > maximum_row_bytes:
            _fail(f"{label} row exceeds its LF-inclusive cap")
        try:
            row = json.loads(raw[:-1].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            _fail(f"{label} contains invalid JSONL: {error}")
        if _jsonl_row_bytes(
            row, label=label, maximum_row_bytes=maximum_row_bytes
        ) != raw:
            _fail(f"{label} row is not canonical JSON")
        rows.append(row)
        if len(rows) > maximum_rows:
            _fail(f"{label} exceeds its row-count cap")
    return rows


def _authenticated_body(
    provider,
    args,
    *,
    expected_bytes,
    expected_sha256,
    hard_cap,
    label,
):
    if (
        type(hard_cap) is not int
        or hard_cap <= 0
        or type(expected_bytes) is not int
        or not 1 <= expected_bytes <= hard_cap
        or type(expected_sha256) is not str
        or len(expected_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_sha256)
    ):
        _fail(f"{label} descriptor is invalid before provider execution")
    try:
        first = provider(*args)
    except Exception as error:
        _fail(f"{label} provider failed: {error}")
    if type(first) is not bytes or len(first) > hard_cap:
        _fail(f"{label} provider returned an invalid first body")
    if len(first) != expected_bytes or not hmac.compare_digest(
        hashlib.sha256(first).hexdigest(), expected_sha256
    ):
        _fail(f"{label} first body differs from its receipt")
    try:
        replay = provider(*args)
    except Exception as error:
        _fail(f"{label} replay provider failed: {error}")
    if (
        type(replay) is not bytes
        or len(replay) > hard_cap
        or len(replay) != expected_bytes
        or not hmac.compare_digest(first, replay)
    ):
        _fail(f"{label} replay is nondeterministic or out of bounds")
    return first


def _sha256(value):
    return hashlib.sha256(value).hexdigest()


def _lifecycle_identity(document_key):
    if type(document_key) is not str or not document_key:
        _fail("lifecycle document key must be a non-empty string")
    return {
        "lifecycle_branch_key": f"{document_key}-branch-main-v1",
        "lifecycle_logical_document_key": document_key,
        "lifecycle_revision_chain_key": (
            f"{document_key}-revision-chain-main-v1"
        ),
        "logical_revision_key": f"{document_key}-revision-w0-v1",
        "semantic_section_key": f"{document_key}-semantic-section-main-v1",
    }


def _base_revision_chain_key(base_row):
    preimage = (
        base_row["logical_document_key"]
        + "\x00"
        + base_row["logical_branch_key"]
    ).encode("utf-8")
    return (
        f"{base_row['persona_id']}-base-revision-chain-"
        f"{_sha256(preimage)[:24]}-v1"
    )


def _witness_fact_id(persona_id, ordinal):
    return f"purge-witness-fact-{persona_id}-syn-{ordinal:03d}"


def _witness_token_id(persona_id, ordinal):
    return f"purge-witness-token-{persona_id}-syn-{ordinal:03d}"


def _witness_visibility():
    return [
        {"checkpoint": checkpoint, "state": state}
        for checkpoint, state in (
            ("W0", "current"),
            ("W1", "current"),
            ("W2", "current"),
            ("W3", "current"),
            ("W4", "current"),
            ("W5-pre-purge", "current"),
            ("W5-final", "absent"),
        )
    ]


def _normal_profile_id(persona_id, topic_slot):
    if topic_slot not in {"g01", "g02", "g03", "g04"}:
        _fail("semantic topic has an invalid topic slot")
    return f"{persona_id}-source-fact-profile-{topic_slot}-normal-v2"


@_detached_lru_cache(maxsize=1)
def _independent_catalog_state():
    semantic = source_semantic.build_source_semantic_membership_catalog()
    source_semantic.validate_source_semantic_membership_catalog(semantic)
    coverage = lifecycle_coverage.build_lifecycle_coverage_catalog()
    lifecycle_coverage.validate_lifecycle_coverage_catalog(coverage)
    graphs = fact_graph.build_fact_graph_suite()
    if (
        type(graphs) is not list
        or any(type(row) is not dict for row in graphs)
        or [row.get("persona_id") for row in graphs]
        != list(envelope.PERSONA_IDS)
    ):
        _fail("fact-graph suite persona domain drifted")

    graph_by_persona_id = {}
    base_fact_coordinates = set()
    base_fact_ids = set()
    project_entities = set()
    for persona_id, value in zip(envelope.PERSONA_IDS, graphs, strict=True):
        fact_graph.validate_fact_graph(persona_id, value)
        for graph in value["graphs"]:
            coordinate = (persona_id, graph["graph_id"])
            if coordinate in graph_by_persona_id:
                _fail("fact graph coordinate is duplicated")
            graph_by_persona_id[coordinate] = graph
            entity_ids = {row["entity_id"] for row in graph["entities"]}
            if graph["project_or_case_id"] not in entity_ids:
                _fail("fact graph project/case is not an authenticated entity")
            project_entities.add(
                (persona_id, graph["graph_id"], graph["project_or_case_id"])
            )
            for fact in graph["facts"]:
                base_fact_coordinates.add((persona_id, fact["fact_id"]))
                base_fact_ids.add(fact["fact_id"])
            for conflict in graph["conflict_sets"]:
                for fact_id in conflict["member_fact_ids"]:
                    base_fact_coordinates.add((persona_id, fact_id))
                    base_fact_ids.add(fact_id)

    predicates = dict(fact_graph_data.PREDICATE_ROWS)
    if predicates.get("predicate-status-syn-004") != "synthetic-token":
        _fail("typed purge witness status predicate drifted")
    fact_profiles = {
        row["fact_profile_id"]: row for row in semantic["fact_profiles"]
    }
    topics = {row["topic_id"]: row for row in semantic["semantic_topics"]}
    if len(fact_profiles) != 900 or len(topics) != 80:
        _fail("source semantic fact-profile/topic catalog drifted")
    for profile in fact_profiles.values():
        if profile["profile_kind"] == "empty":
            if profile["present_fact_ids"]:
                _fail("empty profile gained a fact")
            continue
        coordinate = (profile["persona_id"], profile["graph_id"])
        graph = graph_by_persona_id.get(coordinate)
        graph_fact_ids = (
            {row["fact_id"] for row in graph["facts"]}
            | {
                fact_id
                for conflict in graph["conflict_sets"]
                for fact_id in conflict["member_fact_ids"]
            }
            if graph is not None
            else set()
        )
        if not set(profile["present_fact_ids"]) <= graph_fact_ids:
            _fail("semantic fact profile references a foreign graph fact")
        for conflict in graph["conflict_sets"] if graph is not None else []:
            if not set(conflict["member_fact_ids"]) <= graph_fact_ids:
                _fail("conflict set references a fact outside its graph")
    witness_requirements = {
        row["capability_key"]: row
        for row in coverage["purge_witness_requirements"]
    }
    if len(witness_requirements) != EXPECTED_TYPED_WITNESS_COUNT:
        _fail("purge witness requirement domain drifted")
    planned_witness_ids = {
        _witness_fact_id(persona_id, ordinal)
        for persona_id in envelope.PERSONA_IDS
        for ordinal in range(1, 16)
    }
    if (
        len(planned_witness_ids) != EXPECTED_TYPED_WITNESS_COUNT
        or planned_witness_ids & base_fact_ids
    ):
        _fail("planned witness IDs are not globally unique and base-disjoint")
    return {
        "base_fact_coordinates": frozenset(base_fact_coordinates),
        "base_fact_ids": frozenset(base_fact_ids),
        "coverage": copy.deepcopy(coverage),
        "fact_profiles": copy.deepcopy(fact_profiles),
        "graph_by_persona_id": copy.deepcopy(graph_by_persona_id),
        "graph_values_by_persona": {
            value["persona_id"]: copy.deepcopy(value) for value in graphs
        },
        "project_entities": frozenset(project_entities),
        "semantic": copy.deepcopy(semantic),
        "topics": copy.deepcopy(topics),
        "witness_requirements": copy.deepcopy(witness_requirements),
    }


def _typed_witness_row(
    persona_id, ordinal, match, normal_profile, requirement, catalog_state
):
    graph = catalog_state["graph_by_persona_id"].get(
        (persona_id, normal_profile["graph_id"])
    )
    if graph is None:
        _fail("typed witness graph is outside its persona")
    project_or_case_id = normal_profile["project_or_case_id"]
    if (
        project_or_case_id != graph["project_or_case_id"]
        or (
            persona_id,
            normal_profile["graph_id"],
            project_or_case_id,
        )
        not in catalog_state["project_entities"]
    ):
        _fail("typed witness subject is not an authenticated project entity")
    fact_id = _witness_fact_id(persona_id, ordinal)
    if (persona_id, fact_id) in catalog_state["base_fact_coordinates"]:
        _fail("typed witness fact collides with an authenticated base fact")
    row = {
        "capability_key": match["capability_key"],
        "fact_id": fact_id,
        "graph_id": normal_profile["graph_id"],
        "origin": "pilot",
        "persona_id": persona_id,
        "predicate_id": "predicate-status-syn-004",
        "project_or_case_id": project_or_case_id,
        "purge_witness_key": requirement["purge_witness_key"],
        "row_kind": "typed-purge-witness-fact",
        "subject_entity_id": project_or_case_id,
        "suite_global_uniqueness_required": True,
        "typed_value": {
            "kind": "synthetic-token",
            "token_id": _witness_token_id(persona_id, ordinal),
        },
        "visibility_by_checkpoint": _witness_visibility(),
    }
    if set(row) != TYPED_WITNESS_ROW_FIELDS:
        _fail("typed witness row schema drifted")
    return row


def _primary_override_row(persona_id, match, normal_profile, witness=None):
    witness_ids = [] if witness is None else [witness["fact_id"]]
    row = {
        "base_fact_profile_id": match["base_fact_profile_id"],
        "capability_class_key": match["capability_class_key"],
        "capability_key": match["capability_key"],
        "effective_fact_profile_id": normal_profile["fact_profile_id"],
        "effective_membership_mode": (
            "graph-normal" if witness is None else "graph-normal-plus-witness"
        ),
        "graph_id": normal_profile["graph_id"],
        "intent_key": match["intent_key"],
        **_lifecycle_identity(match["lifecycle_logical_document_slot_key"]),
        "origin": "pilot",
        "persona_id": persona_id,
        "present_fact_ids": [
            *normal_profile["present_fact_ids"],
            *witness_ids,
        ],
        "row_kind": "primary-effective-membership-override",
        "topic_id": match["base_topic_id"],
        "witness_fact_ids": witness_ids,
    }
    if set(row) != PRIMARY_OVERRIDE_ROW_FIELDS:
        _fail("primary override row schema drifted")
    return row


def _companion_mirror_row(match, primary, primary_match):
    if (
        primary_match["allocation_class"] not in {"U", "Y"}
        or primary_match["base_topic_id"] != match["base_topic_id"]
        or primary_match["base_language"] != match["base_language"]
        or primary_match["family"] == match["family"]
        or primary["witness_fact_ids"]
    ):
        _fail("companion is not an exact current U/Y distinct-family mirror")
    row = {
        "base_fact_profile_id": match["base_fact_profile_id"],
        "companion_requirement_key": match["companion_requirement_key"],
        "effective_fact_profile_id": primary["effective_fact_profile_id"],
        "effective_membership_mode": "companion-mirror",
        "graph_id": primary["graph_id"],
        "intent_key": match["intent_key"],
        "lifecycle_branch_key": primary["lifecycle_branch_key"],
        "lifecycle_logical_document_key": primary[
            "lifecycle_logical_document_key"
        ],
        "lifecycle_revision_chain_key": primary[
            "lifecycle_revision_chain_key"
        ],
        "logical_revision_key": primary["logical_revision_key"],
        "origin": "pilot",
        "persona_id": primary["persona_id"],
        "present_fact_ids": list(primary["present_fact_ids"]),
        "primary_capability_key": match["primary_capability_key"],
        "primary_intent_key": primary["intent_key"],
        "rendition_group_key": match["rendition_group_key"],
        "row_kind": "companion-effective-membership-mirror",
        "semantic_section_key": primary["semantic_section_key"],
        "topic_id": primary["topic_id"],
        "witness_fact_ids": [],
    }
    if set(row) != COMPANION_MIRROR_ROW_FIELDS:
        _fail("companion mirror row schema drifted")
    return row


@_detached_lru_cache(maxsize=20)
def _independent_persona_plan(persona_id):
    _require_persona_id(persona_id)
    catalog_state = _independent_catalog_state()
    lifecycle = matched_lifecycle.build_source_matched_lifecycle_persona(persona_id)
    matched_lifecycle.validate_source_matched_lifecycle_persona(
        persona_id, lifecycle
    )
    lifecycle = copy.deepcopy(lifecycle)
    contributor = [
        row
        for row in lifecycle["primary_match_rows"]
        if row["gate_role"] == "contract_contributor"
    ]
    incidental = [
        row
        for row in lifecycle["primary_match_rows"]
        if row["gate_role"] == "incidental_searchable"
    ]
    if len(contributor) != 100 or len(incidental) != 5:
        _fail("lifecycle contributor/incidental split drifted")
    contributor_by_capability = {
        row["capability_key"]: row for row in contributor
    }
    if len(contributor_by_capability) != 100:
        _fail("contributor capability keys are not unique")

    purge_matches = sorted(
        (
            row
            for row in contributor
            if row["allocation_class"] == "P"
            and row["capability_class_key"] == "purged-negative"
        ),
        key=lambda row: _ascii(row["capability_key"]),
    )
    if len(purge_matches) != 15:
        _fail("persona must expose exactly fifteen P primaries")
    witness_by_capability = {}
    witness_rows = []
    for ordinal, match in enumerate(purge_matches, start=1):
        topic = catalog_state["topics"].get(match["base_topic_id"])
        if topic is None or topic["persona_id"] != persona_id:
            _fail("P primary topic is not persona-local")
        normal = catalog_state["fact_profiles"].get(
            _normal_profile_id(persona_id, topic["topic_slot"])
        )
        requirement = catalog_state["witness_requirements"].get(
            match["capability_key"]
        )
        if normal is None or requirement is None:
            _fail("P primary lacks a normal profile or witness requirement")
        witness = _typed_witness_row(
            persona_id,
            ordinal,
            match,
            normal,
            requirement,
            catalog_state,
        )
        witness_by_capability[match["capability_key"]] = witness
        witness_rows.append(witness)

    primary_rows = []
    for match in sorted(contributor, key=lambda row: _ascii(row["capability_key"])):
        topic = catalog_state["topics"].get(match["base_topic_id"])
        if topic is None or topic["persona_id"] != persona_id:
            _fail("contributor topic is not persona-local")
        normal = catalog_state["fact_profiles"].get(
            _normal_profile_id(persona_id, topic["topic_slot"])
        )
        if (
            normal is None
            or normal["persona_id"] != persona_id
            or normal["graph_id"] != topic["graph_id"]
            or normal["profile_kind"] != "graph-normal-w0"
            or len(normal["present_fact_ids"]) != 8
            or len(set(normal["present_fact_ids"])) != 8
        ):
            _fail("same-persona same-topic graph-normal W0 join failed")
        primary_rows.append(
            _primary_override_row(
                persona_id,
                match,
                normal,
                witness_by_capability.get(match["capability_key"]),
            )
        )
    primary_by_capability = {
        row["capability_key"]: row for row in primary_rows
    }
    companion_rows = []
    for match in sorted(
        lifecycle["companion_match_rows"],
        key=lambda row: _ascii(row["primary_capability_key"]),
    ):
        primary = primary_by_capability.get(match["primary_capability_key"])
        primary_match = contributor_by_capability.get(
            match["primary_capability_key"]
        )
        if primary is None or primary_match is None:
            _fail("companion references a non-contributor primary")
        companion_rows.append(
            _companion_mirror_row(match, primary, primary_match)
        )
    if len(primary_rows) != 100 or len(companion_rows) != 10:
        _fail("persona sparse override counts drifted")
    override_by_intent = {
        row["intent_key"]: row
        for row in [*primary_rows, *companion_rows]
    }
    incidental_keys = {row["intent_key"] for row in incidental}
    if len(override_by_intent) != 110 or set(override_by_intent) & incidental_keys:
        _fail("effective overrides collide or capture an I5 source")
    return {
        "companion_rows": tuple(companion_rows),
        "contributor_by_capability": contributor_by_capability,
        "incidental_intent_keys": frozenset(incidental_keys),
        "lifecycle": lifecycle,
        "override_by_intent": override_by_intent,
        "primary_rows": tuple(primary_rows),
        "typed_witness_rows": tuple(witness_rows),
        "witness_by_capability": witness_by_capability,
    }


def _effective_w0_row(base_row, override):
    if set(base_row) != source_semantic.EXPANDED_MEMBERSHIP_ROW_FIELDS:
        _fail("base source-semantic membership row schema drifted")
    if override is None:
        row = {
            "effective_membership_mode": "base-inheritance",
            "intent_key": base_row["intent_key"],
            "lifecycle_branch_key": base_row["logical_branch_key"],
            "lifecycle_logical_document_key": base_row["logical_document_key"],
            "lifecycle_revision_chain_key": _base_revision_chain_key(base_row),
            "logical_revision_key": base_row["logical_revision_key"],
            "origin": base_row["origin"],
            "persona_id": base_row["persona_id"],
            "present_fact_ids": list(base_row["present_fact_ids"]),
            "present_fact_set_key": base_row["present_fact_set_key"],
            "projection_mode": base_row["projection_mode"],
            "row_kind": "effective-w0-membership",
            "semantic_section_key": base_row["semantic_section_key"],
            "witness_fact_ids": [],
        }
    else:
        row = {
            "effective_membership_mode": override["effective_membership_mode"],
            "intent_key": base_row["intent_key"],
            "lifecycle_branch_key": override["lifecycle_branch_key"],
            "lifecycle_logical_document_key": override[
                "lifecycle_logical_document_key"
            ],
            "lifecycle_revision_chain_key": override[
                "lifecycle_revision_chain_key"
            ],
            "logical_revision_key": override["logical_revision_key"],
            "origin": base_row["origin"],
            "persona_id": base_row["persona_id"],
            "present_fact_ids": list(override["present_fact_ids"]),
            "present_fact_set_key": base_row["present_fact_set_key"],
            "projection_mode": "all-present-facts-single-semantic-section",
            "row_kind": "effective-w0-membership",
            "semantic_section_key": override["semantic_section_key"],
            "witness_fact_ids": list(override["witness_fact_ids"]),
        }
    if set(row) != EXPANDED_W0_ROW_FIELDS:
        _fail("effective W0 row schema drifted")
    if len(set(row["present_fact_ids"])) != len(row["present_fact_ids"]):
        _fail("effective W0 row contains duplicate fact IDs")
    return row


def _iter_expected_expanded_w0_rows(persona_id, origin, shard_ordinal):
    plan = _independent_persona_plan(persona_id)
    for base_row in source_semantic.iter_expanded_fact_membership_rows(
        persona_id, origin, shard_ordinal
    ):
        yield _effective_w0_row(
            base_row, plan["override_by_intent"].get(base_row["intent_key"])
        )


def _bounded_expected_body(
    rows,
    *,
    label,
    row_cap,
    body_cap,
    row_count_cap,
):
    parts = []
    maximum = 0
    count = 0
    total = 0
    for row in rows:
        count += 1
        if count > row_count_cap:
            _fail(f"{label} exceeds its row-count cap")
        raw = _jsonl_row_bytes(
            row, label=label, maximum_row_bytes=row_cap
        )
        maximum = max(maximum, len(raw))
        parts.append(raw)
        total += len(raw)
        if total > body_cap:
            _fail(f"{label} exceeds its body cap")
    if not parts:
        _fail(f"{label} cannot be empty")
    return b"".join(parts), maximum, count


def _expected_expanded_w0_body(persona_id, origin, shard_ordinal):
    return _bounded_expected_body(
        _iter_expected_expanded_w0_rows(persona_id, origin, shard_ordinal),
        label="persona v2 expanded effective W0 membership row",
        row_cap=MAX_EXPANDED_ROW_BYTES_INCLUDING_LF,
        body_cap=MAX_EXPANDED_SHARD_BODY_BYTES,
        row_count_cap=MAX_EXPANDED_ROWS_PER_SHARD,
    )


def _event_created_lineage_rows(persona_id):
    plan = _independent_persona_plan(persona_id)
    primary_by_capability = {
        row["capability_key"]: row
        for row in plan["lifecycle"]["primary_match_rows"]
    }
    rows = []
    p_w1_by_capability = {}
    p_prime_by_capability = {}
    created_source_keys = set()
    for event in matched_lifecycle.iter_source_matched_lifecycle_event_rows(
        persona_id
    ):
        event_fields = set(event)
        if event_fields == matched_lifecycle.SCOPE_EVENT_ROW_FIELDS:
            if event.get("row_kind") != "scope":
                _fail("scope event row kind drifted")
            continue
        if (
            event_fields != matched_lifecycle.SOURCE_EVENT_ROW_FIELDS
            or event.get("row_kind") != "source"
        ):
            _fail("lifecycle event iterator emitted an unknown row schema")
        if event["after_source_intent_key"] == event["source_intent_key"]:
            continue
        after_key = event["after_source_intent_key"]
        expected_after = (
            f"{persona_id}-pre-solve-source-intent-"
            f"{event['event_sequence_ordinal']:04d}"
        )
        if after_key != expected_after:
            _fail("event-created source intent is not the canonical event key")
        if after_key in created_source_keys:
            _fail("event-created source intent is duplicated")
        created_source_keys.add(after_key)
        primary = primary_by_capability.get(event["capability_key"])
        witness = plan["witness_by_capability"].get(event["capability_key"])
        if primary is None:
            _fail("event-created source lacks an authenticated primary capability")
        if primary["allocation_class"] == "P" and event["event_profile_key"] == (
            "w1-typed-edit"
        ):
            if witness is None or event["fact_transition_rule"] != "facts/typed-revision":
                _fail("P W1 descendant lacks its typed witness transition")
            role = "matching-w1-p-descendant"
            present = [witness["fact_id"]]
            if event["capability_key"] in p_w1_by_capability:
                _fail("P capability has multiple W1 witness descendants")
            p_w1_by_capability[event["capability_key"]] = event
        elif primary["allocation_class"] == "P" and event[
            "event_profile_key"
        ] == "w5-create-p-prime":
            if witness is None or event["fact_transition_rule"] != "facts/repl-distinct":
                _fail("P-prime transition does not explicitly replace facts")
            role = "p-prime-capacity-replacement"
            present = []
            if event["capability_key"] in p_prime_by_capability:
                _fail("P capability has multiple P-prime replacements")
            p_prime_by_capability[event["capability_key"]] = event
        else:
            role = "other-event-created-intent"
            present = []
            if witness is not None:
                _fail("a P witness leaked to a non-W1/P-prime created event")
        row = {
            "after_source_intent_key": after_key,
            "capability_key": event["capability_key"],
            "consumer_role": role,
            "dependency_group_key": event["dependency_group_key"],
            "event_intent_key": event["event_intent_key"],
            "event_profile_key": event["event_profile_key"],
            "event_sequence_ordinal": event["event_sequence_ordinal"],
            "fact_transition_rule": event["fact_transition_rule"],
            "persona_id": persona_id,
            "present_purge_witness_fact_ids": present,
            "row_kind": "event-created-purge-witness-lineage",
            "source_intent_key": event["source_intent_key"],
            "wave": event["wave"],
        }
        if set(row) != EVENT_LINEAGE_ROW_FIELDS:
            _fail("event-created witness-lineage row schema drifted")
        rows.append(row)
    if (
        len(rows) not in {179, 184, 189}
        or len(p_w1_by_capability) != 15
        or len(p_prime_by_capability) != 15
        or set(p_w1_by_capability) != set(plan["witness_by_capability"])
        or set(p_prime_by_capability) != set(plan["witness_by_capability"])
    ):
        _fail("persona event-created witness-lineage cardinality drifted")
    return tuple(rows), p_w1_by_capability


def _expected_event_lineage_body(persona_id):
    rows, _p_w1 = _event_created_lineage_rows(persona_id)
    return _bounded_expected_body(
        rows,
        label="persona v2 event-created purge-witness lineage row",
        row_cap=MAX_EVENT_LINEAGE_ROW_BYTES_INCLUDING_LF,
        body_cap=MAX_EVENT_LINEAGE_BODY_BYTES,
        row_count_cap=389,
    )


def _inverted_witness_rows(persona_id=None):
    persona_ids = (
        envelope.PERSONA_IDS
        if persona_id is None
        else (_require_persona_id(persona_id) or (persona_id,))
    )
    rows = []
    seen_witness_ids = set()
    total_consumers = 0
    for selected_persona in persona_ids:
        plan = _independent_persona_plan(selected_persona)
        _lineage, p_w1_by_capability = _event_created_lineage_rows(
            selected_persona
        )
        primary_by_capability = {
            row["capability_key"]: row for row in plan["primary_rows"]
        }
        requirements = _independent_catalog_state()["witness_requirements"]
        for capability_key in sorted(
            plan["witness_by_capability"], key=_ascii
        ):
            witness = plan["witness_by_capability"][capability_key]
            primary = primary_by_capability[capability_key]
            event = p_w1_by_capability[capability_key]
            witness_id = witness["fact_id"]
            if witness_id in seen_witness_ids:
                _fail("purge witness has multiple inverted owners")
            seen_witness_ids.add(witness_id)
            consumer_refs = [
                {
                    "consumer_domain": "w0-source",
                    "consumer_role": "matching-w0-p-primary",
                    "event_intent_key": "not-applicable-w0",
                    "source_intent_key": primary["intent_key"],
                },
                {
                    "consumer_domain": "event-created-source",
                    "consumer_role": "matching-w1-p-descendant",
                    "event_intent_key": event["event_intent_key"],
                    "source_intent_key": event["after_source_intent_key"],
                },
            ]
            row = {
                "capability_key": capability_key,
                "consumer_count": 2,
                "consumer_refs": consumer_refs,
                "persona_id": selected_persona,
                "purge_witness_key": requirements[capability_key][
                    "purge_witness_key"
                ],
                "row_kind": "purge-witness-inverted-consumers",
                "witness_fact_id": witness_id,
            }
            if set(row) != INVERTED_WITNESS_ROW_FIELDS:
                _fail("purge-witness inverted row schema drifted")
            rows.append(row)
            total_consumers += len(consumer_refs)
    expected_rows = 300 if persona_id is None else 15
    if len(rows) != expected_rows or total_consumers != 2 * expected_rows:
        _fail("purge-witness inverted cardinality drifted")
    return tuple(rows)


def _expected_inverted_body(persona_id=None):
    return _bounded_expected_body(
        _inverted_witness_rows(persona_id),
        label="persona v2 purge-witness inverted row",
        row_cap=MAX_INVERTED_ROW_BYTES_INCLUDING_LF,
        body_cap=MAX_INVERTED_BODY_BYTES,
        row_count_cap=EXPECTED_INVERTED_WITNESS_COUNT,
    )


def _strict_equal(value, expected):
    if type(value) is not type(expected):
        return False
    if type(expected) is dict:
        return set(value) == set(expected) and all(
            _strict_equal(value[key], expected[key]) for key in expected
        )
    if type(expected) is list:
        return len(value) == len(expected) and all(
            _strict_equal(left, right)
            for left, right in zip(value, expected, strict=True)
        )
    return value == expected


def _require_upstream_non_authorizing(value, *, label):
    if type(value) is not dict:
        _fail(f"{label} must be an artifact object")
    authority = value.get("authority")
    if (
        value.get("g0_contract_frozen") is not False
        or type(authority) is not dict
        or not authority
        or any(
            type(flag) is not bool or flag is not False
            for flag in authority.values()
        )
    ):
        _fail(f"{label} escalated upstream authority")


def _binding(
    name,
    role,
    value,
    *,
    canonical,
    coordinates=(),
    require_non_authorizing=True,
):
    if require_non_authorizing:
        _require_upstream_non_authorizing(value, label=name)
    raw = canonical(value)
    row = {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "dependency_role": role,
        "fixture_id": value["fixture_id"],
        "fixture_schema_version": value["fixture_schema_version"],
        "name": name,
        "sha256": _sha256(raw),
    }
    for coordinate in coordinates:
        row[coordinate] = value[coordinate]
    return row


def _origin_dependencies(persona_id, origin):
    semantic_manifest = (
        source_semantic.build_source_semantic_membership_origin_manifest(
            persona_id, origin
        )
    )
    source_semantic.validate_source_semantic_membership_origin_manifest(
        persona_id, origin, semantic_manifest
    )
    _require_upstream_non_authorizing(
        semantic_manifest,
        label=f"source semantic origin {persona_id}/{origin}",
    )
    source_manifest = source_package.build_source_intent_origin_manifest(
        persona_id, origin
    )
    source_package.validate_source_intent_origin_manifest(
        persona_id, origin, source_manifest
    )
    _require_upstream_non_authorizing(
        source_manifest,
        label=f"source inventory origin {persona_id}/{origin}",
    )
    return semantic_manifest, source_manifest


def _expected_shard_receipt(persona_id, origin, descriptor):
    shard_ordinal = descriptor["shard_ordinal"]
    effective_body, maximum, count = _expected_expanded_w0_body(
        persona_id, origin, shard_ordinal
    )
    base_body = source_semantic.expanded_fact_membership_shard_body_bytes(
        persona_id, origin, shard_ordinal
    )
    if count != descriptor["row_count"]:
        _fail("expanded effective shard count differs from source descriptor")
    row = {
        "expanded_body_bytes": len(effective_body),
        "expanded_body_persisted": False,
        "expanded_body_sha256": _sha256(effective_body),
        "expanded_maximum_row_bytes_including_lf": maximum,
        "first_intent_key": descriptor["first_intent_key"],
        "last_intent_key": descriptor["last_intent_key"],
        "origin": origin,
        "persona_id": persona_id,
        "row_count": count,
        "row_kind": "effective-w0-expanded-shard-receipt",
        "source_semantic_expanded_body_sha256": _sha256(base_body),
        "source_shard_id": descriptor["shard_id"],
        "source_shard_ordinal": shard_ordinal,
    }
    if set(row) != SHARD_RECEIPT_ROW_FIELDS:
        _fail("effective W0 shard-receipt schema drifted")
    return row


def _expected_origin_rows(persona_id, origin):
    _semantic_manifest, source_manifest = _origin_dependencies(
        persona_id, origin
    )
    rows = [
        _expected_shard_receipt(persona_id, origin, descriptor)
        for descriptor in source_manifest["shard_descriptors"]
    ]
    if origin == "pilot":
        plan = _independent_persona_plan(persona_id)
        rows.extend(copy.deepcopy(plan["primary_rows"]))
        rows.extend(copy.deepcopy(plan["companion_rows"]))
        rows.extend(copy.deepcopy(plan["typed_witness_rows"]))
    return rows


def _expected_origin_body(persona_id, origin):
    body, maximum, count = _bounded_expected_body(
        _expected_origin_rows(persona_id, origin),
        label="persona v2 compact lifecycle effective-membership row",
        row_cap=MAX_COMPACT_ROW_BYTES_INCLUDING_LF,
        body_cap=MAX_ORIGIN_BODY_BYTES,
        row_count_cap=MAX_ORIGIN_ROWS,
    )
    return body, maximum, count


@_detached_lru_cache(maxsize=40)
def _expected_origin_manifest(persona_id, origin):
    _require_persona_id(persona_id)
    _require_origin(origin)
    semantic_manifest, source_manifest = _origin_dependencies(
        persona_id, origin
    )
    rows = _expected_origin_rows(persona_id, origin)
    body, maximum, count = _bounded_expected_body(
        rows,
        label="persona v2 compact lifecycle effective-membership row",
        row_cap=MAX_COMPACT_ROW_BYTES_INCLUDING_LF,
        body_cap=MAX_ORIGIN_BODY_BYTES,
        row_count_cap=MAX_ORIGIN_ROWS,
    )
    receipts = [
        row
        for row in rows
        if row["row_kind"] == "effective-w0-expanded-shard-receipt"
    ]
    primaries = [
        row
        for row in rows
        if row["row_kind"] == "primary-effective-membership-override"
    ]
    companions = [
        row
        for row in rows
        if row["row_kind"] == "companion-effective-membership-mirror"
    ]
    witnesses = [
        row
        for row in rows
        if row["row_kind"] == "typed-purge-witness-fact"
    ]
    plan = _independent_persona_plan(persona_id)
    graph_value = _independent_catalog_state()["graph_values_by_persona"][
        persona_id
    ]
    bindings = [
        _binding(
            "persona-v2-source-semantic-membership-catalog",
            "graph-normal-W0-profile-and-topic-owner",
            _independent_catalog_state()["semantic"],
            canonical=source_semantic.canonical_json_bytes,
        ),
        _binding(
            "persona-v2-lifecycle-coverage-catalog",
            "typed-purge-witness-requirement-owner",
            _independent_catalog_state()["coverage"],
            canonical=lifecycle_coverage.canonical_json_bytes,
        ),
        _binding(
            "persona-v2-source-semantic-membership-origin-manifest",
            "immutable-base-W0-membership-and-source-owned-present-fact-set-owner",
            semantic_manifest,
            canonical=source_semantic.canonical_json_bytes,
            coordinates=("persona_id", "origin"),
        ),
        _binding(
            "persona-v2-source-matched-lifecycle-persona",
            "authenticated-capability-source-match-rendition-and-event-owner",
            plan["lifecycle"],
            canonical=matched_lifecycle.canonical_json_bytes,
            coordinates=("persona_id",),
        ),
        _binding(
            "persona-v2-fact-graph",
            "persona-local-typed-fact-and-project-entity-owner",
            graph_value,
            canonical=fact_graph.canonical_json_bytes,
            coordinates=("persona_id",),
        ),
    ]
    source_count = semantic_manifest["summary"]["source_count"]
    mode_counts = {
        "base-inheritance": source_count - len(primaries) - len(companions),
        "companion-mirror": len(companions),
        "graph-normal-plus-witness": sum(
            row["effective_membership_mode"] == "graph-normal-plus-witness"
            for row in primaries
        ),
        "graph-normal": sum(
            row["effective_membership_mode"] == "graph-normal"
            for row in primaries
        ),
    }
    value = {
        "artifact_kind": ORIGIN_KIND,
        "artifact_schema": ORIGIN_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {field: False for field in sorted(AUTHORITY_FIELDS)},
        "body_descriptor": {
            "body_bytes": len(body),
            "body_persisted": True,
            "body_sha256": _sha256(body),
            "file_name": (
                f"{persona_id}-lifecycle-effective-membership-{origin}.jsonl"
            ),
            "maximum_row_bytes_including_lf": maximum,
            "row_count": count,
        },
        "canonical_limits": {
            "max_compact_body_bytes": MAX_ORIGIN_BODY_BYTES,
            "max_compact_row_bytes_including_lf": (
                MAX_COMPACT_ROW_BYTES_INCLUDING_LF
            ),
            "max_compact_rows": MAX_ORIGIN_ROWS,
            "max_expanded_row_bytes_including_lf": (
                MAX_EXPANDED_ROW_BYTES_INCLUDING_LF
            ),
            "max_expanded_shard_body_bytes": MAX_EXPANDED_SHARD_BODY_BYTES,
            "max_expanded_rows_per_shard": MAX_EXPANDED_ROWS_PER_SHARD,
            "max_manifest_bytes": MAX_ORIGIN_MANIFEST_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_origin_w0_memberships_effectively_reconciled": True,
            "expanded_effective_bodies_persisted": False,
            "formal_namespace_completion_authorized": False,
            "incidental_lifecycle_sources_inherit_complete_base_membership": True,
            "source_owned_present_fact_set_keys_preserved": True,
        },
        "completion_scope": (
            "one-persona-one-origin-effective-w0-membership-sparse-owner-and-"
            "streaming-receipts-no-solution-render-write-history-execution-or-g0"
        ),
        "dependency_direction_contract": {
            "base_and_effective_membership_are_not_union_owners": True,
            "base_full_membership_remains_corpus-input-closure": True,
            "expanded_effective_rows_are_nonpersisted-verification-views": True,
            "source_inventory_or_semantic_origins_may_back_bind_this_artifact": False,
        },
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "input_binding_order": [row["name"] for row in bindings],
        "input_bindings": bindings,
        "origin": origin,
        "persona_id": persona_id,
        "remaining_blockers": [
            "joint-scope-bucket-cohort-quota-solution-and-proof",
            "solution-compiled-complete-post-W0-membership-and-history-plan",
            "filesystem-materialization-capacity-and-kio-observation",
            "formal-G0-approval",
        ],
        "summary": {
            "compact_companion_mirror_count": len(companions),
            "compact_primary_override_count": len(primaries),
            "compact_shard_receipt_count": len(receipts),
            "compact_typed_witness_count": len(witnesses),
            "effective_w0_mode_counts": mode_counts,
            "expanded_effective_body_bytes": sum(
                row["expanded_body_bytes"] for row in receipts
            ),
            "maximum_compact_row_bytes_including_lf": maximum,
            "maximum_expanded_row_bytes_including_lf": max(
                row["expanded_maximum_row_bytes_including_lf"]
                for row in receipts
            ),
            "present_fact_reference_count": semantic_manifest["summary"][
                "present_fact_reference_count"
            ]
            + (715 if origin == "pilot" else 0),
            "source_count": source_count,
            "source_shard_count": len(receipts),
        },
    }
    _require_all_false_authority(value, label="effective origin manifest")
    _canonical(
        value,
        label="persona v2 lifecycle effective-membership origin manifest",
        maximum=MAX_ORIGIN_MANIFEST_BYTES,
    )
    return value


def _authenticated_artifact_provider(
    provider, args, *, expected, maximum, label
):
    if not callable(provider):
        _fail(f"{label} provider is not callable")
    expected_raw = _canonical(expected, label=label, maximum=maximum)
    try:
        first = provider(*args)
    except Exception as error:
        _fail(f"{label} provider failed: {error}")
    if type(first) is not dict:
        _fail(f"{label} provider must return an exact object")
    first_raw = _canonical(first, label=label, maximum=maximum)
    if not hmac.compare_digest(first_raw, expected_raw):
        _fail(f"{label} provider differs from independent reconstruction")
    try:
        replay = provider(*args)
    except Exception as error:
        _fail(f"{label} replay provider failed: {error}")
    if type(replay) is not dict:
        _fail(f"{label} replay provider must return an exact object")
    replay_raw = _canonical(replay, label=label, maximum=maximum)
    if not hmac.compare_digest(first_raw, replay_raw):
        _fail(f"{label} replay provider is nondeterministic")
    return json.loads(first_raw)


def validate_lifecycle_effective_membership_origin_manifest(
    persona_id,
    origin,
    value,
    *,
    compact_body_provider=None,
    expanded_w0_body_provider=None,
    _audit=None,
):
    """Validate one detached origin owner and every bounded body provider."""

    _require_persona_id(persona_id)
    _require_origin(origin)
    snapshot, opening_raw = _snapshot(
        value,
        label="persona v2 lifecycle effective-membership origin manifest",
        maximum=MAX_ORIGIN_MANIFEST_BYTES,
    )
    try:
        _require_actual_origin_security_invariants(
            snapshot,
            expected_persona_id=persona_id,
            expected_origin=origin,
        )
        expected = copy.deepcopy(_expected_origin_manifest(persona_id, origin))
        if not _strict_equal(snapshot, expected):
            _fail("effective-membership origin differs from reconstruction")
        descriptor = snapshot["body_descriptor"]
        if not callable(compact_body_provider) or not callable(
            expanded_w0_body_provider
        ):
            _fail("origin validation requires both bounded body providers")
        compact = _authenticated_body(
            compact_body_provider,
            (persona_id, origin),
            expected_bytes=descriptor["body_bytes"],
            expected_sha256=descriptor["body_sha256"],
            hard_cap=MAX_ORIGIN_BODY_BYTES,
            label="compact effective-membership origin body",
        )
        expected_compact, _maximum, _count = _expected_origin_body(
            persona_id, origin
        )
        if not hmac.compare_digest(compact, expected_compact):
            _fail("compact origin body differs from independent reconstruction")
        compact_rows = _parse_jsonl(
            compact,
            label="compact effective-membership origin body",
            maximum_row_bytes=MAX_COMPACT_ROW_BYTES_INCLUDING_LF,
            maximum_rows=MAX_ORIGIN_ROWS,
        )
        receipts = [
            row
            for row in compact_rows
            if row.get("row_kind") == "effective-w0-expanded-shard-receipt"
        ]
        if len(receipts) != snapshot["summary"]["source_shard_count"]:
            _fail("compact body shard receipts do not close the manifest")
        for receipt in receipts:
            if set(receipt) != SHARD_RECEIPT_ROW_FIELDS:
                _fail("effective W0 shard receipt has an unexpected schema")
            args = (persona_id, origin, receipt["source_shard_ordinal"])
            body = _authenticated_body(
                expanded_w0_body_provider,
                args,
                expected_bytes=receipt["expanded_body_bytes"],
                expected_sha256=receipt["expanded_body_sha256"],
                hard_cap=MAX_EXPANDED_SHARD_BODY_BYTES,
                label="expanded effective W0 membership shard",
            )
            expected_body, expected_maximum, expected_count = (
                _expected_expanded_w0_body(*args)
            )
            if not hmac.compare_digest(body, expected_body):
                _fail("expanded effective W0 shard differs from reconstruction")
            rows = _parse_jsonl(
                body,
                label="expanded effective W0 membership shard",
                maximum_row_bytes=MAX_EXPANDED_ROW_BYTES_INCLUDING_LF,
                maximum_rows=MAX_EXPANDED_ROWS_PER_SHARD,
            )
            if (
                len(rows) != expected_count
                or expected_count != receipt["row_count"]
                or expected_maximum
                != receipt["expanded_maximum_row_bytes_including_lf"]
                or rows[0]["intent_key"] != receipt["first_intent_key"]
                or rows[-1]["intent_key"] != receipt["last_intent_key"]
                or any(set(row) != EXPANDED_W0_ROW_FIELDS for row in rows)
            ):
                _fail("expanded effective W0 shard receipt semantics drifted")
            if _audit is not None:
                shard_coordinate = (
                    persona_id,
                    origin,
                    receipt["source_shard_ordinal"],
                )
                if shard_coordinate in _audit["shard_coordinates"]:
                    _fail("effective W0 shard was audited twice")
                _audit["shard_coordinates"].add(shard_coordinate)
                for row in rows:
                    _audit_w0_row(_audit, row)
        return True
    finally:
        _reauthenticate(
            value,
            opening_raw,
            label="effective-membership origin manifest",
            maximum=MAX_ORIGIN_MANIFEST_BYTES,
        )


def _profile_origins(profile):
    _require_profile(profile)
    return ("pilot",) if profile == "pilot" else ORIGIN_ORDER


@_detached_lru_cache(maxsize=40)
def _expected_profile_manifest(persona_id, profile):
    _require_persona_id(persona_id)
    _require_profile(profile)
    origins = [
        copy.deepcopy(_expected_origin_manifest(persona_id, origin))
        for origin in _profile_origins(profile)
    ]
    bindings = [
        _binding(
            "persona-v2-lifecycle-effective-membership-origin-manifest",
            "sparse-effective-membership-origin-owner",
            origin_value,
            canonical=lambda value: _canonical(
                value,
                label="effective-membership origin manifest binding",
                maximum=MAX_ORIGIN_MANIFEST_BYTES,
            ),
            coordinates=("persona_id", "origin"),
        )
        for origin_value in origins
    ]
    mode_counts = {
        mode: sum(
            origin_value["summary"]["effective_w0_mode_counts"][mode]
            for origin_value in origins
        )
        for mode in EXPECTED_W0_MODE_COUNTS
    }
    value = {
        "artifact_kind": PROFILE_KIND,
        "artifact_schema": PROFILE_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {field: False for field in sorted(AUTHORITY_FIELDS)},
        "canonical_limits": {
            "max_manifest_bytes": MAX_PROFILE_MANIFEST_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_profile_w0_memberships_effectively_reconciled": True,
            "full_profile_exactly_reuses_pilot_origin": profile == "full",
            "post_w0_complete_membership_compiled": False,
            "semantic_namespace_completion_authorized": False,
        },
        "completion_scope": (
            "one-persona-pilot-or-full-effective-w0-membership-composition-"
            "without-post-w0-solution-history-execution-or-g0"
        ),
        "dependency_direction_contract": {
            "full_origin_order_is_pilot-then-full-residual": True,
            "full_profile_reuses_byte-identical-pilot-origin-binding": True,
            "origin_manifests_are-strictly-upstream": True,
        },
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "origin_manifest_bindings": bindings,
        "origin_order": [row["origin"] for row in origins],
        "persona_id": persona_id,
        "profile": profile,
        "remaining_blockers": [
            "joint-scope-bucket-cohort-quota-solution-and-proof",
            "solution-compiled-complete-post-W0-membership-and-history-plan",
            "physical-capacity-materialization-and-kio-observation",
            "formal-G0-approval",
        ],
        "summary": {
            "compact_body_bytes": sum(
                row["body_descriptor"]["body_bytes"] for row in origins
            ),
            "compact_row_count": sum(
                row["body_descriptor"]["row_count"] for row in origins
            ),
            "effective_w0_mode_counts": mode_counts,
            "origin_manifest_count": len(origins),
            "present_fact_reference_count": sum(
                row["summary"]["present_fact_reference_count"]
                for row in origins
            ),
            "source_count": sum(
                row["summary"]["source_count"] for row in origins
            ),
            "source_shard_count": sum(
                row["summary"]["source_shard_count"] for row in origins
            ),
        },
    }
    if value["summary"]["source_count"] != envelope.profile_file_count(
        persona_id, profile
    ):
        _fail("effective-membership profile source count drifted")
    _require_all_false_authority(value, label="effective profile manifest")
    _canonical(
        value,
        label="persona v2 lifecycle effective-membership profile manifest",
        maximum=MAX_PROFILE_MANIFEST_BYTES,
    )
    return value


def validate_lifecycle_effective_membership_profile_manifest(
    persona_id, profile, value
):
    _require_persona_id(persona_id)
    _require_profile(profile)
    snapshot, opening_raw = _snapshot(
        value,
        label="persona v2 lifecycle effective-membership profile manifest",
        maximum=MAX_PROFILE_MANIFEST_BYTES,
    )
    try:
        _require_actual_profile_security_invariants(
            snapshot,
            expected_persona_id=persona_id,
            expected_profile=profile,
        )
        expected = copy.deepcopy(
            _expected_profile_manifest(persona_id, profile)
        )
        if not _strict_equal(snapshot, expected):
            _fail("effective-membership profile differs from reconstruction")
        return True
    finally:
        _reauthenticate(
            value,
            opening_raw,
            label="effective-membership profile manifest",
            maximum=MAX_PROFILE_MANIFEST_BYTES,
        )


@_detached_lru_cache(maxsize=20)
def _expected_content_projection(persona_id):
    _require_persona_id(persona_id)
    plan = _independent_persona_plan(persona_id)
    primary_rows = []
    for source in plan["primary_rows"]:
        row = {
            key: copy.deepcopy(source[key])
            for key in CONTENT_PRIMARY_ROW_FIELDS
            if key != "row_kind"
        }
        row["row_kind"] = "effective-primary-membership-content"
        if set(row) != CONTENT_PRIMARY_ROW_FIELDS:
            _fail("primary content row schema drifted")
        primary_rows.append(row)
    companion_rows = []
    for source in plan["companion_rows"]:
        row = {
            key: copy.deepcopy(source[key])
            for key in CONTENT_COMPANION_ROW_FIELDS
            if key != "row_kind"
        }
        row["row_kind"] = "effective-companion-membership-content"
        if set(row) != CONTENT_COMPANION_ROW_FIELDS:
            _fail("companion content row schema drifted")
        companion_rows.append(row)
    witness_rows = []
    for source in plan["typed_witness_rows"]:
        row = {
            key: copy.deepcopy(source[key])
            for key in CONTENT_WITNESS_ROW_FIELDS
            if key != "row_kind"
        }
        row["row_kind"] = "typed-purge-witness-content"
        if set(row) != CONTENT_WITNESS_ROW_FIELDS:
            _fail("typed witness content row schema drifted")
        witness_rows.append(row)
    shard_rows = []
    for origin in ORIGIN_ORDER:
        for source in _expected_origin_rows(persona_id, origin):
            if source["row_kind"] != "effective-w0-expanded-shard-receipt":
                continue
            row = {
                "body_bytes": source["expanded_body_bytes"],
                "body_sha256": source["expanded_body_sha256"],
                "first_intent_key": source["first_intent_key"],
                "last_intent_key": source["last_intent_key"],
                "origin": source["origin"],
                "row_count": source["row_count"],
                "row_kind": "effective-membership-shard-content-commitment",
                "source_shard_id": source["source_shard_id"],
            }
            if set(row) != CONTENT_SHARD_COMMITMENT_FIELDS:
                _fail("effective shard content commitment schema drifted")
            shard_rows.append(row)
    value = {
        "artifact_kind": PROJECTION_KIND,
        "artifact_schema": PROJECTION_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "content_rules": {
            "base_content_context_membership_fields_must_be_removed": True,
            "effective_membership_is_single_namespace_owner": True,
            "event_and_inverted_views_are-input-closure-only": True,
            "projection_excludes": [
                "base-fact-profile-pointers",
                "completion-and-review-state",
                "derivation-and-verification-view-receipts",
                "execution-and-capacity-state",
                "full-upstream-bindings-and-digests",
                "physical-scope-path-quota-and-identifiers",
                "query-oracle-answer-relevance-use-case-and-format-selection",
                "runtime-observations",
            ],
        },
        "content_sections": {
            "effective_companion_membership_rows": companion_rows,
            "effective_membership_shard_commitments": shard_rows,
            "effective_primary_membership_rows": primary_rows,
            "typed_purge_witness_rows": witness_rows,
        },
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "persona_id": persona_id,
        "summary": {
            "companion_membership_row_count": len(companion_rows),
            "effective_shard_commitment_count": len(shard_rows),
            "primary_membership_row_count": len(primary_rows),
            "typed_purge_witness_row_count": len(witness_rows),
        },
    }
    _reject_prohibited_keys(value)
    raw = _canonical(
        value,
        label="persona v2 effective-membership content projection",
        maximum=MAX_CONTENT_PROJECTION_BYTES,
    )
    if len(raw) > TARGET_CONTENT_PROJECTION_BYTES:
        _fail("effective-membership content projection exceeds target")
    return value


def validate_lifecycle_effective_membership_content_projection(
    persona_id, value
):
    _require_persona_id(persona_id)
    snapshot, opening_raw = _snapshot(
        value,
        label="persona v2 effective-membership content projection",
        maximum=MAX_CONTENT_PROJECTION_BYTES,
    )
    try:
        _reject_prohibited_keys(snapshot)
        _require_actual_projection_pin_shapes(
            snapshot,
            expected_persona_id=persona_id,
            opening_raw=opening_raw,
        )
        expected = copy.deepcopy(_expected_content_projection(persona_id))
        if not _strict_equal(snapshot, expected):
            _fail("effective content projection differs from reconstruction")
        return True
    finally:
        _reauthenticate(
            value,
            opening_raw,
            label="effective-membership content projection",
            maximum=MAX_CONTENT_PROJECTION_BYTES,
        )


@_detached_lru_cache(maxsize=1)
def _witness_registry():
    registry = {}
    incidental = set()
    for persona_id in envelope.PERSONA_IDS:
        plan = _independent_persona_plan(persona_id)
        incidental.update(plan["incidental_intent_keys"])
        primary_by_capability = {
            row["capability_key"]: row for row in plan["primary_rows"]
        }
        for capability_key, witness in plan["witness_by_capability"].items():
            fact_id = witness["fact_id"]
            primary = primary_by_capability[capability_key]
            if fact_id in registry:
                _fail("typed purge witness ID is not suite-global unique")
            registry[fact_id] = {
                "capability_key": capability_key,
                "persona_id": persona_id,
                "purge_witness_key": witness["purge_witness_key"],
                "w0_intent_key": primary["intent_key"],
            }
    if len(registry) != EXPECTED_TYPED_WITNESS_COUNT or len(incidental) != 100:
        _fail("witness/I5 registry cardinality drifted")
    return {"incidental": frozenset(incidental), "witnesses": registry}


def _new_suite_audit():
    registry = _witness_registry()
    return {
        "consumers": {
            fact_id: [] for fact_id in registry["witnesses"]
        },
        "domain_counts": Counter(),
        "event_created_count": 0,
        "fact_cardinality_counts": Counter(),
        "incidental": registry["incidental"],
        "mode_counts": Counter(),
        "p_w1_after_by_capability": {},
        "present_fact_reference_count": 0,
        "shard_coordinates": set(),
        "source_count": 0,
        "witnesses": registry["witnesses"],
    }


def _audit_w0_row(audit, row):
    if set(row) != EXPANDED_W0_ROW_FIELDS:
        _fail("suite audit received a malformed effective W0 row")
    mode = row["effective_membership_mode"]
    if mode not in EXPECTED_W0_MODE_COUNTS:
        _fail("suite audit received an unknown effective W0 mode")
    if row["intent_key"] in audit["incidental"] and mode != "base-inheritance":
        _fail("I5 lifecycle source did not retain base membership")
    present = row["present_fact_ids"]
    explicit = row["witness_fact_ids"]
    if (
        type(present) is not list
        or type(explicit) is not list
        or len(present) != len(set(present))
        or len(explicit) != len(set(explicit))
    ):
        _fail("suite audit found noncanonical fact membership")
    embedded = [
        fact_id
        for fact_id in present
        if fact_id in audit["witnesses"]
        or (
            type(fact_id) is str
            and fact_id.startswith("purge-witness-fact-")
        )
    ]
    if explicit != embedded or any(
        fact_id not in audit["witnesses"] for fact_id in embedded
    ):
        _fail("unknown or untyped witness appears in effective W0 membership")
    fact_count = len(present)
    if fact_count == 0 and not explicit:
        bucket = "empty"
    elif fact_count == 1 and not explicit:
        bucket = "singleton"
    elif fact_count == 7 and not explicit:
        bucket = "conflict-branch"
    elif fact_count == 8 and not explicit:
        bucket = "graph-normal-only"
    elif fact_count == 9 and len(explicit) == 1:
        bucket = "graph-normal-plus-witness"
    else:
        _fail("effective W0 fact-cardinality bucket drifted")
    if mode == "graph-normal-plus-witness" and bucket != (
        "graph-normal-plus-witness"
    ):
        _fail("P primary mode lacks its exact witness union")
    if mode != "graph-normal-plus-witness" and explicit:
        _fail("purge witness leaked outside a P primary mode")
    for fact_id in explicit:
        owner = audit["witnesses"][fact_id]
        if (
            row["persona_id"] != owner["persona_id"]
            or row["intent_key"] != owner["w0_intent_key"]
        ):
            _fail("purge witness leaked to a foreign W0 source")
        audit["consumers"][fact_id].append(
            {
                "consumer_domain": "w0-source",
                "consumer_role": "matching-w0-p-primary",
                "event_intent_key": "not-applicable-w0",
                "source_intent_key": row["intent_key"],
            }
        )
    audit["mode_counts"][mode] += 1
    audit["fact_cardinality_counts"][bucket] += 1
    audit["present_fact_reference_count"] += fact_count
    audit["source_count"] += 1
    audit["domain_counts"][(row["persona_id"], row["origin"])] += 1


def _audit_event_lineage_row(audit, row):
    if set(row) != EVENT_LINEAGE_ROW_FIELDS:
        _fail("suite audit received a malformed event-lineage row")
    expected_after = (
        f"{row['persona_id']}-pre-solve-source-intent-"
        f"{row['event_sequence_ordinal']:04d}"
    )
    if row["after_source_intent_key"] != expected_after:
        _fail("event-lineage row has a noncanonical created source intent")
    explicit = row["present_purge_witness_fact_ids"]
    if type(explicit) is not list or any(
        fact_id not in audit["witnesses"] for fact_id in explicit
    ):
        _fail("event-lineage row contains an unknown purge witness")
    role = row["consumer_role"]
    if role == "matching-w1-p-descendant":
        if (
            len(explicit) != 1
            or row["event_profile_key"] != "w1-typed-edit"
            or row["fact_transition_rule"] != "facts/typed-revision"
        ):
            _fail("W1 P descendant witness lineage drifted")
        fact_id = explicit[0]
        owner = audit["witnesses"][fact_id]
        if (
            row["persona_id"] != owner["persona_id"]
            or row["capability_key"] != owner["capability_key"]
            or row["source_intent_key"] != owner["w0_intent_key"]
        ):
            _fail("W1 P descendant consumed a foreign witness")
        if row["capability_key"] in audit["p_w1_after_by_capability"]:
            _fail("P capability has multiple W1 created descendants")
        audit["p_w1_after_by_capability"][row["capability_key"]] = row[
            "after_source_intent_key"
        ]
        audit["consumers"][fact_id].append(
            {
                "consumer_domain": "event-created-source",
                "consumer_role": "matching-w1-p-descendant",
                "event_intent_key": row["event_intent_key"],
                "source_intent_key": row["after_source_intent_key"],
            }
        )
    elif role == "p-prime-capacity-replacement":
        owners_by_capability = {
            owner["capability_key"]: owner
            for owner in audit["witnesses"].values()
        }
        owner = owners_by_capability.get(row["capability_key"])
        if (
            explicit
            or row["event_profile_key"] != "w5-create-p-prime"
            or row["fact_transition_rule"] != "facts/repl-distinct"
            or owner is None
            or row["persona_id"] != owner["persona_id"]
            or row["source_intent_key"]
            != audit["p_w1_after_by_capability"].get(
                row["capability_key"]
            )
        ):
            _fail("P-prime did not explicitly exclude its witness")
    elif role == "other-event-created-intent":
        witness_capabilities = {
            owner["capability_key"] for owner in audit["witnesses"].values()
        }
        if explicit or row["capability_key"] in witness_capabilities:
            _fail("purge witness leaked to another event-created source")
    else:
        _fail("event-created witness consumer role is unknown")
    audit["event_created_count"] += 1


def _finalize_suite_audit(audit):
    if audit["source_count"] != EXPECTED_SOURCE_COUNT:
        _fail("suite audit did not cover exactly 203000 W0 sources")
    if len(audit["shard_coordinates"]) != EXPECTED_SHARD_RECEIPT_COUNT:
        _fail("suite audit did not cover exactly 73 W0 source shards")
    expected_domains = {
        (persona_id, origin): (
            envelope.profile_file_count(persona_id, "pilot")
            if origin == "pilot"
            else envelope.profile_file_count(persona_id, "full")
            - envelope.profile_file_count(persona_id, "pilot")
        )
        for persona_id in envelope.PERSONA_IDS
        for origin in ORIGIN_ORDER
    }
    if dict(audit["domain_counts"]) != expected_domains:
        _fail("suite audit source persona/origin domain drifted")
    if dict(audit["mode_counts"]) != EXPECTED_W0_MODE_COUNTS:
        _fail("suite audit effective W0 mode counts drifted")
    if dict(audit["fact_cardinality_counts"]) != (
        EXPECTED_W0_FACT_DISTRIBUTION
    ):
        _fail("suite audit effective W0 fact distribution drifted")
    if audit["present_fact_reference_count"] != (
        EXPECTED_PRESENT_FACT_REFERENCE_COUNT
    ):
        _fail("suite audit effective W0 fact-reference count drifted")
    if audit["event_created_count"] != EXPECTED_EVENT_CREATED_LINEAGE_COUNT:
        _fail("suite audit event-created lineage count drifted")
    for fact_id, refs in audit["consumers"].items():
        if len(refs) != 2 or [row["consumer_role"] for row in refs] != [
            "matching-w0-p-primary",
            "matching-w1-p-descendant",
        ]:
            _fail(f"purge witness consumer complement drifted: {fact_id}")
    return {
        "fact_cardinality_counts": dict(audit["fact_cardinality_counts"]),
        "mode_counts": dict(audit["mode_counts"]),
        "present_fact_reference_count": audit[
            "present_fact_reference_count"
        ],
        "source_count": audit["source_count"],
        "streamed_complete_domain_verified": True,
    }


def _expected_view_receipt(persona_id):
    event_body, event_maximum, event_count = _expected_event_lineage_body(
        persona_id
    )
    inverted_body, inverted_maximum, inverted_count = _expected_inverted_body(
        persona_id
    )
    return {
        "event_created_lineage_body_bytes": len(event_body),
        "event_created_lineage_body_persisted": False,
        "event_created_lineage_body_sha256": _sha256(event_body),
        "event_created_lineage_maximum_row_bytes_including_lf": event_maximum,
        "event_created_lineage_row_count": event_count,
        "inverted_witness_body_bytes": len(inverted_body),
        "inverted_witness_body_persisted": False,
        "inverted_witness_body_sha256": _sha256(inverted_body),
        "inverted_witness_maximum_row_bytes_including_lf": inverted_maximum,
        "inverted_witness_row_count": inverted_count,
        "persona_id": persona_id,
    }


def _require_frozen_suite_pins(value, origins, profiles, projections):
    suite_raw = _canonical(
        value,
        label="persona v2 lifecycle effective-membership suite descriptor",
        maximum=MAX_SUITE_DESCRIPTOR_BYTES,
    )
    origin_raw = {
        (row["persona_id"], row["origin"]): _canonical(
            row,
            label="persona v2 lifecycle effective-membership origin manifest",
            maximum=MAX_ORIGIN_MANIFEST_BYTES,
        )
        for row in origins
    }
    profile_raw = [
        _canonical(
            row,
            label="persona v2 lifecycle effective-membership profile manifest",
            maximum=MAX_PROFILE_MANIFEST_BYTES,
        )
        for row in profiles
    ]
    projection_raw = {
        row["persona_id"]: _canonical(
            row,
            label="persona v2 effective-membership content projection",
            maximum=MAX_CONTENT_PROJECTION_BYTES,
        )
        for row in projections
    }
    p01_pilot = origins[
        next(
            index
            for index, row in enumerate(origins)
            if row["persona_id"] == "p01" and row["origin"] == "pilot"
        )
    ]["body_descriptor"]
    p12_residual = origins[
        next(
            index
            for index, row in enumerate(origins)
            if row["persona_id"] == "p12"
            and row["origin"] == "full-residual"
        )
    ]["body_descriptor"]
    receipts = value["verification_view_receipts"]
    if (
        len(suite_raw) != EXPECTED_SUITE_CANONICAL_BYTES
        or _sha256(suite_raw) != EXPECTED_SUITE_SHA256
        or max(map(len, origin_raw.values()))
        != EXPECTED_MAX_ORIGIN_MANIFEST_BYTES
        or max(map(len, profile_raw)) != EXPECTED_MAX_PROFILE_MANIFEST_BYTES
        or max(map(len, projection_raw.values()))
        != EXPECTED_MAX_CONTENT_PROJECTION_BYTES
        or max(
            row["body_descriptor"]["maximum_row_bytes_including_lf"]
            for row in origins
        )
        != EXPECTED_MAX_COMPACT_ROW_BYTES_INCLUDING_LF
        or max(
            row["summary"]["maximum_expanded_row_bytes_including_lf"]
            for row in origins
        )
        != EXPECTED_MAX_EXPANDED_ROW_BYTES_INCLUDING_LF
        or max(
            row[
                "event_created_lineage_maximum_row_bytes_including_lf"
            ]
            for row in receipts
        )
        != EXPECTED_MAX_EVENT_LINEAGE_ROW_BYTES_INCLUDING_LF
        or max(
            row["inverted_witness_maximum_row_bytes_including_lf"]
            for row in receipts
        )
        != EXPECTED_MAX_INVERTED_ROW_BYTES_INCLUDING_LF
        or p01_pilot["body_bytes"]
        != EXPECTED_P01_PILOT_COMPACT_BODY_BYTES
        or p01_pilot["body_sha256"]
        != EXPECTED_P01_PILOT_COMPACT_BODY_SHA256
        or p12_residual["body_bytes"]
        != EXPECTED_P12_FULL_RESIDUAL_COMPACT_BODY_BYTES
        or p12_residual["body_sha256"]
        != EXPECTED_P12_FULL_RESIDUAL_COMPACT_BODY_SHA256
        or len(projection_raw["p01"])
        != EXPECTED_P01_CONTENT_PROJECTION_BYTES
        or _sha256(projection_raw["p01"])
        != EXPECTED_P01_CONTENT_PROJECTION_SHA256
    ):
        _fail("effective-membership frozen production pins drifted")


@_detached_lru_cache(maxsize=1)
def _expected_suite_descriptor():
    origins = [
        copy.deepcopy(_expected_origin_manifest(persona_id, origin))
        for persona_id in envelope.PERSONA_IDS
        for origin in ORIGIN_ORDER
    ]
    profiles = [
        copy.deepcopy(_expected_profile_manifest(persona_id, profile))
        for persona_id in envelope.PERSONA_IDS
        for profile in PROFILE_ORDER
    ]
    state = _independent_catalog_state()
    semantic_catalog = state["semantic"]
    coverage_catalog = state["coverage"]
    semantic_suite = (
        source_semantic.build_source_semantic_membership_suite_descriptor()
    )
    source_semantic.validate_source_semantic_membership_suite_descriptor(
        semantic_suite
    )
    lifecycle_suite = (
        matched_lifecycle.build_source_matched_lifecycle_suite_descriptor()
    )
    matched_lifecycle.validate_source_matched_lifecycle_suite_descriptor(
        lifecycle_suite
    )
    _require_upstream_non_authorizing(
        semantic_suite, label="source semantic suite"
    )
    _require_upstream_non_authorizing(
        lifecycle_suite, label="source-matched lifecycle suite"
    )
    input_bindings = [
        _binding(
            "persona-v2-source-semantic-membership-catalog",
            "graph-normal-W0-profile-and-topic-owner",
            semantic_catalog,
            canonical=source_semantic.canonical_json_bytes,
        ),
        _binding(
            "persona-v2-source-semantic-membership-suite",
            "authenticated-base-membership-suite-and-derivation-closure",
            semantic_suite,
            canonical=source_semantic.canonical_json_bytes,
        ),
        _binding(
            "persona-v2-lifecycle-coverage-catalog",
            "typed-purge-witness-requirement-owner",
            coverage_catalog,
            canonical=lifecycle_coverage.canonical_json_bytes,
        ),
        _binding(
            "persona-v2-source-matched-lifecycle-suite",
            "authenticated-source-match-rendition-and-event-owner",
            lifecycle_suite,
            canonical=matched_lifecycle.canonical_json_bytes,
        ),
    ]
    origin_bindings = [
        _binding(
            "persona-v2-lifecycle-effective-membership-origin-manifest",
            "sparse-effective-membership-origin-owner",
            origin_value,
            canonical=lambda value: _canonical(
                value,
                label="effective origin binding",
                maximum=MAX_ORIGIN_MANIFEST_BYTES,
            ),
            coordinates=("persona_id", "origin"),
        )
        for origin_value in origins
    ]
    profile_bindings = [
        _binding(
            "persona-v2-lifecycle-effective-membership-profile-manifest",
            "effective-membership-profile-composition",
            profile_value,
            canonical=lambda value: _canonical(
                value,
                label="effective profile binding",
                maximum=MAX_PROFILE_MANIFEST_BYTES,
            ),
            coordinates=("persona_id", "profile"),
        )
        for profile_value in profiles
    ]
    receipts = [
        _expected_view_receipt(persona_id)
        for persona_id in envelope.PERSONA_IDS
    ]
    projections = [
        copy.deepcopy(_expected_content_projection(persona_id))
        for persona_id in envelope.PERSONA_IDS
    ]
    projection_bindings = [
        _binding(
            "persona-v2-lifecycle-effective-membership-content-projection",
            "persona-semantic-namespace-effective-membership-content",
            projection,
            canonical=lambda value: _canonical(
                value,
                label="effective content projection binding",
                maximum=MAX_CONTENT_PROJECTION_BYTES,
            ),
            coordinates=("persona_id",),
            require_non_authorizing=False,
        )
        for projection in projections
    ]
    full_profiles = [row for row in profiles if row["profile"] == "full"]
    mode_counts = {
        mode: sum(
            row["summary"]["effective_w0_mode_counts"][mode]
            for row in full_profiles
        )
        for mode in EXPECTED_W0_MODE_COUNTS
    }
    value = {
        "artifact_kind": SUITE_KIND,
        "artifact_schema": SUITE_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {field: False for field in sorted(AUTHORITY_FIELDS)},
        "canonical_limits": {
            "max_content_projection_bytes": MAX_CONTENT_PROJECTION_BYTES,
            "max_event_created_lineage_body_bytes_per_persona": (
                MAX_EVENT_LINEAGE_BODY_BYTES
            ),
            "max_inverted_witness_body_bytes": MAX_INVERTED_BODY_BYTES,
            "max_suite_descriptor_bytes": MAX_SUITE_DESCRIPTOR_BYTES,
            "self_hash_embedded": False,
            "target_content_projection_bytes": TARGET_CONTENT_PROJECTION_BYTES,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_203000_effective_w0_memberships_reconciled": True,
            "all_3630_event_created_witness_lineages_receipted": True,
            "all_300_purge_witnesses_have_exactly_two_consumers": True,
            "all_73_expanded_effective_shards_receipted": True,
            "expanded_and_inverted_views_persisted": False,
            "post_w0_complete_membership_compiled": False,
            "semantic_namespace_completion_authorized": False,
        },
        "completion_scope": (
            "all-twenty-persona-effective-w0-membership-and-purge-witness-"
            "isolation-proof-only-no-solved-complete-post-w0-history-execution-or-g0"
        ),
        "content_projection_bindings": projection_bindings,
        "dependency_direction_contract": {
            "base-membership-and-reconciliation-receipts-remain-input-closure": True,
            "effective-W0-is-the-single-formal-namespace-membership-owner": True,
            "witness-isolation-does-not-claim-complete-post-W0-membership": True,
        },
        "effective_w0_distribution_audit": {
            "fact_cardinality_counts": dict(EXPECTED_W0_FACT_DISTRIBUTION),
            "mode_counts": dict(EXPECTED_W0_MODE_COUNTS),
            "present_fact_reference_count": (
                EXPECTED_PRESENT_FACT_REFERENCE_COUNT
            ),
            "source_count": EXPECTED_SOURCE_COUNT,
            "streamed_complete_domain_verified": True,
        },
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "input_binding_order": [row["name"] for row in input_bindings],
        "input_bindings": input_bindings,
        "orders": {
            "origin": list(ORIGIN_ORDER),
            "origin_manifests": "persona-then-origin",
            "persona": list(envelope.PERSONA_IDS),
            "profile": list(PROFILE_ORDER),
            "profile_manifests": "persona-then-profile",
            "verification_view_receipts": "persona-id",
        },
        "origin_manifest_bindings": origin_bindings,
        "profile_manifest_bindings": profile_bindings,
        "remaining_blockers": [
            "joint-scope-bucket-cohort-quota-solution-and-proof",
            "solution-compiled-complete-post-W0-membership-and-history-plan",
            "physical-capacity-materialization-and-kio-observation",
            "formal-G0-approval",
        ],
        "summary": {
            "compact_companion_mirror_count": sum(
                row["summary"]["compact_companion_mirror_count"]
                for row in origins
            ),
            "compact_primary_override_count": sum(
                row["summary"]["compact_primary_override_count"]
                for row in origins
            ),
            "compact_row_count": sum(
                row["body_descriptor"]["row_count"] for row in origins
            ),
            "compact_shard_receipt_count": sum(
                row["summary"]["compact_shard_receipt_count"]
                for row in origins
            ),
            "compact_typed_witness_count": sum(
                row["summary"]["compact_typed_witness_count"]
                for row in origins
            ),
            "content_projection_count": len(projections),
            "effective_w0_mode_counts": mode_counts,
            "event_created_lineage_count": sum(
                row["event_created_lineage_row_count"] for row in receipts
            ),
            "inverted_consumer_reference_count": 2
            * sum(row["inverted_witness_row_count"] for row in receipts),
            "inverted_witness_count": sum(
                row["inverted_witness_row_count"] for row in receipts
            ),
            "origin_manifest_count": len(origins),
            "persona_count": len(envelope.PERSONA_IDS),
            "present_fact_reference_count": sum(
                row["summary"]["present_fact_reference_count"]
                for row in full_profiles
            ),
            "profile_manifest_count": len(profiles),
            "source_count": sum(
                row["summary"]["source_count"] for row in full_profiles
            ),
        },
        "verification_view_receipts": receipts,
    }
    summary = value["summary"]
    if (
        summary["compact_row_count"] != EXPECTED_COMPACT_ROW_COUNT
        or summary["compact_shard_receipt_count"]
        != EXPECTED_SHARD_RECEIPT_COUNT
        or summary["compact_primary_override_count"]
        != EXPECTED_PRIMARY_OVERRIDE_COUNT
        or summary["compact_companion_mirror_count"]
        != EXPECTED_COMPANION_MIRROR_COUNT
        or summary["compact_typed_witness_count"]
        != EXPECTED_TYPED_WITNESS_COUNT
        or summary["source_count"] != EXPECTED_SOURCE_COUNT
        or summary["present_fact_reference_count"]
        != EXPECTED_PRESENT_FACT_REFERENCE_COUNT
        or summary["event_created_lineage_count"]
        != EXPECTED_EVENT_CREATED_LINEAGE_COUNT
        or summary["inverted_witness_count"] != EXPECTED_INVERTED_WITNESS_COUNT
        or summary["inverted_consumer_reference_count"]
        != EXPECTED_INVERTED_CONSUMER_REFERENCE_COUNT
        or summary["content_projection_count"] != len(envelope.PERSONA_IDS)
        or mode_counts != EXPECTED_W0_MODE_COUNTS
    ):
        _fail("effective-membership suite aggregate drifted")
    _require_all_false_authority(value, label="effective suite descriptor")
    _require_frozen_suite_pins(value, origins, profiles, projections)
    return value


def validate_lifecycle_effective_membership_suite_descriptor(
    value,
    *,
    origin_manifest_provider=None,
    profile_manifest_provider=None,
    compact_body_provider=None,
    expanded_w0_body_provider=None,
    event_lineage_provider=None,
    inverted_provider=None,
    content_projection_provider=None,
):
    """Validate the complete sparse package and all verification views."""

    snapshot, opening_raw = _snapshot(
        value,
        label="persona v2 lifecycle effective-membership suite descriptor",
        maximum=MAX_SUITE_DESCRIPTOR_BYTES,
    )
    try:
        _require_actual_suite_security_invariants(
            snapshot, opening_raw=opening_raw
        )
        expected = copy.deepcopy(_expected_suite_descriptor())
        if not _strict_equal(snapshot, expected):
            _fail("effective-membership suite differs from reconstruction")
        providers = (
            origin_manifest_provider,
            profile_manifest_provider,
            compact_body_provider,
            expanded_w0_body_provider,
            event_lineage_provider,
            inverted_provider,
            content_projection_provider,
        )
        if any(not callable(provider) for provider in providers):
            _fail("suite validation requires all bounded providers")

        audit = _new_suite_audit()
        for persona_id in envelope.PERSONA_IDS:
            for origin in ORIGIN_ORDER:
                expected_origin = copy.deepcopy(
                    _expected_origin_manifest(persona_id, origin)
                )
                provided_origin = _authenticated_artifact_provider(
                    origin_manifest_provider,
                    (persona_id, origin),
                    expected=expected_origin,
                    maximum=MAX_ORIGIN_MANIFEST_BYTES,
                    label="effective-membership origin manifest provider",
                )
                validate_lifecycle_effective_membership_origin_manifest(
                    persona_id,
                    origin,
                    provided_origin,
                    compact_body_provider=compact_body_provider,
                    expanded_w0_body_provider=expanded_w0_body_provider,
                    _audit=audit,
                )
        for persona_id in envelope.PERSONA_IDS:
            for profile in PROFILE_ORDER:
                expected_profile = copy.deepcopy(
                    _expected_profile_manifest(persona_id, profile)
                )
                provided_profile = _authenticated_artifact_provider(
                    profile_manifest_provider,
                    (persona_id, profile),
                    expected=expected_profile,
                    maximum=MAX_PROFILE_MANIFEST_BYTES,
                    label="effective-membership profile manifest provider",
                )
                validate_lifecycle_effective_membership_profile_manifest(
                    persona_id, profile, provided_profile
                )
        for persona_id in envelope.PERSONA_IDS:
            expected_projection = copy.deepcopy(
                _expected_content_projection(persona_id)
            )
            provided_projection = _authenticated_artifact_provider(
                content_projection_provider,
                (persona_id,),
                expected=expected_projection,
                maximum=MAX_CONTENT_PROJECTION_BYTES,
                label="effective-membership content projection provider",
            )
            validate_lifecycle_effective_membership_content_projection(
                persona_id, provided_projection
            )

        receipts = {
            row["persona_id"]: row
            for row in snapshot["verification_view_receipts"]
        }
        if list(receipts) != list(envelope.PERSONA_IDS):
            _fail("suite verification-view receipt order drifted")
        inverted_rows_by_persona = {}
        for persona_id in envelope.PERSONA_IDS:
            receipt = receipts[persona_id]
            event_body = _authenticated_body(
                event_lineage_provider,
                (persona_id,),
                expected_bytes=receipt[
                    "event_created_lineage_body_bytes"
                ],
                expected_sha256=receipt[
                    "event_created_lineage_body_sha256"
                ],
                hard_cap=MAX_EVENT_LINEAGE_BODY_BYTES,
                label="event-created purge-witness lineage body",
            )
            expected_event_body, expected_event_maximum, expected_event_count = (
                _expected_event_lineage_body(persona_id)
            )
            if not hmac.compare_digest(event_body, expected_event_body):
                _fail("event-created lineage differs from reconstruction")
            event_rows = _parse_jsonl(
                event_body,
                label="event-created purge-witness lineage body",
                maximum_row_bytes=MAX_EVENT_LINEAGE_ROW_BYTES_INCLUDING_LF,
                maximum_rows=389,
            )
            if (
                len(event_rows) != expected_event_count
                or expected_event_count
                != receipt["event_created_lineage_row_count"]
                or expected_event_maximum
                != receipt[
                    "event_created_lineage_maximum_row_bytes_including_lf"
                ]
            ):
                _fail("event-created lineage receipt semantics drifted")
            for row in event_rows:
                _audit_event_lineage_row(audit, row)

            inverted_body = _authenticated_body(
                inverted_provider,
                (persona_id,),
                expected_bytes=receipt["inverted_witness_body_bytes"],
                expected_sha256=receipt["inverted_witness_body_sha256"],
                hard_cap=MAX_INVERTED_BODY_BYTES,
                label="inverted purge-witness body",
            )
            expected_inverted_body, expected_inverted_maximum, expected_inverted_count = (
                _expected_inverted_body(persona_id)
            )
            if not hmac.compare_digest(inverted_body, expected_inverted_body):
                _fail("inverted purge-witness body differs from reconstruction")
            inverted_rows = _parse_jsonl(
                inverted_body,
                label="inverted purge-witness body",
                maximum_row_bytes=MAX_INVERTED_ROW_BYTES_INCLUDING_LF,
                maximum_rows=15,
            )
            if (
                len(inverted_rows) != expected_inverted_count
                or expected_inverted_count
                != receipt["inverted_witness_row_count"]
                or expected_inverted_maximum
                != receipt[
                    "inverted_witness_maximum_row_bytes_including_lf"
                ]
            ):
                _fail("inverted purge-witness receipt semantics drifted")
            inverted_rows_by_persona[persona_id] = inverted_rows

        audited_distribution = _finalize_suite_audit(audit)
        if not _strict_equal(
            snapshot["effective_w0_distribution_audit"],
            audited_distribution,
        ):
            _fail("suite distribution claim differs from universal audit")
        for persona_id in envelope.PERSONA_IDS:
            for row in inverted_rows_by_persona[persona_id]:
                if set(row) != INVERTED_WITNESS_ROW_FIELDS:
                    _fail("inverted purge-witness row schema drifted")
                fact_id = row["witness_fact_id"]
                owner = audit["witnesses"].get(fact_id)
                if (
                    owner is None
                    or row["persona_id"] != owner["persona_id"]
                    or row["capability_key"] != owner["capability_key"]
                    or row["purge_witness_key"]
                    != owner["purge_witness_key"]
                    or row["consumer_count"] != 2
                    or not _strict_equal(
                        row["consumer_refs"], audit["consumers"][fact_id]
                    )
                ):
                    _fail("inverted row differs from universal consumer scan")
        return True
    finally:
        _reauthenticate(
            value,
            opening_raw,
            label="effective-membership suite descriptor",
            maximum=MAX_SUITE_DESCRIPTOR_BYTES,
        )


__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "COMPANION_MIRROR_ROW_FIELDS",
    "CONTENT_COMPANION_ROW_FIELDS",
    "CONTENT_PRIMARY_ROW_FIELDS",
    "CONTENT_SHARD_COMMITMENT_FIELDS",
    "CONTENT_WITNESS_ROW_FIELDS",
    "EVENT_LINEAGE_ROW_FIELDS",
    "EXPANDED_W0_ROW_FIELDS",
    "INVERTED_WITNESS_ROW_FIELDS",
    "ORIGIN_SCHEMA",
    "PersonaV2LifecycleEffectiveMembershipReconciliationValidationError",
    "PRIMARY_OVERRIDE_ROW_FIELDS",
    "PROFILE_SCHEMA",
    "PROJECTION_SCHEMA",
    "SHARD_RECEIPT_ROW_FIELDS",
    "SUITE_SCHEMA",
    "TYPED_WITNESS_ROW_FIELDS",
    "validate_lifecycle_effective_membership_content_projection",
    "validate_lifecycle_effective_membership_origin_manifest",
    "validate_lifecycle_effective_membership_profile_manifest",
    "validate_lifecycle_effective_membership_suite_descriptor",
]
