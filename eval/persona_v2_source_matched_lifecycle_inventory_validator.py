"""Independent validator for the source-matched lifecycle inventory.

This module intentionally does not import the matching producer.  It
re-authenticates the eight frozen upstream artifacts, independently joins the
pilot source, semantic, format, reservation, and parameter-assignment domains,
reconstructs every source selection and lifecycle event receipt, and compares
canonical bytes.  Provider callbacks are treated as untrusted and every
caller-owned object is re-authenticated after callback execution.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
from collections import Counter, defaultdict

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_lifecycle_coverage_catalog as lifecycle_coverage
    from . import persona_v2_overlay_reservation_layout as reservation_layout
    from . import persona_v2_primary_use_case_catalog as use_case_catalog
    from . import persona_v2_source_inventory_package as source_package
    from . import persona_v2_source_inventory_profile as inventory_profile
    from . import persona_v2_source_parameter_assignment_package as assignment
    from . import persona_v2_source_semantic_membership_package as source_semantic
    from . import persona_v2_variant_catalog as variant_catalog
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_lifecycle_coverage_catalog as lifecycle_coverage
    import persona_v2_overlay_reservation_layout as reservation_layout
    import persona_v2_primary_use_case_catalog as use_case_catalog
    import persona_v2_source_inventory_package as source_package
    import persona_v2_source_inventory_profile as inventory_profile
    import persona_v2_source_parameter_assignment_package as assignment
    import persona_v2_source_semantic_membership_package as source_semantic
    import persona_v2_variant_catalog as variant_catalog


PERSONA_SCHEMA = "kio.persona.pc-source-matched-lifecycle-persona/v1"
SUITE_SCHEMA = "kio.persona.pc-source-matched-lifecycle-suite/v1"
PROJECTION_SCHEMA = (
    "kio.persona.pc-source-matched-lifecycle-content-projection/v1"
)
CONTENT_PROJECTION_SCHEMA = PROJECTION_SCHEMA
ARTIFACT_SCHEMA_VERSION = 1
SCHEMA_VERSION = ARTIFACT_SCHEMA_VERSION

PERSONA_KIND = "persona-pc-v2-source-matched-lifecycle-persona"
SUITE_KIND = "persona-pc-v2-source-matched-lifecycle-suite"
PROJECTION_KIND = (
    "persona-pc-v2-source-matched-lifecycle-content-projection"
)
CONTENT_PROJECTION_KIND = PROJECTION_KIND

PERSONA_IDS = tuple(f"p{ordinal:02d}" for ordinal in range(1, 21))
ORIGIN = "pilot"

MAX_PERSONA_BYTES = 512 * 2**10
MAX_SUITE_BYTES = 512 * 2**10
MAX_CONTENT_PROJECTION_BYTES = 384 * 2**10
TARGET_CONTENT_PROJECTION_BYTES = 256 * 2**10
MAX_EVENT_BODY_BYTES = 4 * 2**20
MAX_EVENT_ROW_BYTES_INCLUDING_LF = 1_024
EXPECTED_SUITE_CANONICAL_BYTES = 14_605
EXPECTED_SUITE_SHA256 = (
    "c4508ed61c88db80b003e9ce3b7c35ea153776442bd3224964897400633dd2c8"
)

EXPECTED_PRIMARY_MATCHES_PER_PERSONA = 105
EXPECTED_COMPANION_MATCHES_PER_PERSONA = 10
EXPECTED_LIFECYCLE_SOURCE_REFS_PER_PERSONA = 115
EXPECTED_EVENT_BASELINE_PER_PERSONA = 379
EXPECTED_EVENT_SUITE_COUNT = 7_630
EXPECTED_FORMAT_WITNESS_COUNT = 93
EXPECTED_SEARCHABLE_WITNESS_COUNT = 52
EXPECTED_PENDING_WITNESS_COUNT = 33
EXPECTED_RAW_ONLY_WITNESS_COUNT = 8

CONTRIBUTOR_PRIMARY_MATCH_FIELDS = frozenset(
    {
        "allocation_class",
        "base_fact_profile_id",
        "base_language",
        "base_logical_document_key",
        "base_logical_revision_key",
        "base_topic_id",
        "capability_class_key",
        "capability_key",
        "family",
        "gate_role",
        "intent_key",
        "lifecycle_logical_document_slot_key",
        "origin",
        "parameter_cell_key",
        "reservation_status",
        "semantic_anchor_slot_ordinal",
        "source_profile_id",
        "variant_id",
    }
)
INCIDENTAL_PRIMARY_MATCH_FIELDS = frozenset(
    set(CONTRIBUTOR_PRIMARY_MATCH_FIELDS) - {"semantic_anchor_slot_ordinal"}
)
COMPANION_MATCH_FIELDS = frozenset(
    {
        "base_fact_profile_id",
        "base_language",
        "base_logical_document_key",
        "base_logical_revision_key",
        "base_topic_id",
        "companion_requirement_key",
        "effective_membership_rule",
        "family",
        "gate_role",
        "intent_key",
        "origin",
        "parameter_cell_key",
        "primary_capability_key",
        "rendition_group_key",
        "reservation_status",
        "source_profile_id",
        "variant_id",
    }
)
POSITIVE_FORMAT_WITNESS_FIELDS = frozenset(
    {
        "classification",
        "family",
        "intent_key",
        "offline_disposition",
        "parameter_cell_key",
        "physical_witness_required",
        "primary_use_case_id",
        "query_answer_anchor_required",
        "query_anchor_ref",
        "source_profile_id",
        "source_selection_kind",
        "variant_id",
    }
)
NEGATIVE_FORMAT_WITNESS_FIELDS = frozenset(
    {
        "classification",
        "family",
        "intent_key",
        "negative_expectation",
        "offline_disposition",
        "parameter_cell_key",
        "physical_witness_required",
        "primary_use_case_id",
        "query_answer_anchor_required",
        "source_profile_id",
        "source_selection_kind",
        "variant_id",
    }
)
EVENT_RECEIPT_FIELDS = frozenset(
    {
        "body_bytes",
        "body_persisted",
        "body_sha256",
        "first_event_intent_key",
        "first_event_sequence_ordinal",
        "last_event_intent_key",
        "last_event_sequence_ordinal",
        "maximum_row_bytes_including_lf",
        "persona_id",
        "row_count",
    }
)
SOURCE_EVENT_ROW_FIELDS = frozenset(
    {
        "after_source_intent_key",
        "byte_transition_rule",
        "capability_key",
        "dependency_group_key",
        "delta_rule_ref",
        "event_intent_key",
        "event_profile_key",
        "event_sequence_ordinal",
        "fact_transition_rule",
        "family",
        "gate_role",
        "path_transition_rule_key",
        "persona_id",
        "predecessor_event_intent_refs",
        "scenario_visibility_rule",
        "scope_relation_rule_key",
        "source_intent_key",
        "symbol_domain_ref",
        "variant_id",
        "wave",
        "row_kind",
    }
)
SCOPE_EVENT_ROW_FIELDS = frozenset(
    {
        "abstract_scope_slot_ordinal",
        "byte_transition_rule",
        "dependency_group_key",
        "delta_rule_ref",
        "event_intent_key",
        "event_profile_key",
        "event_sequence_ordinal",
        "fact_transition_rule",
        "path_transition_rule_key",
        "persona_id",
        "predecessor_event_intent_refs",
        "row_kind",
        "scenario_visibility_rule",
        "scope_relation_rule_key",
        "symbol_domain_ref",
        "wave",
    }
)
CONTENT_ROW_FIELDS = frozenset(
    {
        "family",
        "gate_role",
        "intent_key",
        "parameter_cell_key",
        "selection_role_refs",
        "source_profile_id",
        "variant_id",
    }
)
CONTENT_SECTIONS_FIELDS = frozenset(
    {"scope_event_rows", "source_event_rows", "source_selection_rows"}
)
CONTENT_SOURCE_EVENT_ROW_FIELDS = frozenset(
    {
        "after_source_intent_key",
        "dependency_group_key",
        "delta_rule_ref",
        "event_intent_key",
        "event_profile_key",
        "fact_transition_rule",
        "path_transition_rule_key",
        "predecessor_event_intent_refs",
        "scenario_visibility_rule",
        "scope_relation_rule_key",
        "source_intent_key",
    }
)
CONTENT_SCOPE_EVENT_ROW_FIELDS = frozenset(
    {
        "abstract_scope_slot_ordinal",
        "dependency_group_key",
        "delta_rule_ref",
        "event_intent_key",
        "event_profile_key",
        "fact_transition_rule",
        "path_transition_rule_key",
        "predecessor_event_intent_refs",
        "scenario_visibility_rule",
        "scope_relation_rule_key",
    }
)
RESERVED_SEMANTIC_ANCHOR_FIELDS = frozenset(
    {"family", "intent_key", "semantic_anchor_slot_ordinal", "variant_id"}
)

PERSONA_TOP_LEVEL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "canonical_limits",
        "completion_claims",
        "completion_scope",
        "dependency_direction_contract",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
        "input_binding_order",
        "input_bindings",
        "persona_id",
        "selection_policy",
        "orders",
        "primary_match_rows",
        "companion_match_rows",
        "reserved_semantic_anchor_rows",
        "use_case_family_witness_rows",
        "event_receipt",
        "remaining_blockers",
        "summary",
    }
)
SUITE_TOP_LEVEL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "canonical_limits",
        "completion_claims",
        "completion_scope",
        "dependency_direction_contract",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
        "input_binding_order",
        "input_bindings",
        "orders",
        "persona_bindings",
        "policy",
        "remaining_blockers",
        "summary",
    }
)
PROJECTION_TOP_LEVEL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "fixture_id",
        "fixture_schema_version",
        "persona_id",
        "content_rules",
        "content_sections",
        "summary",
    }
)

AUTHORITY_FIELDS = frozenset(
    {
        "actual_chunks_attested",
        "actual_lifecycle_receipts_attested",
        "authorizes_compiled_history_plan",
        "authorizes_evaluation_target_resolution",
        "authorizes_final_identifiers",
        "authorizes_g0_freeze",
        "authorizes_history_mutation",
        "authorizes_kio_execution",
        "authorizes_physical_write",
        "authorizes_query_rendering",
        "authorizes_renderer_execution",
        "authorizes_solver_execution",
        "authorizes_source_plan",
        "compiled_history_plan_available",
        "evaluation_target_mapping_available",
        "filesystem_writer_available",
        "formal_capacity_gate_satisfied",
        "history_executor_available",
        "kio_execution_available",
        "query_instances_rendered",
    }
)

EXPECTED_DEPENDENCY_PINS = {
    "persona-v2-lifecycle-coverage-catalog": (
        1_385_596,
        "1760eeed4bde8c7a1c2c720a437fb4c3d62971af3f2159e768696e938389b9d4",
    ),
    "persona-v2-primary-use-case-catalog": (
        30_008,
        "73939fc66fc234b5a8b3bfb8e6362b12807015204fd49253dde870a7f29528ed",
    ),
    "persona-v2-variant-catalog": (
        211_733,
        "807dd3cdd8df613ac21e6ba64877fb5abb40c72ed4949abaa0d440a449e7f9e9",
    ),
    "persona-v2-source-inventory-suite": (
        45_887,
        "9f216f3d986bdc92f7b07e0d2bfe266dc03df46d990f8ded706ad802d227edc3",
    ),
    "persona-v2-overlay-reservation-suite": (
        21_680,
        "11d042775faebf353a284aad18d137d2735bfd0e29b528666a19d14a008f2c3d",
    ),
    "persona-v2-source-semantic-membership-suite": (
        49_837,
        "62394dd2a3544f7d6c332652e6799b7a60353e8e3aa6a87f80e0ff21590a2e28",
    ),
    "persona-v2-source-inventory-profile-catalog": (
        87_391,
        "9b0de3defbc106f0bfa8b96ca2134886acd6766ac69196e3498b6b6f7edf43c0",
    ),
    "persona-v2-source-instance-parameter-assignment-suite": (
        72_535,
        "ed95d7875cb961d4fa054f6fa8a8a281cf6906724bc5f2524d9d046b2c3e8f1a",
    ),
}

FORBIDDEN_EXACT_KEYS = frozenset(
    {
        "absolute_path",
        "actual_qim",
        "assigned_bucket_key",
        "assigned_history_cohort_id",
        "assigned_scope_key",
        "chunk_id",
        "chunk_quota",
        "final_event_id",
        "final_materialization_id",
        "final_source_id",
        "materialization_id",
        "oracle_id",
        "oracle_key",
        "path",
        "query_id",
        "query_key",
        "query_text",
        "quota",
        "relative_path",
        "rendered_event_payload",
        "runtime_event_id",
        "scope_id",
        "solved_path",
        "solved_scope_key",
        "source_id",
    }
)

FAMILY_CLASS_COUNTS = {
    "pending-conversion-negative": 33,
    "raw-only-structural-negative": 8,
    "searchable-positive": 52,
}

SEARCHABLE_POSITIVE_FAMILIES = frozenset(
    {
        "md",
        "txt_log",
        "code",
        "structured_text",
        "csv_tsv",
        "html_eml",
        "ipynb",
        "pdf_text",
    }
)
PENDING_CONVERSION_FAMILIES = frozenset(
    {"pdf_scan", "docx", "xlsx", "pptx", "image"}
)
RAW_ONLY_FAMILIES = frozenset({"media", "domain_binary"})

SOURCE_EVENT_TYPE_COUNTS_PER_PERSONA = {
    "w1-incidental-typed-edit": 1,
    "w1-typed-edit": 69,
    "w2-move": 5,
    "w2-rename": 5,
    "w3-surface-edit": 54,
    "w4-archive": 10,
    "w4-create-x-prime": 20,
    "w4-delete": 20,
    "w5-create-p-prime": 15,
    "w5-delete-x-prime": 10,
    "w5-export-x": 10,
    "w5-purge-p": 15,
    "w5-restore-x": 10,
}

DERIVE_DIAGNOSTIC_PERSONAS = frozenset({"p01", "p04", "p06", "p09"})
DUPLICATE_DIAGNOSTIC_PERSONAS = frozenset(
    {"p04", "p05", "p08", "p10", "p14", "p19"}
)


class PersonaV2SourceMatchedLifecycleInventoryValidationError(ValueError):
    """Raised when independent source/lifecycle reconstruction rejects input."""


def _fail(message):
    raise PersonaV2SourceMatchedLifecycleInventoryValidationError(message)


def _ascii_key(value):
    if type(value) is not str:
        _fail("canonical ordering key must be an exact string")
    try:
        return value.encode("ascii", "strict")
    except UnicodeEncodeError:
        _fail("canonical ordering key must be ASCII")


def _require_persona_id(persona_id):
    if type(persona_id) is not str or persona_id not in PERSONA_IDS:
        _fail(f"unknown persona identity: {persona_id!r}")


def _canonical(value, *, label, maximum):
    try:
        return artifact_common.canonical_json_bytes(
            value, label=label, max_bytes=maximum
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _opening_snapshot(value, *, label, maximum):
    opening = _canonical(value, label=label, maximum=maximum)
    return json.loads(opening), opening


def _reject_forbidden_keys(value, *, path="$"):
    if type(value) is dict:
        for key, child in value.items():
            if type(key) is not str:
                _fail(f"non-string object key at {path}")
            if key in FORBIDDEN_EXACT_KEYS:
                _fail(f"forbidden solved/evaluation namespace at {path}.{key}")
            _reject_forbidden_keys(child, path=f"{path}.{key}")
    elif type(value) is list:
        for index, child in enumerate(value):
            _reject_forbidden_keys(child, path=f"{path}[{index}]")


def _strict_json_domain(value, *, path="$"):
    if value is None:
        _fail(f"null is forbidden at {path}")
    if type(value) is float:
        _fail(f"float is forbidden at {path}")
    if type(value) is int and value < 0:
        _fail(f"negative integer is forbidden at {path}")
    if type(value) is dict:
        for key, child in value.items():
            if type(key) is not str:
                _fail(f"non-string object key at {path}")
            if key.endswith(("_bytes", "_count", "_ordinal", "_version")):
                if type(child) is bool:
                    _fail(f"boolean aliases integer field at {path}.{key}")
            _strict_json_domain(child, path=f"{path}.{key}")
    elif type(value) is list:
        for index, child in enumerate(value):
            _strict_json_domain(child, path=f"{path}[{index}]")
    elif type(value) not in {dict, list, str, int, bool}:
        _fail(f"unsupported JSON-domain type at {path}")


def _require_all_false_authority(value, *, label, exact_fields=None):
    if type(value) is not dict or value.get("g0_contract_frozen") is not False:
        _fail(f"{label} must remain non-G0")
    authority = value.get("authority")
    if type(authority) is not dict or not authority:
        _fail(f"{label} authority must be a non-empty object")
    if exact_fields is not None and set(authority) != set(exact_fields):
        _fail(f"{label} authority schema drifted")
    if any(type(flag) is not bool or flag is not False for flag in authority.values()):
        _fail(f"{label} authority must be exact all-false booleans")


def _negative_authority():
    return {field: False for field in sorted(AUTHORITY_FIELDS)}


def _strict_equal(value, expected):
    if type(value) is not type(expected):
        return False
    if type(expected) is dict:
        return set(value) == set(expected) and all(
            _strict_equal(value[key], expected[key]) for key in expected
        )
    if type(expected) is list:
        return len(value) == len(expected) and all(
            _strict_equal(item, wanted)
            for item, wanted in zip(value, expected)
        )
    return value == expected


def _first_difference(value, expected, *, path="$"):
    """Return one deterministic, bounded path explaining strict inequality."""

    if type(value) is not type(expected):
        return f"{path} (type {type(value).__name__} != {type(expected).__name__})"
    if type(expected) is dict:
        value_keys = set(value)
        expected_keys = set(expected)
        if value_keys != expected_keys:
            missing = sorted(expected_keys - value_keys)
            extra = sorted(value_keys - expected_keys)
            return f"{path} (missing={missing[:1]!r}, extra={extra[:1]!r})"
        for key in sorted(expected, key=lambda item: item.encode("utf-8")):
            child = _first_difference(
                value[key], expected[key], path=f"{path}.{key}"
            )
            if child is not None:
                return child
        return None
    if type(expected) is list:
        if len(value) != len(expected):
            return f"{path} (length {len(value)} != {len(expected)})"
        for index, (item, wanted) in enumerate(zip(value, expected)):
            child = _first_difference(
                item, wanted, path=f"{path}[{index}]"
            )
            if child is not None:
                return child
        return None
    if value != expected:
        rendered_value = repr(value)
        rendered_expected = repr(expected)
        return (
            f"{path} ({rendered_value[:96]} != {rendered_expected[:96]})"
        )
    return None


def _dependency_specs():
    return (
        (
            "coverage",
            "persona-v2-lifecycle-coverage-catalog",
            lifecycle_coverage.build_lifecycle_coverage_catalog,
            lifecycle_coverage.validate_lifecycle_coverage_catalog,
            lifecycle_coverage.canonical_json_bytes,
        ),
        (
            "use_cases",
            "persona-v2-primary-use-case-catalog",
            use_case_catalog.build_primary_use_case_catalog,
            use_case_catalog.validate_primary_use_case_catalog,
            use_case_catalog.canonical_json_bytes,
        ),
        (
            "variants",
            "persona-v2-variant-catalog",
            variant_catalog.build_variant_catalog,
            variant_catalog.validate_variant_catalog,
            variant_catalog.canonical_json_bytes,
        ),
        (
            "source_suite",
            "persona-v2-source-inventory-suite",
            source_package.build_source_intent_suite_descriptor,
            source_package.validate_source_intent_suite_descriptor,
            source_package.canonical_json_bytes,
        ),
        (
            "reservation_suite",
            "persona-v2-overlay-reservation-suite",
            reservation_layout.build_overlay_reservation_suite,
            reservation_layout.validate_overlay_reservation_suite,
            reservation_layout.overlay_reservation_suite_bytes,
        ),
        (
            "semantic_suite",
            "persona-v2-source-semantic-membership-suite",
            source_semantic.build_source_semantic_membership_suite_descriptor,
            source_semantic.validate_source_semantic_membership_suite_descriptor,
            source_semantic.canonical_json_bytes,
        ),
        (
            "inventory_profiles",
            "persona-v2-source-inventory-profile-catalog",
            inventory_profile.build_source_inventory_profile_catalog,
            inventory_profile.validate_source_inventory_profile_catalog,
            inventory_profile.canonical_json_bytes,
        ),
    )


def _resolve_inputs(overrides):
    inputs = {}
    originals = {}
    canonicalizers = {}
    opening = {}
    for key, name, builder, validate, canonicalizer in _dependency_specs():
        supplied = overrides.get(key)
        original = builder() if supplied is None else supplied
        try:
            if validate is not None:
                validate(original)
            _require_all_false_authority(original, label=name)
            raw = canonicalizer(original)
        except Exception as error:
            if isinstance(
                error, PersonaV2SourceMatchedLifecycleInventoryValidationError
            ):
                raise
            raise PersonaV2SourceMatchedLifecycleInventoryValidationError(
                f"{name} failed upstream authentication"
            ) from error
        actual = (len(raw), hashlib.sha256(raw).hexdigest())
        if actual != EXPECTED_DEPENDENCY_PINS[name]:
            _fail(f"{name} differs from its frozen dependency pin")
        originals[key] = original
        canonicalizers[key] = canonicalizer
        opening[key] = bytes(raw)
        inputs[key] = copy.deepcopy(original)
    return originals, canonicalizers, opening, inputs


def _reauth_inputs(originals, canonicalizers, opening):
    for key in originals:
        try:
            current = canonicalizers[key](originals[key])
        except Exception as error:
            raise PersonaV2SourceMatchedLifecycleInventoryValidationError(
                "upstream artifact became invalid during validation"
            ) from error
        if not hmac.compare_digest(opening[key], current):
            _fail("upstream artifact mutated during callback execution")


def _dependency_binding(name, role, value, canonicalizer):
    raw = canonicalizer(value)
    expected = EXPECTED_DEPENDENCY_PINS[name]
    actual = (len(raw), hashlib.sha256(raw).hexdigest())
    if actual != expected:
        _fail(f"{name} dependency binding drifted")
    return {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": actual[0],
        "dependency_role": role,
        "fixture_id": value["fixture_id"],
        "fixture_schema_version": value["fixture_schema_version"],
        "name": name,
        "sha256": actual[1],
    }


def _parse_jsonl(body, *, label, maximum_row_bytes):
    if type(body) is not bytes or not body or not body.endswith(b"\n"):
        _fail(f"{label} must be non-empty exact LF-terminated bytes")
    rows = []
    for ordinal, line in enumerate(body.splitlines(keepends=True), start=1):
        if not line.endswith(b"\n") or len(line) > maximum_row_bytes:
            _fail(f"{label} row {ordinal} violates its LF-inclusive bound")
        payload = line[:-1]
        try:
            row = json.loads(payload.decode("utf-8", "strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PersonaV2SourceMatchedLifecycleInventoryValidationError(
                f"{label} row {ordinal} is not strict UTF-8 JSON"
            ) from error
        if type(row) is not dict:
            _fail(f"{label} row {ordinal} must be an object")
        canonical = _canonical(
            row,
            label=f"{label} row",
            maximum=maximum_row_bytes - 1,
        )
        if canonical != payload:
            _fail(f"{label} row {ordinal} is not canonical JSON")
        _strict_json_domain(row, path=f"${label}[{ordinal - 1}]")
        rows.append(row)
    return rows


def _authenticated_body(
    provider,
    coordinate,
    *,
    expected_bytes,
    expected_sha256,
    maximum_bytes,
    label,
    replay=False,
):
    if (
        type(maximum_bytes) is not int
        or type(maximum_bytes) is bool
        or maximum_bytes < 1
        or type(expected_bytes) is not int
        or type(expected_bytes) is bool
        or expected_bytes < 1
        or expected_bytes > maximum_bytes
        or type(expected_sha256) is not str
        or len(expected_sha256) != 64
        or any(
            character not in "0123456789abcdef"
            for character in expected_sha256
        )
    ):
        _fail(f"{label} has invalid authenticated receipt bounds")
    if not callable(provider):
        _fail(f"{label} provider must be callable")
    try:
        first = provider(*coordinate)
    except Exception as error:
        raise PersonaV2SourceMatchedLifecycleInventoryValidationError(
            f"{label} provider failed"
        ) from error
    if type(first) is not bytes:
        _fail(f"{label} provider must return exact bytes")
    if len(first) > maximum_bytes:
        _fail(f"{label} exceeds its pre-parse byte bound")
    if (
        len(first) != expected_bytes
        or hashlib.sha256(first).hexdigest() != expected_sha256
    ):
        _fail(f"{label} differs from its authenticated receipt")
    opening = bytes(first)
    if replay:
        try:
            second = provider(*coordinate)
        except Exception as error:
            raise PersonaV2SourceMatchedLifecycleInventoryValidationError(
                f"{label} replay failed"
            ) from error
        if type(second) is not bytes:
            _fail(f"{label} provider replay must return exact bytes")
        if len(second) > maximum_bytes:
            _fail(f"{label} replay exceeds its pre-compare byte bound")
        if len(second) != expected_bytes:
            _fail(f"{label} provider is nondeterministic or alias-mutated")
        if not hmac.compare_digest(opening, second):
            _fail(f"{label} provider is nondeterministic or alias-mutated")
    return opening


def _reservation_referenced_intents(reservation):
    referenced = set()
    for row in reservation["reservation_rows"]:
        if row["row_kind"] == "content-relation-reservation":
            referenced.update(
                (row["anchor_intent_key"], row["derivative_intent_key"])
            )
        elif row["row_kind"] == "attachment-membership-reservation":
            referenced.update(
                (row["host_intent_key"], row["standalone_member_intent_key"])
            )
        else:
            _fail("overlay reservation contains an unknown row kind")
    return referenced


def _default_assignment_origin_payload(persona_id):
    """Build manifest and expanded rows from one authenticated upstream state."""

    manifest, state = assignment._default_origin_build(  # noqa: SLF001
        persona_id, ORIGIN, return_state=True
    )
    rows = []
    for descriptor, source_rows in state["source_shards"]:
        for intent_key, _variant_id in source_rows:
            rows.append(
                {
                    "intent_key": intent_key,
                    "parameter_cell_key": state["assignments"][intent_key],
                    "shard_ordinal": descriptor["shard_ordinal"],
                }
            )
    return {"expanded_rows": rows, "manifest": manifest}


def _assignment_payload_fingerprint(payload):
    if type(payload) is not dict or set(payload) != {"expanded_rows", "manifest"}:
        _fail("assignment origin provider returned an unexpected schema")
    manifest_raw = assignment.canonical_json_bytes(payload["manifest"])
    rows_raw = _canonical(
        payload["expanded_rows"],
        label="assignment expanded origin rows",
        maximum=2 * 2**20,
    )
    return manifest_raw, rows_raw


def _load_pilot_records(
    inputs,
    persona_id,
    *,
    assignment_origin_provider=None,
):
    """Independently stream-join one persona's authenticated pilot sources."""

    _require_persona_id(persona_id)
    try:
        source_origin = source_package.build_source_intent_origin_manifest(
            persona_id, ORIGIN
        )
        source_package.validate_source_intent_origin_manifest(
            persona_id, ORIGIN, source_origin
        )
        reservation = reservation_layout.build_overlay_reservation_origin(
            persona_id, ORIGIN
        )
        reservation_layout.validate_overlay_reservation_origin(
            persona_id, ORIGIN, reservation
        )
        semantic_origin = (
            source_semantic.build_source_semantic_membership_origin_manifest(
                persona_id, ORIGIN
            )
        )
        source_semantic.validate_source_semantic_membership_origin_manifest(
            persona_id, ORIGIN, semantic_origin
        )
    except Exception as error:
        raise PersonaV2SourceMatchedLifecycleInventoryValidationError(
            f"{persona_id} pilot upstream origin failed authentication"
        ) from error

    provider = (
        _default_assignment_origin_payload
        if assignment_origin_provider is None
        else assignment_origin_provider
    )
    if not callable(provider):
        _fail("assignment origin provider must be callable")
    try:
        assignment_payload = copy.deepcopy(provider(persona_id))
        assignment_opening = _assignment_payload_fingerprint(assignment_payload)
        assignment_origin = assignment_payload["manifest"]
        assignment.validate_source_parameter_assignment_origin_manifest(
            persona_id, ORIGIN, assignment_origin
        )
        expanded_assignment_rows = assignment_payload["expanded_rows"]
        if type(expanded_assignment_rows) is not list or any(
            type(row) is not dict
            or set(row)
            != {"intent_key", "parameter_cell_key", "shard_ordinal"}
            for row in expanded_assignment_rows
        ):
            _fail("assignment expanded rows have an unexpected schema")
    except Exception as error:
        raise PersonaV2SourceMatchedLifecycleInventoryValidationError(
            f"{persona_id} pilot assignment origin failed authentication"
        ) from error

    profile_rows = inputs["inventory_profiles"]["source_profile_rows"]
    profile_by_id = {row["source_profile_id"]: row for row in profile_rows}
    if len(profile_by_id) != 71:
        _fail("inventory profile identity mapping drifted")
    variant_by_id = {
        row["variant_id"]: row for row in inputs["variants"]["variant_rows"]
    }
    if len(variant_by_id) != 71:
        _fail("variant identity mapping drifted")

    try:
        semantic_compact = _authenticated_body(
            source_semantic.source_semantic_membership_origin_body_bytes,
            (persona_id, ORIGIN),
            expected_bytes=semantic_origin["body_descriptor"]["body_bytes"],
            expected_sha256=semantic_origin["body_descriptor"]["body_sha256"],
            maximum_bytes=source_semantic.MAX_ORIGIN_BODY_BYTES,
            label="source semantic compact origin body",
        )
        compact_rows = _parse_jsonl(
            semantic_compact,
            label="source semantic compact origin body",
            maximum_row_bytes=source_semantic.MAX_COMPACT_ROW_BYTES_INCLUDING_LF,
        )
    except AttributeError as error:
        raise PersonaV2SourceMatchedLifecycleInventoryValidationError(
            "source semantic public bounds are unavailable"
        ) from error
    semantic_receipts = {
        row["source_shard_id"]: row
        for row in compact_rows
        if row.get("row_kind") == "source-shard-total-projection"
    }
    if len(semantic_receipts) != len(source_origin["shard_descriptors"]):
        _fail("semantic range receipts do not cover the pilot source shards")
    assignment_receipts = {
        row["source_shard_id"]: row
        for row in assignment_origin["expanded_view_receipts"]
    }
    if len(assignment_receipts) != len(source_origin["shard_descriptors"]):
        _fail("assignment receipts do not cover the pilot source shards")
    assignment_rows_by_shard = defaultdict(list)
    for row in expanded_assignment_rows:
        assignment_rows_by_shard[row["shard_ordinal"]].append(row)
    if set(assignment_rows_by_shard) != {
        row["shard_ordinal"] for row in source_origin["shard_descriptors"]
    }:
        _fail("assignment expanded rows do not cover exact source shards")

    records = []
    seen = set()
    for descriptor in source_origin["shard_descriptors"]:
        shard_ordinal = descriptor["shard_ordinal"]
        shard_id = descriptor["shard_id"]
        semantic_receipt = semantic_receipts.get(shard_id)
        assignment_receipt = assignment_receipts.get(shard_id)
        if semantic_receipt is None or assignment_receipt is None:
            _fail("pilot source shard lacks a semantic or assignment receipt")

        source_body = _authenticated_body(
            source_package.source_intent_shard_body_bytes,
            (persona_id, ORIGIN, shard_ordinal),
            expected_bytes=descriptor["body_bytes"],
            expected_sha256=descriptor["body_sha256"],
            maximum_bytes=source_package.MAX_SHARD_BODY_BYTES,
            label="source inventory shard body",
        )
        context_body = _authenticated_body(
            source_semantic.expanded_content_context_shard_body_bytes,
            (persona_id, ORIGIN, shard_ordinal),
            expected_bytes=semantic_receipt[
                "expanded_content_context_body_bytes"
            ],
            expected_sha256=semantic_receipt[
                "expanded_content_context_sha256"
            ],
            maximum_bytes=source_semantic.MAX_EXPANDED_SHARD_BODY_BYTES,
            label="expanded content-context shard body",
        )
        membership_body = _authenticated_body(
            source_semantic.expanded_fact_membership_shard_body_bytes,
            (persona_id, ORIGIN, shard_ordinal),
            expected_bytes=semantic_receipt[
                "expanded_fact_membership_body_bytes"
            ],
            expected_sha256=semantic_receipt[
                "expanded_fact_membership_sha256"
            ],
            maximum_bytes=source_semantic.MAX_EXPANDED_SHARD_BODY_BYTES,
            label="expanded fact-membership shard body",
        )
        expanded_rows = assignment_rows_by_shard[shard_ordinal]
        assignment_parts = [
            _canonical(
                {
                    "intent_key": row["intent_key"],
                    "parameter_cell_key": row["parameter_cell_key"],
                },
                label="expanded parameter-assignment row",
                maximum=assignment.MAX_EXPANDED_ROW_BYTES_INCLUDING_LF - 1,
            )
            + b"\n"
            for row in expanded_rows
        ]
        assignment_body = b"".join(assignment_parts)
        if (
            len(assignment_body) != assignment_receipt["expanded_body_bytes"]
            or hashlib.sha256(assignment_body).hexdigest()
            != assignment_receipt["expanded_body_sha256"]
            or max(map(len, assignment_parts))
            != assignment_receipt["maximum_row_bytes_including_lf"]
        ):
            _fail("expanded assignment rows differ from authenticated receipt")

        source_rows = _parse_jsonl(
            source_body,
            label="source inventory shard body",
            maximum_row_bytes=source_package.MAX_INTENT_ROW_BYTES_INCLUDING_LF,
        )
        context_rows = _parse_jsonl(
            context_body,
            label="expanded content-context shard body",
            maximum_row_bytes=(
                source_semantic.MAX_EXPANDED_CONTEXT_ROW_BYTES_INCLUDING_LF
            ),
        )
        membership_rows = _parse_jsonl(
            membership_body,
            label="expanded fact-membership shard body",
            maximum_row_bytes=(
                source_semantic.MAX_EXPANDED_MEMBERSHIP_ROW_BYTES_INCLUDING_LF
            ),
        )
        assignment_rows = expanded_rows
        if not (
            len(source_rows)
            == len(context_rows)
            == len(membership_rows)
            == len(assignment_rows)
            == descriptor["row_count"]
            == semantic_receipt["row_count"]
            == assignment_receipt["row_count"]
        ):
            _fail("pilot source/semantic/assignment shard row counts diverged")

        for source_row, context, membership, assigned in zip(
            source_rows, context_rows, membership_rows, assignment_rows
        ):
            intent_key = source_row.get("intent_key")
            if (
                intent_key in seen
                or context.get("intent_key") != intent_key
                or membership.get("intent_key") != intent_key
                or assigned.get("intent_key") != intent_key
                or source_row.get("persona_id") != persona_id
                or source_row.get("origin") != ORIGIN
                or context.get("persona_id") != persona_id
                or context.get("origin") != ORIGIN
                or membership.get("persona_id") != persona_id
                or membership.get("origin") != ORIGIN
            ):
                _fail("pilot source join identity drifted")
            seen.add(intent_key)
            profile = profile_by_id.get(source_row["source_profile_id"])
            if profile is None:
                _fail("pilot source references an unknown inventory profile")
            variant = variant_by_id.get(profile["variant_id"])
            if (
                variant is None
                or variant["family"] != profile["family"]
                or variant["gate_role"] != profile["gate_role"]
                or variant["expected_offline_disposition"]
                != profile["expected_offline_disposition"]
            ):
                _fail("inventory profile/variant metadata join drifted")
            records.append(
                {
                    "base_fact_profile_id": membership["fact_profile_id"],
                    "base_language": context["language"],
                    "base_logical_document_key": membership[
                        "logical_document_key"
                    ],
                    "base_logical_revision_key": membership[
                        "logical_revision_key"
                    ],
                    "base_topic_id": context["topic_id"],
                    "family": profile["family"],
                    "gate_role": profile["gate_role"],
                    "intent_key": intent_key,
                    "offline_disposition": profile[
                        "expected_offline_disposition"
                    ],
                    "origin": ORIGIN,
                    "parameter_cell_key": assigned["parameter_cell_key"],
                    "source_profile_id": profile["source_profile_id"],
                    "variant_id": profile["variant_id"],
                }
            )

    if len(records) != source_origin["summary"]["source_intent_count"]:
        _fail("pilot joined record count differs from source origin")

    anchors = {
        row["intent_key"]: row["semantic_anchor_slot_ordinal"]
        for row in reservation["semantic_anchor_slots"]
    }
    if len(anchors) != 105:
        _fail("pilot semantic anchor count must be exact 105")
    reserved = _reservation_referenced_intents(reservation) | set(anchors)
    by_key = {row["intent_key"]: row for row in records}
    if len(by_key) != len(records) or not reserved <= set(by_key):
        _fail("pilot reservation references unknown or duplicate source intents")

    try:
        replay = provider(persona_id)
        replay_fingerprint = _assignment_payload_fingerprint(replay)
        replay_manifest = replay["manifest"]
        assignment.validate_source_parameter_assignment_origin_manifest(
            persona_id, ORIGIN, replay_manifest
        )
    except Exception as error:
        raise PersonaV2SourceMatchedLifecycleInventoryValidationError(
            "assignment origin provider failed postflight authentication"
        ) from error
    if any(
        not hmac.compare_digest(before, after)
        for before, after in zip(assignment_opening, replay_fingerprint)
    ):
        _fail("assignment origin provider changed during source reconstruction")

    cell_catalog = assignment.build_source_parameter_cell_catalog()
    cell_by_key = {
        row["parameter_cell_key"]: row for row in cell_catalog["parameter_cells"]
    }
    if len(cell_by_key) != 363 or any(
        row["parameter_cell_key"] not in cell_by_key
        or cell_by_key[row["parameter_cell_key"]]["variant_id"]
        != row["variant_id"]
        for row in records
    ):
        _fail("pilot assignment references an unknown parameter cell")
    return {
        "anchors": anchors,
        "assignment_origin": assignment_origin,
        "by_key": by_key,
        "cell_catalog": cell_catalog,
        "cell_by_key": cell_by_key,
        "records": records,
        "reservation": reservation,
        "reserved": reserved,
        "semantic_origin": semantic_origin,
        "source_origin": source_origin,
    }


def _bound_artifact(name, role, value, canonicalizer, *, coordinates=()):
    raw = canonicalizer(value)
    result = {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "dependency_role": role,
        "name": name,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    for field in coordinates:
        result[field] = value[field]
    return result


def _global_bindings(inputs, joined):
    return [
        _bound_artifact(
            "persona-v2-lifecycle-coverage-catalog",
            "anonymous-capability-event-algebra-and-receipt-demand-owner",
            inputs["coverage"],
            lifecycle_coverage.canonical_json_bytes,
        ),
        _bound_artifact(
            "persona-v2-primary-use-case-catalog",
            "persona-required-family-and-scenario-owner",
            inputs["use_cases"],
            use_case_catalog.canonical_json_bytes,
        ),
        _bound_artifact(
            "persona-v2-variant-catalog",
            "family-gate-role-and-offline-disposition-owner",
            inputs["variants"],
            variant_catalog.canonical_json_bytes,
        ),
        _bound_artifact(
            "persona-v2-source-inventory-profile-catalog",
            "source-profile-to-variant-family-and-gate-role-owner",
            inputs["inventory_profiles"],
            inventory_profile.canonical_json_bytes,
        ),
        _bound_artifact(
            "persona-v2-source-parameter-cell-catalog",
            "selected-source-parameter-cell-and-target-byte-owner",
            joined["cell_catalog"],
            assignment.canonical_json_bytes,
        ),
        {
            "artifact_kind": assignment.SUITE_KIND,
            "artifact_schema": assignment.SUITE_SCHEMA,
            "artifact_schema_version": assignment.ARTIFACT_SCHEMA_VERSION,
            "canonical_bytes": EXPECTED_DEPENDENCY_PINS[
                "persona-v2-source-instance-parameter-assignment-suite"
            ][0],
            "dependency_role": "frozen-all-source-parameter-assignment-suite-pin",
            "name": "persona-v2-source-instance-parameter-assignment-suite",
            "sha256": EXPECTED_DEPENDENCY_PINS[
                "persona-v2-source-instance-parameter-assignment-suite"
            ][1],
        },
    ]


def _persona_origin_bindings(joined):
    return [
        _bound_artifact(
            "persona-v2-source-inventory-origin-manifest",
            "authenticated-pilot-source-intent-owner",
            joined["source_origin"],
            source_package.canonical_json_bytes,
            coordinates=("persona_id", "origin"),
        ),
        _bound_artifact(
            "persona-v2-overlay-reservation-origin",
            "semantic-anchor-and-overlay-unreserved-domain-owner",
            joined["reservation"],
            reservation_layout.canonical_json_bytes,
            coordinates=("persona_id", "origin"),
        ),
        _bound_artifact(
            "persona-v2-source-semantic-membership-origin-manifest",
            "base-topic-language-fact-and-logical-identity-owner",
            joined["semantic_origin"],
            source_semantic.canonical_json_bytes,
            coordinates=("persona_id", "origin"),
        ),
        _bound_artifact(
            "persona-v2-source-instance-parameter-assignment-origin-manifest",
            "authenticated-pilot-intent-to-parameter-cell-owner",
            joined["assignment_origin"],
            assignment.canonical_json_bytes,
            coordinates=("persona_id", "origin"),
        ),
    ]


def _domain_key(domain, intent_key):
    raw = (
        b"kio-lifecycle-v1/"
        + _ascii_key(domain)
        + b"/"
        + _ascii_key(intent_key)
    )
    return hashlib.sha256(raw).digest(), _ascii_key(intent_key)


def _cross_pairs(anchor_records, candidate_records):
    """Return the first ten successes of an independent ordered DFS matching."""

    left = sorted(
        anchor_records,
        key=lambda row: _domain_key("cross-anchor", row["intent_key"]),
    )
    right = sorted(
        candidate_records,
        key=lambda row: _domain_key("cross-candidate", row["intent_key"]),
    )
    right_by_key = {row["intent_key"]: row for row in right}
    right_match = {}

    def visit(left_row, seen):
        for right_row in right:
            right_key = right_row["intent_key"]
            if right_key in seen:
                continue
            if (
                left_row["base_topic_id"] != right_row["base_topic_id"]
                or left_row["base_language"] != right_row["base_language"]
                or left_row["family"] == right_row["family"]
            ):
                continue
            seen.add(right_key)
            prior = right_match.get(right_key)
            if prior is None or visit(prior, seen):
                right_match[right_key] = left_row
                return True
        return False

    success_count = 0
    for left_row in left:
        if visit(left_row, set()):
            success_count += 1
            if success_count == 10:
                break
    if success_count != 10 or len(right_match) != 10:
        _fail("deterministic cross-format matching did not close at ten pairs")
    pair_by_left = {
        row["intent_key"]: right_by_key[right_key]
        for right_key, row in right_match.items()
    }
    return [
        (row, pair_by_left[row["intent_key"]])
        for row in sorted(
            right_match.values(),
            key=lambda item: _domain_key("cross-anchor", item["intent_key"]),
        )
    ]


def _family_classification(family):
    if family in SEARCHABLE_POSITIVE_FAMILIES:
        return "searchable-positive"
    if family in PENDING_CONVERSION_FAMILIES:
        return "pending-conversion-negative"
    if family in RAW_ONLY_FAMILIES:
        return "raw-only-structural-negative"
    _fail(f"required use-case family has no disposition class: {family}")


def _reconstruct_selection(inputs, persona_id, joined):
    records = joined["records"]
    by_key = joined["by_key"]
    anchors = joined["anchors"]
    reserved = joined["reserved"]
    cell_by_key = joined["cell_by_key"]

    persona_capabilities = sorted(
        (
            row
            for row in inputs["coverage"]["primary_capabilities"]
            if row["persona_id"] == persona_id
        ),
        key=lambda row: _ascii_key(row["capability_key"]),
    )
    companion_requirements = sorted(
        (
            row
            for row in inputs["coverage"][
                "cross_format_companion_requirements"
            ]
            if row["persona_id"] == persona_id
        ),
        key=lambda row: _ascii_key(row["primary_capability_key"]),
    )
    if len(persona_capabilities) != 105 or len(companion_requirements) != 10:
        _fail("persona lifecycle coverage cardinality drifted")

    anchor_records = [by_key[key] for key in anchors]
    overlay_unreserved = [
        row for row in records if row["intent_key"] not in reserved
    ]
    companion_candidates = [
        row
        for row in overlay_unreserved
        if row["gate_role"] == "contract_contributor"
    ]
    pairs = _cross_pairs(anchor_records, companion_candidates)
    cross_capabilities = [
        row for row in persona_capabilities if row["cross_format_companion_required"]
    ]
    if [row["primary_capability_key"] for row in companion_requirements] != [
        row["capability_key"] for row in cross_capabilities
    ]:
        _fail("cross-format primary and companion requirement order diverged")

    primary_record_by_capability = {}
    companion_record_by_capability = {}
    for capability, (primary_record, companion_record) in zip(
        cross_capabilities, pairs
    ):
        primary_record_by_capability[capability["capability_key"]] = primary_record
        companion_record_by_capability[capability["capability_key"]] = (
            companion_record
        )

    used_anchor_keys = {
        row["intent_key"] for row in primary_record_by_capability.values()
    }
    remaining_anchors = sorted(
        (
            row
            for row in anchor_records
            if row["intent_key"] not in used_anchor_keys
        ),
        key=lambda row: _domain_key("primary-anchor", row["intent_key"]),
    )
    remaining_contributor_capabilities = [
        row
        for row in persona_capabilities
        if row["allocation_class"] != "I"
        and row["capability_key"] not in primary_record_by_capability
    ]
    if len(remaining_contributor_capabilities) != 90:
        _fail("non-cross contributor capability count must be exact ninety")
    for capability, record in zip(
        remaining_contributor_capabilities, remaining_anchors[:90]
    ):
        primary_record_by_capability[capability["capability_key"]] = record
    used_anchor_keys.update(row["intent_key"] for row in remaining_anchors[:90])
    reserved_unused_anchor_keys = set(anchors) - used_anchor_keys
    if len(used_anchor_keys) != 100 or len(reserved_unused_anchor_keys) != 5:
        _fail("semantic anchor consumption/reserve split must be exact 100/5")

    selected_contributor_families = {
        row["family"] for row in primary_record_by_capability.values()
    }
    use_case_matches = [
        row
        for row in inputs["use_cases"]["primary_use_cases"]
        if row["persona_id"] == persona_id
    ]
    if len(use_case_matches) != 1:
        _fail("persona must own exactly one primary use case")
    use_case = use_case_matches[0]
    missing_required_families = [
        family
        for family in use_case["required_families"]
        if family in SEARCHABLE_POSITIVE_FAMILIES
        and family not in selected_contributor_families
    ]

    already_selected = {
        row["intent_key"] for row in primary_record_by_capability.values()
    } | {
        row["intent_key"] for row in companion_record_by_capability.values()
    }
    incidental_pool = [
        row
        for row in overlay_unreserved
        if row["gate_role"] == "incidental_searchable"
        and row["intent_key"] not in already_selected
        and cell_by_key[row["parameter_cell_key"]]["target_bytes"] <= 32_768
    ]
    incidental_selection = []
    incidental_keys = set()
    for family in missing_required_families:
        candidates = sorted(
            (
                row
                for row in incidental_pool
                if row["family"] == family
                and row["intent_key"] not in incidental_keys
            ),
            key=lambda row: _domain_key(
                "incidental-required", row["intent_key"]
            ),
        )
        if not candidates:
            _fail(f"required incidental family cannot be covered: {family}")
        incidental_selection.append(candidates[0])
        incidental_keys.add(candidates[0]["intent_key"])
    fill = sorted(
        (
            row
            for row in incidental_pool
            if row["intent_key"] not in incidental_keys
        ),
        key=lambda row: _domain_key("incidental-fill", row["intent_key"]),
    )
    incidental_selection.extend(fill[: 5 - len(incidental_selection)])
    if len(incidental_selection) != 5 or len(
        {row["intent_key"] for row in incidental_selection}
    ) != 5:
        _fail("incidental primary selection must contain five distinct sources")
    incidental_capabilities = [
        row for row in persona_capabilities if row["allocation_class"] == "I"
    ]
    for capability, record in zip(
        incidental_capabilities, incidental_selection
    ):
        primary_record_by_capability[capability["capability_key"]] = record

    if len(primary_record_by_capability) != 105:
        _fail("primary source matching did not cover all 105 capabilities")
    lifecycle_intent_keys = {
        row["intent_key"] for row in primary_record_by_capability.values()
    } | {
        row["intent_key"] for row in companion_record_by_capability.values()
    }
    if len(lifecycle_intent_keys) != 115:
        _fail("lifecycle source references must be 115 distinct pilot intents")

    return {
        "companion_record_by_capability": companion_record_by_capability,
        "companion_requirements": companion_requirements,
        "lifecycle_intent_keys": lifecycle_intent_keys,
        "overlay_unreserved": overlay_unreserved,
        "primary_record_by_capability": primary_record_by_capability,
        "reserved_unused_anchor_keys": reserved_unused_anchor_keys,
        "use_case": use_case,
    }


def _base_match_fields(record):
    return {
        "base_fact_profile_id": record["base_fact_profile_id"],
        "base_language": record["base_language"],
        "base_logical_document_key": record["base_logical_document_key"],
        "base_logical_revision_key": record["base_logical_revision_key"],
        "base_topic_id": record["base_topic_id"],
        "family": record["family"],
        "gate_role": record["gate_role"],
        "intent_key": record["intent_key"],
        "origin": ORIGIN,
        "parameter_cell_key": record["parameter_cell_key"],
        "source_profile_id": record["source_profile_id"],
        "variant_id": record["variant_id"],
    }


def _build_match_rows(inputs, persona_id, joined, selection):
    capability_by_key = {
        row["capability_key"]: row
        for row in inputs["coverage"]["primary_capabilities"]
        if row["persona_id"] == persona_id
    }
    requirement_by_primary = {
        row["primary_capability_key"]: row
        for row in selection["companion_requirements"]
    }
    primary_rows = []
    for capability_key in sorted(capability_by_key, key=_ascii_key):
        capability = capability_by_key[capability_key]
        record = selection["primary_record_by_capability"][capability_key]
        row = {
            **_base_match_fields(record),
            "allocation_class": capability["allocation_class"],
            "capability_class_key": capability["capability_class_key"],
            "capability_key": capability_key,
            "lifecycle_logical_document_slot_key": capability[
                "logical_document_slot_key"
            ],
            "reservation_status": (
                "selected-pilot-overlay-unreserved-incidental"
                if capability["allocation_class"] == "I"
                else "selected-pilot-semantic-anchor"
            ),
        }
        if capability["allocation_class"] == "I":
            expected_fields = INCIDENTAL_PRIMARY_MATCH_FIELDS
        else:
            row["semantic_anchor_slot_ordinal"] = joined["anchors"][
                record["intent_key"]
            ]
            expected_fields = CONTRIBUTOR_PRIMARY_MATCH_FIELDS
        if set(row) != expected_fields:
            _fail("independent primary match row schema drifted")
        primary_rows.append(row)

    companion_rows = []
    for primary_key in sorted(
        selection["companion_record_by_capability"], key=_ascii_key
    ):
        requirement = requirement_by_primary[primary_key]
        record = selection["companion_record_by_capability"][primary_key]
        row = {
            **_base_match_fields(record),
            "companion_requirement_key": requirement[
                "companion_requirement_key"
            ],
            "effective_membership_rule": (
                "replace-with-primary-lifecycle-logical-document-fact-revision-chain"
            ),
            "primary_capability_key": primary_key,
            "rendition_group_key": requirement["rendition_group_key"],
            "reservation_status": (
                "selected-pilot-overlay-unreserved-companion"
            ),
        }
        if set(row) != COMPANION_MATCH_FIELDS:
            _fail("independent companion match row schema drifted")
        primary = next(
            item for item in primary_rows if item["capability_key"] == primary_key
        )
        if (
            row["base_topic_id"] != primary["base_topic_id"]
            or row["base_language"] != primary["base_language"]
            or row["family"] == primary["family"]
            or row["intent_key"] == primary["intent_key"]
        ):
            _fail("cross-format companion semantics or distinctness drifted")
        companion_rows.append(row)
    if len(primary_rows) != 105 or len(companion_rows) != 10:
        _fail("independent match row cardinality drifted")
    return primary_rows, companion_rows


def _negative_witness_candidate(family, candidates):
    classification = _family_classification(family)
    if classification == "pending-conversion-negative":
        candidates = [
            row
            for row in candidates
            if row["offline_disposition"] in {"awaiting_ocr", "await_conversion"}
        ]
    elif classification == "raw-only-structural-negative":
        candidates = [
            row
            for row in candidates
            if row["offline_disposition"] == "unsupported_binary"
        ]
    else:
        _fail("negative witness candidate requested for a searchable family")
    candidates.sort(
        key=lambda row: (
            int(row["variant_id"] not in {"jpg", "png"})
            if family == "image"
            else 0,
            *_domain_key("format-witness", row["intent_key"]),
        )
    )
    if not candidates:
        _fail(f"no overlay-unreserved physical witness for {family}")
    return candidates[0]


def _build_format_witness_rows(persona_id, selection, primary_rows, joined):
    use_case = selection["use_case"]
    by_family = defaultdict(list)
    for row in primary_rows:
        by_family[row["family"]].append(row)
    for rows in by_family.values():
        rows.sort(key=lambda row: _ascii_key(row["capability_key"]))
    negative_pool = [
        row
        for row in selection["overlay_unreserved"]
        if row["intent_key"] not in selection["lifecycle_intent_keys"]
        and row["gate_role"] == "raw_only"
    ]
    witness_rows = []
    witness_intents = set()
    for family in use_case["required_families"]:
        classification = _family_classification(family)
        if classification == "searchable-positive":
            candidates = by_family.get(family, [])
            if not candidates:
                _fail(
                    f"{persona_id}/{family} lacks a matched primary query anchor"
                )
            anchor = candidates[0]
            row = {
                "classification": classification,
                "family": family,
                "intent_key": anchor["intent_key"],
                "offline_disposition": joined["by_key"][anchor["intent_key"]][
                    "offline_disposition"
                ],
                "parameter_cell_key": anchor["parameter_cell_key"],
                "physical_witness_required": True,
                "primary_use_case_id": use_case["primary_use_case_id"],
                "query_answer_anchor_required": True,
                "query_anchor_ref": anchor["intent_key"],
                "source_profile_id": anchor["source_profile_id"],
                "source_selection_kind": "matched-lifecycle-primary",
                "variant_id": anchor["variant_id"],
            }
            if set(row) != POSITIVE_FORMAT_WITNESS_FIELDS:
                _fail("positive format witness schema drifted")
        else:
            candidates = [
                item for item in negative_pool if item["family"] == family
            ]
            selected = _negative_witness_candidate(family, candidates)
            row = {
                "classification": classification,
                "family": family,
                "intent_key": selected["intent_key"],
                "negative_expectation": selected["offline_disposition"],
                "offline_disposition": selected["offline_disposition"],
                "parameter_cell_key": selected["parameter_cell_key"],
                "physical_witness_required": True,
                "primary_use_case_id": use_case["primary_use_case_id"],
                "query_answer_anchor_required": False,
                "source_profile_id": selected["source_profile_id"],
                "source_selection_kind": (
                    "extra-overlay-unreserved-pilot-witness"
                ),
                "variant_id": selected["variant_id"],
            }
            if set(row) != NEGATIVE_FORMAT_WITNESS_FIELDS:
                _fail("negative format witness schema drifted")
        if row["intent_key"] in witness_intents and classification != "searchable-positive":
            _fail("negative physical witness intent was reused")
        witness_intents.add(row["intent_key"])
        witness_rows.append(row)
    return witness_rows


def _build_reserved_anchor_rows(joined, selection):
    rows = []
    for intent_key in sorted(
        selection["reserved_unused_anchor_keys"],
        key=lambda key: joined["anchors"][key],
    ):
        record = joined["by_key"][intent_key]
        row = {
            "family": record["family"],
            "intent_key": intent_key,
            "semantic_anchor_slot_ordinal": joined["anchors"][intent_key],
            "variant_id": record["variant_id"],
        }
        if set(row) != RESERVED_SEMANTIC_ANCHOR_FIELDS:
            _fail("reserved semantic anchor row schema drifted")
        rows.append(row)
    if len(rows) != 5:
        _fail("reserved semantic anchor row count must be exact five")
    return rows


def _event_subject_rule(operation_key, *, companion=False, diagnostic=False):
    if companion:
        return "subject/companion"
    if diagnostic:
        return "subject/diag"
    if operation_key in {"w4-create-x-prime", "w5-delete-x-prime"}:
        return "subject/x-prime"
    if operation_key == "w5-create-p-prime":
        return "subject/p+"
    if operation_key == "w5-forced-purged-commit":
        return "subject/p-purged"
    return "subject/w0-source"


def _event_transition_rules(operation_key):
    if operation_key in {
        "w1-typed-edit",
        "w1-incidental-typed-edit",
        "w3-surface-edit",
    }:
        return (
            "state/live",
            "state/live-plus-history",
            "bytes/new-disjoint",
            "facts/typed-revision"
            if operation_key != "w3-surface-edit"
            else "facts/carry-forward",
        )
    if operation_key in {"w2-rename", "w2-move", "w4-archive"}:
        return (
            "state/live-before-path",
            "state/live-after-path",
            "bytes/preserved",
            "facts/preserved",
        )
    if operation_key == "w3-derive-diagnostic":
        return (
            "state/diag-absent",
            "state/derived-live",
            "bytes/new-derived",
            "facts/derived-nondenom",
        )
    if operation_key.startswith("w3-duplicate-diagnostic"):
        return (
            "state/diag-absent",
            "state/duplicate-live",
            "bytes/reused",
            "facts/preserved-nondenom",
        )
    mapping = {
        "w4-delete": (
            "state/live",
            "state/deleted-history",
            "bytes/history-retained",
            "facts/history-only",
        ),
        "w4-create-x-prime": (
            "state/repl-absent",
            "state/repl-live",
            "bytes/new-distinct",
            "facts/repl-distinct",
        ),
        "w5-create-p-prime": (
            "state/repl-absent",
            "state/repl-live",
            "bytes/new-distinct",
            "facts/repl-distinct",
        ),
        "w5-export-x": (
            "state/deleted-history",
            "state/export-nonindexed",
            "bytes/exact-export",
            "facts/no-change",
        ),
        "w5-restore-x": (
            "state/deleted-history",
            "state/restored-live",
            "bytes/cas-reuse",
            "facts/restored-current-history",
        ),
        "w5-delete-x-prime": (
            "state/x-prime-live",
            "state/x-prime-deleted",
            "bytes/x-prime-history",
            "facts/x-prime-history-only",
        ),
        "w5-purge-p": (
            "state/p-live-plus-history",
            "state/p-purged",
            "bytes/two-p-versions-purged",
            "facts/p-witness-unreachable",
        ),
        "w5-forced-purged-commit": (
            "state/p-purged",
            "state/p-purge-committed",
            "bytes/no-change",
            "facts/purge-committed",
        ),
    }
    if operation_key not in mapping:
        _fail(f"event operation has no transition rules: {operation_key}")
    return mapping[operation_key]


def _event_visibility_rule(operation_key, capability_class_key):
    if operation_key.startswith("w3-derive") or operation_key.startswith(
        "w3-duplicate"
    ):
        return "vis/diagnostic-nondenom"
    if operation_key == "w4-delete":
        return "visibility/original-history-only"
    if operation_key == "w5-restore-x":
        return "visibility/original-restored"
    if operation_key in {"w4-create-x-prime", "w5-create-p-prime"}:
        return "vis/repl-nonanchor"
    if operation_key in {"w5-purge-p", "w5-forced-purged-commit"}:
        return "visibility/p-purged"
    if "history" in capability_class_key:
        return "visibility/history-scenario"
    return "visibility/current-transition-scenario"


def _event_anchor_rule(operation_key):
    mapping = {
        "w4-create-x-prime": "anchor/x-prime-new",
        "w5-delete-x-prime": "anchor/x-prime-existing",
        "w5-create-p-prime": "anchor/p+-new",
        "w5-export-x": "anchor/x-export",
        "w5-restore-x": "anchor/x-plus-export",
    }
    if operation_key in mapping:
        return mapping[operation_key]
    if operation_key in {"w5-purge-p", "w5-forced-purged-commit"}:
        return "anchor/p-purge-witness"
    if operation_key.startswith("w3-") and "diagnostic" in operation_key:
        return "anchor/stable-diagnostic"
    return "anchor/w0-capability"


def _symbol_domain_ref(operation, symbol_order):
    used = {
        term["symbol"]
        for term in operation["delta_terms"]
        if term["symbol"] != "zero"
    }
    if not used:
        return "symbols:none"
    return "symbols:" + ",".join(symbol for symbol in symbol_order if symbol in used)


def _expected_source_event_row(spec, ordinal, persona_id, operation, symbol_order):
    match = spec["match"]
    operation_key = spec["operation_key"]
    _before, _after, byte_rule, fact_rule = _event_transition_rules(operation_key)
    row = {
        "after_source_intent_key": spec["after_source_intent_key"],
        "byte_transition_rule": byte_rule,
        "capability_key": match["capability_key"],
        "dependency_group_key": spec["dependency_group_key"],
        "delta_rule_ref": f"operation-algebra/{operation_key}",
        "event_intent_key": f"{persona_id}-lifecycle-event-intent-{ordinal:04d}",
        "event_profile_key": operation_key,
        "event_sequence_ordinal": ordinal,
        "fact_transition_rule": fact_rule,
        "family": match["family"],
        "gate_role": match["gate_role"],
        "path_transition_rule_key": operation["path_transition_rule_key"],
        "persona_id": persona_id,
        "predecessor_event_intent_refs": spec[
            "predecessor_event_intent_refs"
        ],
        "row_kind": "source",
        "scenario_visibility_rule": _event_visibility_rule(
            operation_key, match["capability_class_key"]
        ),
        "scope_relation_rule_key": operation["scope_relation_rule_key"],
        "source_intent_key": spec["source_intent_key"],
        "symbol_domain_ref": _symbol_domain_ref(operation, symbol_order),
        "variant_id": match["variant_id"],
        "wave": operation["wave"],
    }
    if set(row) != SOURCE_EVENT_ROW_FIELDS:
        _fail("expected source lifecycle event row schema drifted")
    return row


def _expected_scope_event_row(spec, ordinal, persona_id):
    profile = spec["operation_key"]
    if profile == "ordinary-scope-index":
        scope_rule = "each-of-twenty-leaf-scopes"
        path_rule = "scope-only-no-path-transition"
        visibility = "visibility/scope-index-nonanchor"
    elif profile == "w5-post-purge-noop-index":
        scope_rule = "each-of-twenty-leaf-scopes"
        path_rule = "scope-only-no-path-transition"
        visibility = "visibility/purge-remains-invisible"
    else:
        _fail(f"unknown scope lifecycle event profile: {profile}")
    row = {
        "abstract_scope_slot_ordinal": spec["scope_slot_ordinal"],
        "byte_transition_rule": "bytes/no-change",
        "dependency_group_key": spec["dependency_group_key"],
        "delta_rule_ref": f"operation-algebra/{profile}",
        "event_intent_key": f"{persona_id}-lifecycle-event-intent-{ordinal:04d}",
        "event_profile_key": profile,
        "event_sequence_ordinal": ordinal,
        "fact_transition_rule": "facts/no-change",
        "path_transition_rule_key": path_rule,
        "persona_id": persona_id,
        "predecessor_event_intent_refs": spec[
            "predecessor_event_intent_refs"
        ],
        "row_kind": "scope",
        "scenario_visibility_rule": visibility,
        "scope_relation_rule_key": scope_rule,
        "symbol_domain_ref": "symbols:none",
        "wave": spec["wave"],
    }
    if set(row) != SCOPE_EVENT_ROW_FIELDS:
        _fail("expected scope lifecycle event row schema drifted")
    return row


_CREATED_SOURCE_OPERATIONS = frozenset(
    {
        "w1-incidental-typed-edit",
        "w1-typed-edit",
        "w3-derive-diagnostic",
        "w3-duplicate-diagnostic-cross-scope",
        "w3-duplicate-diagnostic-same-scope",
        "w3-surface-edit",
        "w4-create-x-prime",
        "w5-create-p-prime",
        "w5-export-x",
        "w5-restore-x",
    }
)


def _event_intent_key(persona_id, ordinal):
    return f"{persona_id}-lifecycle-event-intent-{ordinal:04d}"


def _created_source_intent_key(persona_id, ordinal):
    return f"{persona_id}-pre-solve-source-intent-{ordinal:04d}"


def _capability_suffix(match):
    suffix = match["capability_key"].rsplit("-", 1)[-1]
    if len(suffix) != 3 or not suffix.isascii() or not suffix.isdigit():
        _fail("lifecycle capability suffix is not exact three-digit ASCII")
    return suffix


def _resolve_expected_source_event_dependencies(combined, persona_id):
    """Resolve exact event/source FKs without consulting producer output."""

    entries = []
    by_subject_operation = {}
    primary_by_capability_operation = {}
    for ordinal, (kind, spec) in enumerate(combined, start=1):
        if kind != "source":
            continue
        match = spec["match"]
        operation_key = spec["operation_key"]
        entry = {
            "event_intent_key": _event_intent_key(persona_id, ordinal),
            "ordinal": ordinal,
            "spec": spec,
        }
        subject_coordinate = (
            match["capability_key"],
            match["intent_key"],
            operation_key,
        )
        if subject_coordinate in by_subject_operation:
            _fail("independent source subject/operation coordinate is not unique")
        by_subject_operation[subject_coordinate] = entry
        if not spec.get("companion", False):
            primary_coordinate = (match["capability_key"], operation_key)
            if primary_coordinate in primary_by_capability_operation:
                _fail("independent primary capability operation is not unique")
            primary_by_capability_operation[primary_coordinate] = entry
        entries.append(entry)

    def subject_entry(spec, operation_key, *, required=True):
        match = spec["match"]
        entry = by_subject_operation.get(
            (match["capability_key"], match["intent_key"], operation_key)
        )
        if entry is None and required:
            _fail(
                "independent required predecessor is absent for "
                f"{match['capability_key']}/{operation_key}"
            )
        return entry

    def primary_entry(spec, operation_key):
        entry = primary_by_capability_operation.get(
            (spec["match"]["capability_key"], operation_key)
        )
        if entry is None:
            _fail("independent mirrored primary predecessor is absent")
        return entry

    for entry in entries:
        spec = entry["spec"]
        match = spec["match"]
        operation_key = spec["operation_key"]
        ordinal = entry["ordinal"]
        suffix = _capability_suffix(match)
        capability_class = match["capability_class_key"]

        if operation_key in {"w4-delete", "w4-create-x-prime"}:
            group_key = f"{persona_id}-event-dependency-x4-{suffix}"
        elif operation_key in {
            "w5-export-x",
            "w5-restore-x",
            "w5-delete-x-prime",
        }:
            group_key = f"{persona_id}-event-dependency-x5-{suffix}"
        elif operation_key in {
            "w5-create-p-prime",
            "w5-purge-p",
            "w5-forced-purged-commit",
        }:
            group_key = f"{persona_id}-event-dependency-p5-{suffix}"
        elif operation_key == "w2-move":
            group_key = f"{persona_id}-event-dependency-move-bundle"
        elif (
            capability_class == "replacement-current-cross-format"
            and operation_key in {"w1-typed-edit", "w3-surface-edit"}
        ):
            wave = "w1" if operation_key == "w1-typed-edit" else "w3"
            group_key = f"{persona_id}-event-dependency-mirror-{wave}"
        else:
            group_key = f"{persona_id}-event-dependency-single-{ordinal:04d}"

        predecessors = []
        source_intent_key = match["intent_key"]
        prior = None
        if operation_key == "w2-move":
            prior = subject_entry(
                spec, "w1-incidental-typed-edit", required=False
            )
        elif operation_key == "w3-surface-edit":
            prior = subject_entry(spec, "w1-typed-edit")
        elif operation_key in {"w4-delete", "w4-archive"}:
            prior = subject_entry(spec, "w3-surface-edit")
        elif operation_key == "w4-create-x-prime":
            prior = subject_entry(spec, "w3-surface-edit")
            predecessors.append(
                subject_entry(spec, "w4-delete")["event_intent_key"]
            )
        elif operation_key == "w5-export-x":
            prior = subject_entry(spec, "w3-surface-edit")
            predecessors.append(
                subject_entry(spec, "w4-delete")["event_intent_key"]
            )
        elif operation_key == "w5-restore-x":
            prior = subject_entry(spec, "w5-export-x")
        elif operation_key == "w5-delete-x-prime":
            x_prime = subject_entry(spec, "w4-create-x-prime")
            restore = subject_entry(spec, "w5-restore-x")
            source_intent_key = _created_source_intent_key(
                persona_id, x_prime["ordinal"]
            )
            predecessors.extend(
                [x_prime["event_intent_key"], restore["event_intent_key"]]
            )
        elif operation_key in {
            "w5-create-p-prime",
            "w5-purge-p",
            "w5-forced-purged-commit",
        }:
            prior = subject_entry(spec, "w1-typed-edit")
            if operation_key == "w5-purge-p":
                predecessors.append(
                    subject_entry(spec, "w5-create-p-prime")[
                        "event_intent_key"
                    ]
                )
            elif operation_key == "w5-forced-purged-commit":
                predecessors.append(
                    subject_entry(spec, "w5-purge-p")["event_intent_key"]
                )

        if prior is not None and operation_key not in {
            "w4-create-x-prime",
            "w5-export-x",
            "w5-delete-x-prime",
            "w5-forced-purged-commit",
        }:
            predecessors.append(prior["event_intent_key"])
        if prior is not None:
            source_intent_key = prior["spec"]["after_source_intent_key"]

        if spec.get("companion", False) and capability_class == (
            "replacement-current-cross-format"
        ):
            predecessors.append(
                primary_entry(spec, operation_key)["event_intent_key"]
            )

        predecessors = sorted(
            set(predecessors), key=lambda key: int(key.rsplit("-", 1)[-1])
        )
        after_source_intent_key = (
            _created_source_intent_key(persona_id, ordinal)
            if operation_key in _CREATED_SOURCE_OPERATIONS
            else source_intent_key
        )
        spec["after_source_intent_key"] = after_source_intent_key
        spec["dependency_group_key"] = group_key
        spec["predecessor_event_intent_refs"] = predecessors
        spec["source_intent_key"] = source_intent_key

    ordinal_by_event = {
        entry["event_intent_key"]: entry["ordinal"] for entry in entries
    }
    group_profiles = defaultdict(list)
    for entry in entries:
        spec = entry["spec"]
        group_profiles[spec["dependency_group_key"]].append(
            spec["operation_key"]
        )
        for predecessor in spec["predecessor_event_intent_refs"]:
            if (
                predecessor not in ordinal_by_event
                or ordinal_by_event[predecessor] >= entry["ordinal"]
            ):
                _fail("independent event predecessor is absent or not earlier")

    multi_groups = {
        key: profiles for key, profiles in group_profiles.items() if len(profiles) > 1
    }
    expected_group_shapes = Counter(
        {
            ("w4-create-x-prime", "w4-delete"): 20,
            ("w5-delete-x-prime", "w5-export-x", "w5-restore-x"): 10,
            ("w5-create-p-prime", "w5-forced-purged-commit", "w5-purge-p"): 15,
            ("w2-move",) * 5: 1,
            ("w1-typed-edit",) * 2: 1,
            ("w3-surface-edit",) * 2: 1,
        }
    )
    actual_group_shapes = Counter(
        tuple(sorted(profiles)) for profiles in multi_groups.values()
    )
    if len(multi_groups) != 48 or actual_group_shapes != expected_group_shapes:
        _fail("independent multi-event dependency group partition drifted")

    created_entries = [
        entry
        for entry in entries
        if entry["spec"]["operation_key"] in _CREATED_SOURCE_OPERATIONS
    ]
    if any(
        entry["spec"]["after_source_intent_key"]
        != _created_source_intent_key(persona_id, entry["ordinal"])
        for entry in created_entries
    ):
        _fail("independent created source intent namespace drifted")
    if any(
        entry["spec"]["after_source_intent_key"]
        != entry["spec"]["source_intent_key"]
        for entry in entries
        if entry["spec"]["operation_key"] not in _CREATED_SOURCE_OPERATIONS
    ):
        _fail("non-created event changed exact source identity")
    diagnostic_count = sum(
        entry["spec"]["operation_key"].startswith("w3-derive-diagnostic")
        or entry["spec"]["operation_key"].startswith(
            "w3-duplicate-diagnostic"
        )
        for entry in entries
    )
    if len(created_entries) != 179 + diagnostic_count or len(
        {entry["spec"]["after_source_intent_key"] for entry in created_entries}
    ) != len(created_entries):
        _fail("independent created source intent count or uniqueness drifted")


def _expected_event_rows(inputs, persona_id, primary_rows, companion_rows):
    coverage = inputs["coverage"]
    operations = {
        row["operation_key"]: row for row in coverage["operation_algebra"]
    }
    operation_order = {
        row["operation_key"]: index
        for index, row in enumerate(coverage["operation_algebra"])
    }
    symbol_order = [row["symbol"] for row in coverage["symbol_contracts"]]
    capability_by_key = {
        row["capability_key"]: row
        for row in coverage["primary_capabilities"]
        if row["persona_id"] == persona_id
    }
    primary_by_key = {row["capability_key"]: row for row in primary_rows}
    companion_by_key = {
        row["primary_capability_key"]: row for row in companion_rows
    }
    specs = []
    baseline_counts = Counter()
    for capability_key in sorted(primary_by_key, key=_ascii_key):
        capability = capability_by_key[capability_key]
        for operation_key in capability["required_event_profile_keys"]:
            specs.append(
                {
                    "match": primary_by_key[capability_key],
                    "operation_key": operation_key,
                }
            )
            baseline_counts[operation_key] += 1
            if (
                capability["capability_class_key"]
                == "replacement-current-cross-format"
                and operation_key in {"w1-typed-edit", "w3-surface-edit"}
            ):
                companion = companion_by_key[capability_key]
                specs.append(
                    {
                        "companion": True,
                        "match": {
                            **companion,
                            "capability_class_key": capability[
                                "capability_class_key"
                            ],
                            "capability_key": capability_key,
                        },
                        "operation_key": operation_key,
                    }
                )
                baseline_counts[operation_key] += 1
    if baseline_counts != Counter(SOURCE_EVENT_TYPE_COUNTS_PER_PERSONA):
        _fail("independent baseline lifecycle event counts drifted")

    diagnostic_count = 5 * int(persona_id in DERIVE_DIAGNOSTIC_PERSONAS)
    diagnostic_count += 5 * int(persona_id in DUPLICATE_DIAGNOSTIC_PERSONAS)
    diagnostic_sources = sorted(
        (
            row
            for row in primary_rows
            if row["capability_class_key"].startswith("stable-current-")
        ),
        key=lambda row: _domain_key("diagnostic-source", row["intent_key"]),
    )[:diagnostic_count]
    cursor = 0
    if persona_id in DERIVE_DIAGNOSTIC_PERSONAS:
        for match in diagnostic_sources[:5]:
            specs.append(
                {
                    "diagnostic": True,
                    "match": match,
                    "operation_key": "w3-derive-diagnostic",
                }
            )
        cursor = 5
    if persona_id in DUPLICATE_DIAGNOSTIC_PERSONAS:
        for index, match in enumerate(
            diagnostic_sources[cursor : cursor + 5], start=1
        ):
            specs.append(
                {
                    "diagnostic": True,
                    "match": match,
                    "operation_key": (
                        "w3-duplicate-diagnostic-same-scope"
                        if index in {1, 3, 5}
                        else "w3-duplicate-diagnostic-cross-scope"
                    ),
                }
            )

    purged_matches = [
        row
        for row in primary_rows
        if row["capability_class_key"] == "purged-negative"
    ]
    if len(purged_matches) != 15:
        _fail("independent forced purge source count drifted")
    for match in purged_matches:
        specs.append(
            {
                "match": match,
                "operation_key": "w5-forced-purged-commit",
            }
        )

    wave_order = list(coverage["orders"]["wave_order"])
    wave_index = {wave: index for index, wave in enumerate(wave_order)}
    specs.sort(
        key=lambda spec: (
            wave_index[operations[spec["operation_key"]]["wave"]],
            operation_order[spec["operation_key"]],
            _ascii_key(spec["match"]["capability_key"]),
            spec.get("companion", False),
            _ascii_key(spec["match"]["intent_key"]),
        )
    )
    scope_specs = [
        {
            "operation_key": "ordinary-scope-index",
            "scope_slot_ordinal": scope_slot,
            "wave": wave,
        }
        for wave in ("W1", "W2", "W3", "W4", "W5-pre-purge")
        for scope_slot in range(1, 21)
    ]
    scope_specs.extend(
        {
            "operation_key": "w5-post-purge-noop-index",
            "scope_slot_ordinal": scope_slot,
            "wave": "W5-final",
        }
        for scope_slot in range(1, 21)
    )
    combined = []
    for wave in wave_order:
        combined.extend(
            ("source", spec)
            for spec in specs
            if operations[spec["operation_key"]]["wave"] == wave
        )
        combined.extend(
            ("scope", spec) for spec in scope_specs if spec["wave"] == wave
        )
    _resolve_expected_source_event_dependencies(combined, persona_id)
    last_source_event_by_wave = {}
    for ordinal, (kind, spec) in enumerate(combined, start=1):
        if kind == "source":
            last_source_event_by_wave[
                operations[spec["operation_key"]]["wave"]
            ] = _event_intent_key(persona_id, ordinal)
    for kind, spec in combined:
        if kind != "scope":
            continue
        wave = spec["wave"]
        predecessor = last_source_event_by_wave.get(wave)
        if predecessor is None:
            _fail(f"independent scope barrier lacks source events for {wave}")
        spec["dependency_group_key"] = (
            f"{persona_id}-event-dependency-index-barrier-{wave.lower()}"
        )
        spec["predecessor_event_intent_refs"] = [predecessor]
    rows = []
    for ordinal, (kind, spec) in enumerate(combined, start=1):
        if kind == "source":
            rows.append(
                _expected_source_event_row(
                    spec,
                    ordinal,
                    persona_id,
                    operations[spec["operation_key"]],
                    symbol_order,
                )
            )
        else:
            rows.append(_expected_scope_event_row(spec, ordinal, persona_id))
    if len(rows) != EXPECTED_EVENT_BASELINE_PER_PERSONA + diagnostic_count:
        _fail("independent expanded event count drifted")
    return rows


def _expected_event_receipt(rows, persona_id):
    parts = [
        _canonical(
            row,
            label="source-matched lifecycle expected event row",
            maximum=MAX_EVENT_ROW_BYTES_INCLUDING_LF - 1,
        )
        + b"\n"
        for row in rows
    ]
    if any(len(part) > MAX_EVENT_ROW_BYTES_INCLUDING_LF for part in parts):
        _fail("expected event row exceeds LF-inclusive bound")
    body = b"".join(parts)
    if len(body) > MAX_EVENT_BODY_BYTES:
        _fail("expected event body exceeds bound")
    return {
        "body_bytes": len(body),
        "body_persisted": False,
        "body_sha256": hashlib.sha256(body).hexdigest(),
        "first_event_intent_key": rows[0]["event_intent_key"],
        "first_event_sequence_ordinal": rows[0]["event_sequence_ordinal"],
        "last_event_intent_key": rows[-1]["event_intent_key"],
        "last_event_sequence_ordinal": rows[-1]["event_sequence_ordinal"],
        "maximum_row_bytes_including_lf": max(map(len, parts)),
        "persona_id": persona_id,
        "row_count": len(rows),
    }


def _expected_persona_value(
    inputs,
    persona_id,
    joined,
    primary_rows,
    companion_rows,
    reserved_rows,
    witness_rows,
    event_rows,
):
    bindings = _global_bindings(inputs, joined) + _persona_origin_bindings(joined)
    witness_counts = {
        classification: sum(
            row["classification"] == classification for row in witness_rows
        )
        for classification in (
            "searchable-positive",
            "pending-conversion-negative",
            "raw-only-structural-negative",
        )
    }
    incidental_targets = [
        joined["cell_by_key"][row["parameter_cell_key"]]["target_bytes"]
        for row in primary_rows
        if row["gate_role"] == "incidental_searchable"
    ]
    value = {
        "artifact_kind": PERSONA_KIND,
        "artifact_schema": PERSONA_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": _negative_authority(),
        "canonical_limits": {
            "event_jsonl_record_terminator": "LF",
            "framed_byte_cap_before_body_required": True,
            "max_body_bytes": MAX_PERSONA_BYTES,
            "max_event_body_bytes_nonpersisted": MAX_EVENT_BODY_BYTES,
            "max_event_row_bytes_including_lf": MAX_EVENT_ROW_BYTES_INCLUDING_LF,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_105_primary_capabilities_source_matched": True,
            "all_10_cross_format_companions_source_matched": True,
            "all_required_family_witnesses_bound": True,
            "compiled_history_plan_available": False,
            "concrete_scope_path_quota_or_final_ids_present": False,
            "event_expanded_body_persisted": False,
            "event_intent_inventory_receipted": True,
            "full_profile_reuses_exact_pilot_selection": True,
            "query_or_oracle_dependency_present": False,
        },
        "completion_scope": (
            "one-persona-pre-solve-pilot-source-matching-format-witness-and-"
            "lifecycle-event-intent-receipt-only-no-scope-solution-query-"
            "render-write-execution-observation-or-g0"
        ),
        "dependency_direction_contract": {
            "assignment_cells_are_content_parameters_not_quota_or_scope": True,
            "base_companion_membership_is_reconciled_downstream_to_primary_chain": True,
            "content_only_projection_includes_event_content_not_runtime_fields": True,
            "event_created_p_prime_or_x_prime_may_be_selected_at_w0": False,
            "evaluation_query_or_oracle_imported": False,
            "full_profile_may_select_full_residual_lifecycle_sources": False,
            "source_matching_may_bind_solved_scope_path_or_final_identity": False,
        },
        "event_receipt": _expected_event_receipt(event_rows, persona_id),
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "input_binding_order": [row["name"] for row in bindings],
        "input_bindings": bindings,
        "orders": {
            "companion_match_rows": "primary-capability-key-ascii",
            "event_rows_nonpersisted": (
                "wave-operation-capability-source-then-scope-slot"
            ),
            "primary_match_rows": "capability-key-ascii",
            "reserved_semantic_anchor_rows": "semantic-anchor-slot-ordinal",
            "use_case_family_witness_rows": (
                "primary-use-case-required-family-order"
            ),
        },
        "persona_id": persona_id,
        "selection_policy": {
            "companion_effective_membership_rule": (
                "replace-with-primary-lifecycle-logical-document-fact-revision-chain"
            ),
            "cross_format_candidate_requirement": (
                "same-base-topic-and-language-different-family-overlay-unreserved-contributor"
            ),
            "cross_format_matching_algorithm": (
                "domain-separated-sha256-order-dfs-augmenting-path-stop-after-ten"
            ),
            "full_profile_source_selection": (
                "byte-identical-pilot-reuse-no-residual"
            ),
            "incidental_assignment_cell_target_bytes_inclusive_maximum": 32_768,
            "incidental_observed_chunk_domain": {
                "inclusive_maximum": 70,
                "inclusive_minimum": 1,
                "observed_values_present": False,
            },
            "negative_family_sources": (
                "extra-overlay-unreserved-pilot-raw-only"
            ),
            "positive_family_sources": (
                "matched-lifecycle-primary-query-anchor"
            ),
            "semantic_anchor_selection": (
                "ten-cross-first-then-ninety-primary-hash-order"
            ),
            "semantic_anchor_slots_reserved_unused": 5,
            "source_or_event_final_identity_present": False,
        },
        "primary_match_rows": primary_rows,
        "companion_match_rows": companion_rows,
        "reserved_semantic_anchor_rows": reserved_rows,
        "use_case_family_witness_rows": witness_rows,
        "remaining_blockers": [
            "effective-lifecycle-fact-and-rendition-overlay-not-built",
            "scope-bucket-cohort-quota-solver-solution-and-proof-not-built",
            "solution-compiled-history-plan-and-pre-w2-patch-not-built",
            "query-render-evaluation-target-and-relevance-not-built",
            "filesystem-render-index-history-kio-receipts-and-g0-not-built",
        ],
        "summary": {
            "companion_source_match_count": len(companion_rows),
            "contributor_primary_source_match_count": sum(
                row["gate_role"] == "contract_contributor"
                for row in primary_rows
            ),
            "derive_diagnostic_event_count": (
                5 if persona_id in DERIVE_DIAGNOSTIC_PERSONAS else 0
            ),
            "duplicate_diagnostic_event_count": (
                5 if persona_id in DUPLICATE_DIAGNOSTIC_PERSONAS else 0
            ),
            "event_intent_count": len(event_rows),
            "format_witness_counts": witness_counts,
            "format_witness_count": len(witness_rows),
            "incidental_primary_source_match_count": sum(
                row["gate_role"] == "incidental_searchable"
                for row in primary_rows
            ),
            "incidental_selected_target_bytes_maximum": max(incidental_targets),
            "lifecycle_source_ref_count": EXPECTED_LIFECYCLE_SOURCE_REFS_PER_PERSONA,
            "negative_extra_physical_witness_count": sum(
                not row["query_answer_anchor_required"] for row in witness_rows
            ),
            "primary_source_match_count": len(primary_rows),
            "reserved_unused_semantic_anchor_count": len(reserved_rows),
            "selected_pilot_parameter_assignment_resolution_count": len(
                {
                    row["intent_key"]
                    for row in primary_rows + companion_rows + witness_rows
                }
            ),
        },
    }
    if set(value) != PERSONA_TOP_LEVEL_FIELDS:
        _fail("independent expected persona top-level schema drifted")
    return value


def _reconstruct_expected_persona(
    inputs, persona_id, *, assignment_origin_provider=None
):
    joined = _load_pilot_records(
        inputs,
        persona_id,
        assignment_origin_provider=assignment_origin_provider,
    )
    selection = _reconstruct_selection(inputs, persona_id, joined)
    primary_rows, companion_rows = _build_match_rows(
        inputs, persona_id, joined, selection
    )
    witness_rows = _build_format_witness_rows(
        persona_id, selection, primary_rows, joined
    )
    reserved_rows = _build_reserved_anchor_rows(joined, selection)
    event_rows = _expected_event_rows(
        inputs, persona_id, primary_rows, companion_rows
    )
    value = _expected_persona_value(
        inputs,
        persona_id,
        joined,
        primary_rows,
        companion_rows,
        reserved_rows,
        witness_rows,
        event_rows,
    )
    return {
        "event_rows": event_rows,
        "joined": joined,
        "persona": value,
        "selection": selection,
    }


def _persona_binding(value):
    return _bound_artifact(
        "persona-v2-source-matched-lifecycle-persona",
        "one-persona-compact-source-match-and-event-receipt-owner",
        value,
        lambda item: _canonical(
            item,
            label="bound source-matched lifecycle persona",
            maximum=MAX_PERSONA_BYTES,
        ),
        coordinates=("persona_id",),
    )


def _expected_suite_value(inputs, reconstructed):
    personas = [reconstructed[persona_id]["persona"] for persona_id in PERSONA_IDS]
    persona_bindings = [_persona_binding(value) for value in personas]
    global_bindings = _global_bindings(
        inputs, reconstructed[PERSONA_IDS[0]]["joined"]
    )
    witness_counts = {
        classification: sum(
            row["classification"] == classification
            for value in personas
            for row in value["use_case_family_witness_rows"]
        )
        for classification in (
            "searchable-positive",
            "pending-conversion-negative",
            "raw-only-structural-negative",
        )
    }
    event_count = sum(
        value["summary"]["event_intent_count"] for value in personas
    )
    witness_count = sum(
        value["summary"]["format_witness_count"] for value in personas
    )
    if (
        event_count != EXPECTED_EVENT_SUITE_COUNT
        or witness_count != EXPECTED_FORMAT_WITNESS_COUNT
        or witness_counts != FAMILY_CLASS_COUNTS
    ):
        _fail("independent suite event/witness totals drifted")
    value = {
        "artifact_kind": SUITE_KIND,
        "artifact_schema": SUITE_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": _negative_authority(),
        "canonical_limits": {
            "max_body_bytes": MAX_SUITE_BYTES,
            "max_content_projection_bytes": MAX_CONTENT_PROJECTION_BYTES,
            "max_event_body_bytes_per_persona_nonpersisted": MAX_EVENT_BODY_BYTES,
            "max_event_row_bytes_including_lf": MAX_EVENT_ROW_BYTES_INCLUDING_LF,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_persona_match_owner_bytes": MAX_PERSONA_BYTES,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "target_content_projection_bytes": TARGET_CONTENT_PROJECTION_BYTES,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_20_persona_match_owners_bound": True,
            "all_2100_primary_capabilities_source_matched": True,
            "all_200_companion_requirements_source_matched": True,
            "all_2300_lifecycle_source_refs_bound": True,
            "all_7630_event_intents_receipted": True,
            "all_93_required_family_witnesses_bound": True,
            "compiled_history_plan_available": False,
            "query_or_oracle_dependency_present": False,
            "solved_scope_path_quota_or_final_ids_present": False,
        },
        "completion_scope": (
            "all-twenty-pre-solve-source-matched-lifecycle-and-format-witness-"
            "inventory-only-no-scope-solution-query-render-write-execution-or-g0"
        ),
        "dependency_direction_contract": {
            "content_only_projections_include_query_independent_event_content": True,
            "full_profile_is_exact-pilot-selection-reuse": True,
            "persona_match_owners_are_strictly-upstream-of-solver": True,
            "query_or_oracle_may_back-bind-source-matching": False,
        },
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "input_binding_order": [row["name"] for row in global_bindings],
        "input_bindings": global_bindings,
        "orders": {
            "persona_bindings": "persona-id",
            "persona_local_rows": "owned-by-bound-persona-manifest",
        },
        "persona_bindings": persona_bindings,
        "policy": {
            "diagnostic_derive_personas": sorted(DERIVE_DIAGNOSTIC_PERSONAS),
            "diagnostic_duplicate_personas": sorted(
                DUPLICATE_DIAGNOSTIC_PERSONAS
            ),
            "duplicate_branch_pattern": [
                "same-scope",
                "cross-scope",
                "same-scope",
                "cross-scope",
                "same-scope",
            ],
            "event_baseline_per_persona": EXPECTED_EVENT_BASELINE_PER_PERSONA,
            "format_witness_classification": {
                "pending-conversion-negative": sorted(
                    PENDING_CONVERSION_FAMILIES
                ),
                "raw-only-structural-negative": sorted(RAW_ONLY_FAMILIES),
                "searchable-positive": sorted(SEARCHABLE_POSITIVE_FAMILIES),
            },
            "physical_lane_mapping_stage": "downstream-solution-compositor",
            "query_answer_anchor_required_for_searchable_positive": True,
        },
        "remaining_blockers": [
            "effective-lifecycle-membership-overlay-not-built",
            "joint-scope-quota-solver-and-proof-not-built",
            "compiled-history-plan-and-execution-not-built",
            "query-render-evaluation-and-kio-observation-not-built",
            "g0-contract-not-frozen",
        ],
        "summary": {
            "companion_source_match_count": sum(
                item["summary"]["companion_source_match_count"]
                for item in personas
            ),
            "event_intent_count": event_count,
            "format_witness_count": witness_count,
            "format_witness_counts": witness_counts,
            "lifecycle_source_ref_count": sum(
                item["summary"]["lifecycle_source_ref_count"]
                for item in personas
            ),
            "maximum_event_body_bytes_nonpersisted": max(
                item["event_receipt"]["body_bytes"] for item in personas
            ),
            "maximum_event_row_bytes_including_lf": max(
                item["event_receipt"]["maximum_row_bytes_including_lf"]
                for item in personas
            ),
            "maximum_persona_match_owner_bytes": max(
                len(
                    _canonical(
                        item,
                        label="suite-bound source-matched lifecycle persona",
                        maximum=MAX_PERSONA_BYTES,
                    )
                )
                for item in personas
            ),
            "persona_count": len(personas),
            "primary_source_match_count": sum(
                item["summary"]["primary_source_match_count"] for item in personas
            ),
            "reserved_unused_semantic_anchor_count": sum(
                item["summary"]["reserved_unused_semantic_anchor_count"]
                for item in personas
            ),
        },
    }
    if set(value) != SUITE_TOP_LEVEL_FIELDS:
        _fail("independent expected suite top-level schema drifted")
    return value


def _expected_content_projection(persona_id, persona, event_rows):
    by_intent = {}

    def add(row, role):
        intent_key = row["intent_key"]
        existing = by_intent.setdefault(
            intent_key,
            {
                "family": row["family"],
                "gate_role": (
                    "raw_only"
                    if role.startswith("format-negative:")
                    else row.get("gate_role", "raw_only")
                ),
                "intent_key": intent_key,
                "parameter_cell_key": row["parameter_cell_key"],
                "selection_role_refs": [],
                "source_profile_id": row["source_profile_id"],
                "variant_id": row["variant_id"],
            },
        )
        comparable = {
            key: item for key, item in existing.items() if key != "selection_role_refs"
        }
        candidate = {
            "family": row["family"],
            "gate_role": existing["gate_role"],
            "intent_key": intent_key,
            "parameter_cell_key": row["parameter_cell_key"],
            "source_profile_id": row["source_profile_id"],
            "variant_id": row["variant_id"],
        }
        if comparable != candidate:
            _fail("content projection intent metadata conflict")
        existing["selection_role_refs"].append(role)

    for row in persona["primary_match_rows"]:
        add(row, f"primary:{row['capability_key']}")
    for row in persona["companion_match_rows"]:
        add(row, f"companion:{row['companion_requirement_key']}")
    for row in persona["use_case_family_witness_rows"]:
        prefix = (
            "format-positive"
            if row["classification"] == "searchable-positive"
            else "format-negative"
        )
        add(row, f"{prefix}:{row['family']}")
    source_selection_rows = []
    for intent_key in sorted(by_intent, key=_ascii_key):
        row = by_intent[intent_key]
        row["selection_role_refs"].sort(key=_ascii_key)
        if set(row) != CONTENT_ROW_FIELDS:
            _fail("independent content projection row schema drifted")
        source_selection_rows.append(row)

    source_event_rows = []
    scope_event_rows = []
    created_source_intent_count = 0
    dependency_group_counts = Counter()
    for event in event_rows:
        if set(event) == SOURCE_EVENT_ROW_FIELDS:
            projected = {
                key: event[key] for key in CONTENT_SOURCE_EVENT_ROW_FIELDS
            }
            if set(projected) != CONTENT_SOURCE_EVENT_ROW_FIELDS:
                _fail("independent projected source event schema drifted")
            if event["after_source_intent_key"] == _created_source_intent_key(
                persona_id, event["event_sequence_ordinal"]
            ):
                created_source_intent_count += 1
            source_event_rows.append(projected)
        elif set(event) == SCOPE_EVENT_ROW_FIELDS:
            projected = {
                key: event[key] for key in CONTENT_SCOPE_EVENT_ROW_FIELDS
            }
            if set(projected) != CONTENT_SCOPE_EVENT_ROW_FIELDS:
                _fail("independent projected scope event schema drifted")
            scope_event_rows.append(projected)
        else:
            _fail("independent projection received unknown event row schema")
        dependency_group_counts[event["dependency_group_key"]] += 1

    content_sections = {
        "scope_event_rows": scope_event_rows,
        "source_event_rows": source_event_rows,
        "source_selection_rows": source_selection_rows,
    }
    if set(content_sections) != CONTENT_SECTIONS_FIELDS:
        _fail("independent content projection section schema drifted")
    multi_event_dependency_group_count = sum(
        count > 1 for count in dependency_group_counts.values()
    )
    if multi_event_dependency_group_count != 54:
        _fail("independent projected dependency group count drifted")
    value = {
        "artifact_kind": PROJECTION_KIND,
        "artifact_schema": PROJECTION_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "content_sections": content_sections,
        "content_rules": {
            "companion_effective_membership": (
                "replace-with-primary-lifecycle-logical-document-fact-revision-chain"
            ),
            "created_source_intent_namespace": (
                "persona-pre-solve-source-intent-by-event-ordinal"
            ),
            "dependency_identity": (
                "exact-group-key-and-full-predecessor-event-intent-refs"
            ),
            "full_profile_selection": (
                "exact-pilot-intent-reuse-no-residual-selection"
            ),
            "lifecycle_event_order": "event-sequence-ordinal",
            "parameter_cell_identity": (
                "authenticated-upstream-parameter-cell-key"
            ),
            "projection_excludes": [
                "authority",
                "dependency-bindings-and-sha",
                "event-receipts-and-expanded-runtime-payloads",
                "query-or-oracle-fields",
                "runtime-review-and-completion-fields",
            ],
        },
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "persona_id": persona_id,
        "summary": {
            "created_source_intent_count": created_source_intent_count,
            "lifecycle_event_content_row_count": (
                len(source_event_rows) + len(scope_event_rows)
            ),
            "multi_event_dependency_group_count": (
                multi_event_dependency_group_count
            ),
            "negative_extra_witness_content_row_count": persona["summary"][
                "negative_extra_physical_witness_count"
            ],
            "selection_role_reference_count": sum(
                len(row["selection_role_refs"])
                for row in source_selection_rows
            ),
            "source_event_content_row_count": len(source_event_rows),
            "source_selection_content_row_count": len(
                source_selection_rows
            ),
            "scope_event_content_row_count": len(scope_event_rows),
            "unique_selected_intent_count": len(source_selection_rows),
        },
    }
    if set(value) != PROJECTION_TOP_LEVEL_FIELDS:
        _fail("independent content projection top-level schema drifted")
    raw = _canonical(
        value,
        label="independent source-matched lifecycle content projection",
        maximum=MAX_CONTENT_PROJECTION_BYTES,
    )
    if len(raw) > TARGET_CONTENT_PROJECTION_BYTES:
        _fail("independent content projection exceeds 256-KiB target")
    return value


def _event_rows_from_provider(persona_id, receipt, event_body_provider):
    if type(receipt) is not dict or set(receipt) != EVENT_RECEIPT_FIELDS:
        _fail("event receipt schema drifted")
    if (
        receipt["persona_id"] != persona_id
        or receipt["body_persisted"] is not False
        or type(receipt["row_count"]) is not int
        or type(receipt["row_count"]) is bool
        or receipt["row_count"] < 1
        or type(receipt["first_event_sequence_ordinal"]) is not int
        or type(receipt["first_event_sequence_ordinal"]) is bool
        or type(receipt["last_event_sequence_ordinal"]) is not int
        or type(receipt["last_event_sequence_ordinal"]) is bool
        or type(receipt["maximum_row_bytes_including_lf"]) is not int
        or type(receipt["maximum_row_bytes_including_lf"]) is bool
        or receipt["maximum_row_bytes_including_lf"] < 1
        or receipt["first_event_sequence_ordinal"] != 1
        or receipt["last_event_sequence_ordinal"] != receipt["row_count"]
        or receipt["maximum_row_bytes_including_lf"]
        > MAX_EVENT_ROW_BYTES_INCLUDING_LF
    ):
        _fail("event receipt coordinate/count/bounds drifted")
    body = _authenticated_body(
        event_body_provider,
        (persona_id,),
        expected_bytes=receipt["body_bytes"],
        expected_sha256=receipt["body_sha256"],
        maximum_bytes=MAX_EVENT_BODY_BYTES,
        label="source-matched lifecycle event body",
        replay=True,
    )
    rows = _parse_jsonl(
        body,
        label="source-matched lifecycle event body",
        maximum_row_bytes=MAX_EVENT_ROW_BYTES_INCLUDING_LF,
    )
    if len(rows) != receipt["row_count"]:
        _fail("event body row count differs from its receipt")
    if (
        receipt["maximum_row_bytes_including_lf"]
        != max(len(line) + 1 for line in body.splitlines())
        or receipt["first_event_intent_key"] != rows[0].get("event_intent_key")
        or receipt["last_event_intent_key"] != rows[-1].get("event_intent_key")
    ):
        _fail("event receipt boundary or maximum-row metadata drifted")

    source_rows = []
    scope_rows = []
    event_keys = set()
    for ordinal, row in enumerate(rows, start=1):
        if (
            row.get("persona_id") != persona_id
            or row.get("event_sequence_ordinal") != ordinal
            or type(row.get("event_intent_key")) is not str
            or row["event_intent_key"] in event_keys
        ):
            _fail("event identity/order is not exact persona-local sequence")
        event_keys.add(row["event_intent_key"])
        if set(row) == SOURCE_EVENT_ROW_FIELDS:
            source_rows.append(row)
        elif set(row) == SCOPE_EVENT_ROW_FIELDS:
            scope_rows.append(row)
        else:
            _fail("event row does not match exact source or scope schema")

    diagnostic_count = 5 * int(persona_id in DERIVE_DIAGNOSTIC_PERSONAS)
    diagnostic_count += 5 * int(persona_id in DUPLICATE_DIAGNOSTIC_PERSONAS)
    if (
        len(source_rows) != 244 + 15 + diagnostic_count
        or len(scope_rows) != 120
        or len(rows) != 379 + diagnostic_count
    ):
        _fail("event source/scope/baseline/diagnostic counts drifted")
    source_profile_counts = Counter(
        row["event_profile_key"] for row in source_rows
    )
    for key, count in SOURCE_EVENT_TYPE_COUNTS_PER_PERSONA.items():
        if source_profile_counts[key] != count:
            _fail(f"baseline source event count drifted: {key}")
    if sum(SOURCE_EVENT_TYPE_COUNTS_PER_PERSONA.values()) != 244:
        _fail("internal baseline source event count drifted")
    derive_count = sum(
        "derive-diagnostic" in key for key in source_profile_counts.elements()
    )
    duplicate_count = sum(
        "duplicate-diagnostic" in key for key in source_profile_counts.elements()
    )
    forced_count = sum(
        "forced-purg" in key for key in source_profile_counts.elements()
    )
    if (
        derive_count != 5 * int(persona_id in DERIVE_DIAGNOSTIC_PERSONAS)
        or duplicate_count
        != 5 * int(persona_id in DUPLICATE_DIAGNOSTIC_PERSONAS)
        or forced_count != 15
    ):
        _fail("diagnostic or forced-purge source event counts drifted")
    scope_profile_counts = Counter(
        row["event_profile_key"] for row in scope_rows
    )
    if scope_profile_counts != Counter(
        {"ordinary-scope-index": 100, "w5-post-purge-noop-index": 20}
    ):
        _fail("ordinary/post-purge scope event counts drifted")
    if len({row["abstract_scope_slot_ordinal"] for row in scope_rows}) != 20:
        _fail("scope event rows must cover twenty abstract scope slots")
    return rows


def validate_source_matched_lifecycle_persona(
    persona_id,
    value,
    *,
    event_body_provider=None,
    coverage_value=None,
    use_case_value=None,
    variant_value=None,
    source_suite_value=None,
    reservation_suite_value=None,
    semantic_suite_value=None,
    inventory_profile_value=None,
    assignment_origin_provider=None,
):
    """Validate one persona owner and its unpersisted event view independently."""

    _require_persona_id(persona_id)
    if type(value) is not dict:
        _fail("source-matched lifecycle persona must be an object")
    target, opening_target = _opening_snapshot(
        value,
        label="source-matched lifecycle persona",
        maximum=MAX_PERSONA_BYTES,
    )
    if (
        set(target) != PERSONA_TOP_LEVEL_FIELDS
        or target.get("artifact_kind") != PERSONA_KIND
        or target.get("artifact_schema") != PERSONA_SCHEMA
        or target.get("artifact_schema_version") != SCHEMA_VERSION
        or target.get("fixture_id") != envelope.FIXTURE_ID
        or target.get("fixture_schema_version")
        != envelope.FIXTURE_SCHEMA_VERSION
        or target.get("persona_id") != persona_id
    ):
        _fail("source-matched lifecycle persona envelope drifted")
    _require_all_false_authority(
        target,
        label="source-matched lifecycle persona",
        exact_fields=AUTHORITY_FIELDS,
    )
    _strict_json_domain(target)
    _reject_forbidden_keys(target)

    overrides = {
        "coverage": coverage_value,
        "use_cases": use_case_value,
        "variants": variant_value,
        "source_suite": source_suite_value,
        "reservation_suite": reservation_suite_value,
        "semantic_suite": semantic_suite_value,
        "inventory_profiles": inventory_profile_value,
    }
    originals = canonicalizers = opening_inputs = None
    try:
        originals, canonicalizers, opening_inputs, inputs = _resolve_inputs(
            overrides
        )
        joined = _load_pilot_records(
            inputs,
            persona_id,
            assignment_origin_provider=assignment_origin_provider,
        )
        selection = _reconstruct_selection(inputs, persona_id, joined)
        primary_rows, companion_rows = _build_match_rows(
            inputs, persona_id, joined, selection
        )
        witness_rows = _build_format_witness_rows(
            persona_id, selection, primary_rows, joined
        )
        reserved_rows = _build_reserved_anchor_rows(joined, selection)
        if not _strict_equal(target["primary_match_rows"], primary_rows):
            _fail(
                "primary matches differ from independent source reconstruction at "
                + _first_difference(target["primary_match_rows"], primary_rows)
            )
        if not _strict_equal(target["companion_match_rows"], companion_rows):
            _fail(
                "companion matches differ from independent source reconstruction at "
                + _first_difference(target["companion_match_rows"], companion_rows)
            )
        if not _strict_equal(
            target["use_case_family_witness_rows"], witness_rows
        ):
            _fail(
                "format witnesses differ from independent source reconstruction at "
                + _first_difference(
                    target["use_case_family_witness_rows"], witness_rows
                )
            )
        if not _strict_equal(
            target["reserved_semantic_anchor_rows"], reserved_rows
        ):
            _fail(
                "reserved anchors differ from independent source reconstruction at "
                + _first_difference(
                    target["reserved_semantic_anchor_rows"], reserved_rows
                )
            )

        expected_bindings = _global_bindings(inputs, joined) + _persona_origin_bindings(
            joined
        )
        expected_binding_order = [row["name"] for row in expected_bindings]
        if target["input_binding_order"] != expected_binding_order:
            _fail(
                "persona dependency binding order differs at "
                + _first_difference(
                    target["input_binding_order"], expected_binding_order
                )
            )
        if not _strict_equal(target["input_bindings"], expected_bindings):
            _fail(
                "persona dependency bindings differ from authenticated owners at "
                + _first_difference(
                    target["input_bindings"], expected_bindings
                )
            )

        expected_event_rows = _expected_event_rows(
            inputs, persona_id, primary_rows, companion_rows
        )
        expected_persona = _expected_persona_value(
            inputs,
            persona_id,
            joined,
            primary_rows,
            companion_rows,
            reserved_rows,
            witness_rows,
            expected_event_rows,
        )
        if not _strict_equal(target, expected_persona):
            _fail(
                "persona differs from complete independent reconstruction at "
                + _first_difference(target, expected_persona)
            )
        if event_body_provider is None:
            event_rows = expected_event_rows
        else:
            event_rows = _event_rows_from_provider(
                persona_id, target["event_receipt"], event_body_provider
            )
            if not _strict_equal(event_rows, expected_event_rows):
                _fail("event body differs from independent lifecycle expansion")
        event_source_intents = {
            row["source_intent_key"]
            for row in event_rows
            if set(row) == SOURCE_EVENT_ROW_FIELDS
        }
        event_created_intents = {
            row["after_source_intent_key"]
            for row in event_rows
            if set(row) == SOURCE_EVENT_ROW_FIELDS
            and row["after_source_intent_key"]
            == _created_source_intent_key(
                persona_id, row["event_sequence_ordinal"]
            )
        }
        if not event_source_intents <= (
            selection["lifecycle_intent_keys"] | event_created_intents
        ):
            _fail(
                "source event references neither a matched nor an earlier "
                "event-created lifecycle intent"
            )
        positive_rows = [
            row
            for row in witness_rows
            if row["classification"] == "searchable-positive"
        ]
        if any(
            row["query_anchor_ref"] != row["intent_key"]
            or row["query_anchor_ref"] not in selection["lifecycle_intent_keys"]
            for row in positive_rows
        ):
            _fail("searchable witness query anchor escaped exact lifecycle refs")
        if any(
            "query_anchor_ref" in row
            for row in witness_rows
            if row["classification"] != "searchable-positive"
        ):
            _fail("negative format witness gained a query-answer anchor")
    finally:
        postflight_error = None
        if originals is not None:
            try:
                _reauth_inputs(originals, canonicalizers, opening_inputs)
            except Exception as error:
                postflight_error = error
        try:
            current = _canonical(
                value,
                label="source-matched lifecycle persona",
                maximum=MAX_PERSONA_BYTES,
            )
            if not hmac.compare_digest(opening_target, current):
                _fail("caller-owned persona mutated during provider callbacks")
        except Exception as error:
            if postflight_error is None:
                postflight_error = error
        if postflight_error is not None:
            raise postflight_error
    return True


def validate_source_matched_lifecycle_suite_descriptor(
    value,
    *,
    persona_provider=None,
    event_body_provider=None,
    coverage_value=None,
    use_case_value=None,
    variant_value=None,
    source_suite_value=None,
    reservation_suite_value=None,
    semantic_suite_value=None,
    inventory_profile_value=None,
    assignment_origin_provider=None,
):
    """Reconstruct and validate all twenty persona owners and suite closure."""

    if type(value) is not dict:
        _fail("source-matched lifecycle suite must be an object")
    target, opening_target = _opening_snapshot(
        value,
        label="source-matched lifecycle suite",
        maximum=MAX_SUITE_BYTES,
    )
    if (
        set(target) != SUITE_TOP_LEVEL_FIELDS
        or target.get("artifact_kind") != SUITE_KIND
        or target.get("artifact_schema") != SUITE_SCHEMA
        or target.get("artifact_schema_version") != ARTIFACT_SCHEMA_VERSION
        or target.get("fixture_id") != envelope.FIXTURE_ID
        or target.get("fixture_schema_version")
        != envelope.FIXTURE_SCHEMA_VERSION
    ):
        _fail("source-matched lifecycle suite envelope drifted")
    _require_all_false_authority(
        target,
        label="source-matched lifecycle suite",
        exact_fields=AUTHORITY_FIELDS,
    )
    _strict_json_domain(target)
    _reject_forbidden_keys(target)
    if persona_provider is not None and not callable(persona_provider):
        _fail("persona provider must be callable")
    if event_body_provider is not None and not callable(event_body_provider):
        _fail("event body provider must be callable")

    overrides = {
        "coverage": coverage_value,
        "use_cases": use_case_value,
        "variants": variant_value,
        "source_suite": source_suite_value,
        "reservation_suite": reservation_suite_value,
        "semantic_suite": semantic_suite_value,
        "inventory_profiles": inventory_profile_value,
    }
    originals = canonicalizers = opening_inputs = None
    provider_opening = {}
    try:
        originals, canonicalizers, opening_inputs, inputs = _resolve_inputs(
            overrides
        )
        reconstructed = {
            persona_id: _reconstruct_expected_persona(
                inputs,
                persona_id,
                assignment_origin_provider=assignment_origin_provider,
            )
            for persona_id in PERSONA_IDS
        }
        expected = _expected_suite_value(inputs, reconstructed)
        if not _strict_equal(target, expected):
            _fail(
                "suite differs from complete independent reconstruction at "
                + _first_difference(target, expected)
            )
        if (
            type(EXPECTED_SUITE_CANONICAL_BYTES) is not int
            or type(EXPECTED_SUITE_CANONICAL_BYTES) is bool
            or EXPECTED_SUITE_CANONICAL_BYTES < 1
            or type(EXPECTED_SUITE_SHA256) is not str
            or len(EXPECTED_SUITE_SHA256) != 64
            or len(opening_target) != EXPECTED_SUITE_CANONICAL_BYTES
            or not hmac.compare_digest(
                hashlib.sha256(opening_target).hexdigest(),
                EXPECTED_SUITE_SHA256,
            )
        ):
            _fail("suite differs from its final independently accepted pin")

        if persona_provider is not None:
            for persona_id in PERSONA_IDS:
                try:
                    supplied = copy.deepcopy(persona_provider(persona_id))
                except Exception as error:
                    raise PersonaV2SourceMatchedLifecycleInventoryValidationError(
                        "persona provider failed"
                    ) from error
                raw = _canonical(
                    supplied,
                    label="provided source-matched lifecycle persona",
                    maximum=MAX_PERSONA_BYTES,
                )
                provider_opening[persona_id] = raw
                if not _strict_equal(
                    supplied, reconstructed[persona_id]["persona"]
                ):
                    _fail("persona provider differs from independent reconstruction")
        if event_body_provider is not None:
            for persona_id in PERSONA_IDS:
                rows = _event_rows_from_provider(
                    persona_id,
                    reconstructed[persona_id]["persona"]["event_receipt"],
                    event_body_provider,
                )
                if not _strict_equal(
                    rows, reconstructed[persona_id]["event_rows"]
                ):
                    _fail("suite event provider differs from independent expansion")
    finally:
        postflight_error = None
        if persona_provider is not None and provider_opening:
            try:
                for persona_id in provider_opening:
                    closing = persona_provider(persona_id)
                    closing_raw = _canonical(
                        closing,
                        label="postflight source-matched lifecycle persona",
                        maximum=MAX_PERSONA_BYTES,
                    )
                    if not hmac.compare_digest(
                        provider_opening[persona_id], closing_raw
                    ):
                        _fail("persona provider changed during suite validation")
            except Exception as error:
                postflight_error = error
        if originals is not None:
            try:
                _reauth_inputs(originals, canonicalizers, opening_inputs)
            except Exception as error:
                if postflight_error is None:
                    postflight_error = error
        try:
            current = _canonical(
                value,
                label="source-matched lifecycle suite",
                maximum=MAX_SUITE_BYTES,
            )
            if not hmac.compare_digest(opening_target, current):
                _fail("caller-owned suite mutated during provider callbacks")
        except Exception as error:
            if postflight_error is None:
                postflight_error = error
        if postflight_error is not None:
            raise postflight_error
    return True


def validate_source_matched_lifecycle_content_projection(
    persona_id,
    value,
    *,
    coverage_value=None,
    use_case_value=None,
    variant_value=None,
    source_suite_value=None,
    reservation_suite_value=None,
    semantic_suite_value=None,
    inventory_profile_value=None,
    assignment_origin_provider=None,
):
    """Validate the nine-field content-only derivation boundary."""

    _require_persona_id(persona_id)
    if type(value) is not dict:
        _fail("source-matched lifecycle content projection must be an object")
    target, opening_target = _opening_snapshot(
        value,
        label="source-matched lifecycle content projection",
        maximum=MAX_CONTENT_PROJECTION_BYTES,
    )
    if (
        set(target) != PROJECTION_TOP_LEVEL_FIELDS
        or target.get("artifact_kind") != PROJECTION_KIND
        or target.get("artifact_schema") != PROJECTION_SCHEMA
        or target.get("artifact_schema_version") != ARTIFACT_SCHEMA_VERSION
        or target.get("fixture_id") != envelope.FIXTURE_ID
        or target.get("fixture_schema_version")
        != envelope.FIXTURE_SCHEMA_VERSION
        or target.get("persona_id") != persona_id
    ):
        _fail("content projection envelope or nine-field boundary drifted")
    _strict_json_domain(target)
    _reject_forbidden_keys(target)
    if set(target) & {
        "authority",
        "completion_claims",
        "g0_contract_frozen",
        "input_bindings",
        "remaining_blockers",
        "sha256",
    }:
        _fail("content projection leaked manifest/runtime metadata")

    overrides = {
        "coverage": coverage_value,
        "use_cases": use_case_value,
        "variants": variant_value,
        "source_suite": source_suite_value,
        "reservation_suite": reservation_suite_value,
        "semantic_suite": semantic_suite_value,
        "inventory_profiles": inventory_profile_value,
    }
    originals = canonicalizers = opening_inputs = None
    try:
        originals, canonicalizers, opening_inputs, inputs = _resolve_inputs(
            overrides
        )
        reconstructed = _reconstruct_expected_persona(
            inputs,
            persona_id,
            assignment_origin_provider=assignment_origin_provider,
        )
        expected = _expected_content_projection(
            persona_id,
            reconstructed["persona"],
            reconstructed["event_rows"],
        )
        if not _strict_equal(target, expected):
            _fail(
                "content projection differs from independent normalization at "
                + _first_difference(target, expected)
            )
    finally:
        postflight_error = None
        if originals is not None:
            try:
                _reauth_inputs(originals, canonicalizers, opening_inputs)
            except Exception as error:
                postflight_error = error
        try:
            current = _canonical(
                value,
                label="source-matched lifecycle content projection",
                maximum=MAX_CONTENT_PROJECTION_BYTES,
            )
            if not hmac.compare_digest(opening_target, current):
                _fail("caller-owned content projection mutated during validation")
        except Exception as error:
            if postflight_error is None:
                postflight_error = error
        if postflight_error is not None:
            raise postflight_error
    return True


__all__ = [
    "CONTENT_SCOPE_EVENT_ROW_FIELDS",
    "CONTENT_SECTIONS_FIELDS",
    "CONTENT_SOURCE_EVENT_ROW_FIELDS",
    "EXPECTED_DEPENDENCY_PINS",
    "EXPECTED_SUITE_CANONICAL_BYTES",
    "EXPECTED_SUITE_SHA256",
    "MAX_CONTENT_PROJECTION_BYTES",
    "MAX_EVENT_BODY_BYTES",
    "MAX_EVENT_ROW_BYTES_INCLUDING_LF",
    "MAX_PERSONA_BYTES",
    "MAX_SUITE_BYTES",
    "PersonaV2SourceMatchedLifecycleInventoryValidationError",
    "validate_source_matched_lifecycle_content_projection",
    "validate_source_matched_lifecycle_persona",
    "validate_source_matched_lifecycle_suite_descriptor",
]
