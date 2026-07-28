"""Pre-solve source-matched lifecycle inventory for persona-PC fidelity v2.

This artifact binds the anonymous lifecycle coverage requirements to concrete
``pilot`` source intents before scope/quota solving.  The full profile reuses
the exact pilot intent selection; no full-residual source is selected here.
Expanded lifecycle events are deterministic verification views whose receipt,
not body, is persisted.

The package remains deliberately non-authorizing: it owns neither a solved
scope/path, chunk quota, final source/materialization/event identifier, query
or oracle body, filesystem write, history execution, nor G0 completion.
"""

from __future__ import annotations

import copy
import functools
import hashlib
import hmac

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_lifecycle_coverage_catalog as lifecycle_coverage
    from . import persona_v2_overlay_reservation_layout as reservation_layout
    from . import persona_v2_primary_use_case_catalog as use_cases
    from . import persona_v2_source_inventory_package as source_package
    from . import persona_v2_source_inventory_profile as source_profiles
    from . import persona_v2_source_parameter_assignment_package as assignments
    from . import persona_v2_source_semantic_membership_package as semantics
    from . import persona_v2_variant_catalog as variants
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_lifecycle_coverage_catalog as lifecycle_coverage
    import persona_v2_overlay_reservation_layout as reservation_layout
    import persona_v2_primary_use_case_catalog as use_cases
    import persona_v2_source_inventory_package as source_package
    import persona_v2_source_inventory_profile as source_profiles
    import persona_v2_source_parameter_assignment_package as assignments
    import persona_v2_source_semantic_membership_package as semantics
    import persona_v2_variant_catalog as variants


PERSONA_SCHEMA = "kio.persona.pc-source-matched-lifecycle-persona/v1"
PERSONA_KIND = "persona-pc-v2-source-matched-lifecycle-persona"
SUITE_SCHEMA = "kio.persona.pc-source-matched-lifecycle-suite/v1"
SUITE_KIND = "persona-pc-v2-source-matched-lifecycle-suite"
PROJECTION_SCHEMA = "kio.persona.pc-source-matched-lifecycle-content-projection/v1"
PROJECTION_KIND = "persona-pc-v2-source-matched-lifecycle-content-projection"
ARTIFACT_SCHEMA_VERSION = 1

MAX_PERSONA_BYTES = 512 * 1024
MAX_SUITE_BYTES = 512 * 1024
MAX_CONTENT_PROJECTION_BYTES = 384 * 1024
TARGET_CONTENT_PROJECTION_BYTES = 256 * 1024
MAX_EVENT_BODY_BYTES = 4 * 1024 * 1024
MAX_EVENT_ROW_BYTES_INCLUDING_LF = 1_024

EXPECTED_PRIMARY_MATCHES_PER_PERSONA = 105
EXPECTED_COMPANION_MATCHES_PER_PERSONA = 10
EXPECTED_LIFECYCLE_SOURCE_REFS_PER_PERSONA = 115
EXPECTED_EVENT_BASELINE_PER_PERSONA = 379
EXPECTED_EVENT_SUITE_COUNT = 7_630
EXPECTED_FORMAT_WITNESS_COUNT = 93
EXPECTED_SEARCHABLE_WITNESS_COUNT = 52
EXPECTED_PENDING_WITNESS_COUNT = 33
EXPECTED_RAW_ONLY_WITNESS_COUNT = 8

ASSIGNMENT_SUITE_CANONICAL_BYTES = 72_535
ASSIGNMENT_SUITE_SHA256 = (
    "ed95d7875cb961d4fa054f6fa8a8a281cf6906724bc5f2524d9d046b2c3e8f1a"
)
EXPECTED_SUITE_CANONICAL_BYTES = 14_605
EXPECTED_SUITE_SHA256 = (
    "c4508ed61c88db80b003e9ce3b7c35ea153776442bd3224964897400633dd2c8"
)

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

DERIVE_DIAGNOSTIC_PERSONAS = frozenset({"p01", "p04", "p06", "p09"})
DUPLICATE_DIAGNOSTIC_PERSONAS = frozenset(
    {"p04", "p05", "p08", "p10", "p14", "p19"}
)

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
        "row_kind",
        "scenario_visibility_rule",
        "scope_relation_rule_key",
        "source_intent_key",
        "symbol_domain_ref",
        "variant_id",
        "wave",
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


class PersonaV2SourceMatchedLifecycleInventoryError(ValueError):
    """Raised when source matching or lifecycle inventory construction drifts."""


def _fail(message):
    raise PersonaV2SourceMatchedLifecycleInventoryError(message)


def _negative_authority():
    return {field: False for field in sorted(AUTHORITY_FIELDS)}


def _require_persona_id(persona_id):
    if type(persona_id) is not str or persona_id not in envelope.PERSONA_IDS:
        _fail(f"unknown persona ID: {persona_id!r}")


def _ascii(value):
    if type(value) is not str:
        _fail("canonical key must be a string")
    try:
        return value.encode("ascii", "strict")
    except UnicodeEncodeError:
        _fail("canonical keys must be ASCII")


def _domain_key(domain, intent_key):
    raw = b"kio-lifecycle-v1/" + _ascii(domain) + b"/" + _ascii(intent_key)
    return hashlib.sha256(raw).digest(), _ascii(intent_key)


def _canonical_fragment(value, *, label, max_bytes):
    try:
        return artifact_common.canonical_json_bytes(
            value, label=label, max_bytes=max_bytes
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SourceMatchedLifecycleInventoryError(str(error)) from None


def _jsonl_row_bytes(row):
    raw = _canonical_fragment(
        row,
        label="persona v2 source-matched lifecycle event row",
        max_bytes=MAX_EVENT_ROW_BYTES_INCLUDING_LF - 1,
    )
    if len(raw) + 1 > MAX_EVENT_ROW_BYTES_INCLUDING_LF:
        _fail("expanded lifecycle event row exceeds its LF-inclusive cap")
    return raw + b"\n"


def _reject_prohibited_keys(value, *, path="$"):
    if type(value) is dict:
        for key, child in value.items():
            if type(key) is not str:
                _fail(f"non-string key at {path}")
            if key in FORBIDDEN_EXACT_KEYS:
                _fail(f"prohibited downstream key at {path}.{key}")
            _reject_prohibited_keys(child, path=f"{path}.{key}")
    elif type(value) is list:
        for index, child in enumerate(value):
            _reject_prohibited_keys(child, path=f"{path}[{index}]")


def _binding(name, role, value, *, validate, canonical, coordinates=()):
    validate(value)
    if value.get("g0_contract_frozen") is not False or any(
        value.get("authority", {}).values()
    ):
        _fail(f"{name} gained execution or G0 authority")
    raw = canonical(value)
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


def _assignment_suite_pin_binding():
    return {
        "artifact_kind": assignments.SUITE_KIND,
        "artifact_schema": assignments.SUITE_SCHEMA,
        "artifact_schema_version": assignments.ARTIFACT_SCHEMA_VERSION,
        "canonical_bytes": ASSIGNMENT_SUITE_CANONICAL_BYTES,
        "dependency_role": "frozen-all-source-parameter-assignment-suite-pin",
        "name": "persona-v2-source-instance-parameter-assignment-suite",
        "sha256": ASSIGNMENT_SUITE_SHA256,
    }


@functools.lru_cache(maxsize=1)
def _cached_global_inputs():
    coverage_value = lifecycle_coverage.build_lifecycle_coverage_catalog()
    use_case_value = use_cases.build_primary_use_case_catalog()
    variant_value = variants.build_variant_catalog()
    profile_value = source_profiles.build_source_inventory_profile_catalog()
    cell_value = assignments.build_source_parameter_cell_catalog()
    bindings = [
        _binding(
            "persona-v2-lifecycle-coverage-catalog",
            "anonymous-capability-event-algebra-and-receipt-demand-owner",
            coverage_value,
            validate=lifecycle_coverage.validate_lifecycle_coverage_catalog,
            canonical=lifecycle_coverage.canonical_json_bytes,
        ),
        _binding(
            "persona-v2-primary-use-case-catalog",
            "persona-required-family-and-scenario-owner",
            use_case_value,
            validate=use_cases.validate_primary_use_case_catalog,
            canonical=use_cases.canonical_json_bytes,
        ),
        _binding(
            "persona-v2-variant-catalog",
            "family-gate-role-and-offline-disposition-owner",
            variant_value,
            validate=variants.validate_variant_catalog,
            canonical=variants.canonical_json_bytes,
        ),
        _binding(
            "persona-v2-source-inventory-profile-catalog",
            "source-profile-to-variant-family-and-gate-role-owner",
            profile_value,
            validate=source_profiles.validate_source_inventory_profile_catalog,
            canonical=source_profiles.canonical_json_bytes,
        ),
        _binding(
            "persona-v2-source-parameter-cell-catalog",
            "selected-source-parameter-cell-and-target-byte-owner",
            cell_value,
            validate=assignments.validate_source_parameter_cell_catalog,
            canonical=assignments.canonical_json_bytes,
        ),
        _assignment_suite_pin_binding(),
    ]
    return {
        "bindings": bindings,
        "cell_catalog": cell_value,
        "coverage": coverage_value,
        "profiles": profile_value,
        "use_cases": use_case_value,
        "variants": variant_value,
    }


def _global_fingerprint(inputs):
    if type(inputs) is not dict or set(inputs) != {
        "bindings",
        "cell_catalog",
        "coverage",
        "profiles",
        "use_cases",
        "variants",
    }:
        _fail("global dependency snapshot schema drifted")
    return (
        lifecycle_coverage.canonical_json_bytes(inputs["coverage"]),
        use_cases.canonical_json_bytes(inputs["use_cases"]),
        variants.canonical_json_bytes(inputs["variants"]),
        source_profiles.canonical_json_bytes(inputs["profiles"]),
        assignments.canonical_json_bytes(inputs["cell_catalog"]),
        _canonical_fragment(
            inputs["bindings"],
            label="source-matched lifecycle dependency bindings",
            max_bytes=128 * 1024,
        ),
    )


def _detached_global_inputs(dependency_observer=None):
    cached = _cached_global_inputs()
    opening = _global_fingerprint(cached)
    detached = copy.deepcopy(cached)
    if dependency_observer is not None:
        dependency_observer(cached)
    if _global_fingerprint(cached) != opening:
        _fail("global dependency changed during snapshot")
    return detached


def _default_source_origin_provider(persona_id):
    return source_package.build_source_intent_origin_manifest(persona_id, "pilot")


def _default_reservation_origin_provider(persona_id):
    return reservation_layout.build_overlay_reservation_origin(persona_id, "pilot")


def _default_semantic_origin_provider(persona_id):
    return semantics.build_source_semantic_membership_origin_manifest(
        persona_id, "pilot"
    )


@functools.lru_cache(maxsize=20)
def _cached_default_assignment_origin_payload(persona_id):
    """Return one authenticated manifest plus its nonpersisted expanded rows.

    The upstream combined builder is used so manifest and expanded mapping are
    produced from one authenticated snapshot rather than triggering two cold
    origin constructions.  This private bridge is intentionally isolated here;
    the returned manifest and every row are rechecked against its receipts.
    """

    manifest, state = assignments._default_origin_build(  # noqa: SLF001
        persona_id, "pilot", return_state=True
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


def _default_assignment_origin_provider(persona_id):
    return copy.deepcopy(_cached_default_assignment_origin_payload(persona_id))


def _origin_binding(name, role, value, *, canonical, coordinates=("persona_id", "origin")):
    raw = canonical(value)
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


def _assignment_expanded_row_bytes(intent_key, parameter_cell_key):
    raw = _canonical_fragment(
        {"intent_key": intent_key, "parameter_cell_key": parameter_cell_key},
        label="authenticated source parameter expanded row",
        max_bytes=assignments.MAX_EXPANDED_ROW_BYTES_INCLUDING_LF - 1,
    )
    return raw + b"\n"


def _authenticate_assignment_payload(persona_id, payload, source_rows):
    if type(payload) is not dict or set(payload) != {"expanded_rows", "manifest"}:
        _fail("assignment origin provider returned an unexpected schema")
    manifest = payload["manifest"]
    if (
        type(manifest) is not dict
        or manifest.get("persona_id") != persona_id
        or manifest.get("origin") != "pilot"
        or manifest.get("artifact_schema") != assignments.ORIGIN_MANIFEST_SCHEMA
    ):
        _fail("assignment origin provider escaped the requested coordinate")
    if manifest.get("g0_contract_frozen") is not False or any(
        manifest.get("authority", {}).values()
    ):
        _fail("assignment origin gained authority")
    # Canonicalization is a bounded schema dispatch check.  The default provider
    # already authenticates every source/concrete dependency internally; custom
    # providers must additionally equal exact upstream regeneration.
    assignments.canonical_json_bytes(manifest)
    rows = payload["expanded_rows"]
    if type(rows) is not list or any(
        type(row) is not dict
        or set(row) != {"intent_key", "parameter_cell_key", "shard_ordinal"}
        for row in rows
    ):
        _fail("assignment expanded provider rows have an unexpected schema")
    source_order = [row["intent_key"] for row in source_rows]
    if [row["intent_key"] for row in rows] != source_order:
        _fail("assignment expanded rows differ from authenticated source order")
    if len(set(source_order)) != len(source_order):
        _fail("authenticated source order contains duplicate intents")
    receipts = manifest.get("expanded_view_receipts")
    if type(receipts) is not list or not receipts:
        _fail("assignment manifest lacks expanded-view receipts")
    by_shard = {}
    for row in rows:
        by_shard.setdefault(row["shard_ordinal"], []).append(row)
    if [row["shard_ordinal"] for row in receipts] != sorted(by_shard):
        _fail("assignment receipt shard order drifted")
    for receipt in receipts:
        selected = by_shard[receipt["shard_ordinal"]]
        parts = [
            _assignment_expanded_row_bytes(
                row["intent_key"], row["parameter_cell_key"]
            )
            for row in selected
        ]
        body = b"".join(parts)
        if (
            receipt["row_count"] != len(selected)
            or receipt["first_intent_key"] != selected[0]["intent_key"]
            or receipt["last_intent_key"] != selected[-1]["intent_key"]
            or receipt["expanded_body_bytes"] != len(body)
            or receipt["maximum_row_bytes_including_lf"] != max(map(len, parts))
            or not hmac.compare_digest(
                receipt["expanded_body_sha256"], hashlib.sha256(body).hexdigest()
            )
        ):
            _fail("assignment expanded rows differ from their authenticated receipt")
    return manifest, {
        row["intent_key"]: row["parameter_cell_key"] for row in rows
    }


def _load_persona_inputs(
    persona_id,
    *,
    source_origin_provider,
    reservation_origin_provider,
    semantic_origin_provider,
    assignment_origin_provider,
):
    try:
        source_origin = copy.deepcopy(source_origin_provider(persona_id))
        reservation_origin = copy.deepcopy(reservation_origin_provider(persona_id))
        semantic_origin = copy.deepcopy(semantic_origin_provider(persona_id))
        assignment_payload = copy.deepcopy(assignment_origin_provider(persona_id))
        source_package.validate_source_intent_origin_manifest(
            persona_id, "pilot", source_origin
        )
        reservation_layout.validate_overlay_reservation_origin(
            persona_id, "pilot", reservation_origin
        )
        semantics.validate_source_semantic_membership_origin_manifest(
            persona_id, "pilot", semantic_origin
        )
    except Exception as error:
        raise PersonaV2SourceMatchedLifecycleInventoryError(
            "persona origin provider failed authentication"
        ) from error
    if any(
        value.get("persona_id") != persona_id or value.get("origin") != "pilot"
        for value in (source_origin, reservation_origin, semantic_origin)
    ):
        _fail("persona origin provider escaped the requested coordinate")

    source_rows = []
    for descriptor in source_origin["shard_descriptors"]:
        source_rows.extend(
            source_package.iter_source_intent_rows(
                persona_id, "pilot", descriptor["shard_ordinal"]
            )
        )
    if len(source_rows) != source_origin["summary"]["source_intent_count"]:
        _fail("source origin row count drifted")
    assignment_origin, parameter_by_intent = _authenticate_assignment_payload(
        persona_id, assignment_payload, source_rows
    )

    context_by_intent = {}
    membership_by_intent = {}
    for descriptor in source_origin["shard_descriptors"]:
        ordinal = descriptor["shard_ordinal"]
        for row in semantics.iter_expanded_content_context_rows(
            persona_id, "pilot", ordinal
        ):
            context_by_intent[row["intent_key"]] = row
        for row in semantics.iter_expanded_fact_membership_rows(
            persona_id, "pilot", ordinal
        ):
            membership_by_intent[row["intent_key"]] = row
    source_keys = {row["intent_key"] for row in source_rows}
    if (
        set(context_by_intent) != source_keys
        or set(membership_by_intent) != source_keys
        or set(parameter_by_intent) != source_keys
    ):
        _fail("source, semantic, and assignment pilot domains do not close")

    bindings = [
        _origin_binding(
            "persona-v2-source-inventory-origin-manifest",
            "authenticated-pilot-source-intent-owner",
            source_origin,
            canonical=source_package.canonical_json_bytes,
        ),
        _origin_binding(
            "persona-v2-overlay-reservation-origin",
            "semantic-anchor-and-overlay-unreserved-domain-owner",
            reservation_origin,
            canonical=reservation_layout.canonical_json_bytes,
        ),
        _origin_binding(
            "persona-v2-source-semantic-membership-origin-manifest",
            "base-topic-language-fact-and-logical-identity-owner",
            semantic_origin,
            canonical=semantics.canonical_json_bytes,
        ),
        _origin_binding(
            "persona-v2-source-instance-parameter-assignment-origin-manifest",
            "authenticated-pilot-intent-to-parameter-cell-owner",
            assignment_origin,
            canonical=assignments.canonical_json_bytes,
        ),
    ]
    return {
        "assignment_origin": assignment_origin,
        "bindings": bindings,
        "context_by_intent": context_by_intent,
        "membership_by_intent": membership_by_intent,
        "parameter_by_intent": parameter_by_intent,
        "reservation_origin": reservation_origin,
        "semantic_origin": semantic_origin,
        "source_by_intent": {row["intent_key"]: row for row in source_rows},
        "source_origin": source_origin,
    }


def _persona_rows(global_inputs, persona_id):
    capabilities = [
        row
        for row in global_inputs["coverage"]["primary_capabilities"]
        if row["persona_id"] == persona_id
    ]
    companions = [
        row
        for row in global_inputs["coverage"]["cross_format_companion_requirements"]
        if row["persona_id"] == persona_id
    ]
    use_case_matches = [
        row
        for row in global_inputs["use_cases"]["primary_use_cases"]
        if row["persona_id"] == persona_id
    ]
    if (
        len(capabilities) != EXPECTED_PRIMARY_MATCHES_PER_PERSONA
        or len(companions) != EXPECTED_COMPANION_MATCHES_PER_PERSONA
        or len(use_case_matches) != 1
    ):
        _fail("persona coverage/use-case cardinality drifted")
    return capabilities, companions, use_case_matches[0]


def _source_indexes(global_inputs, persona_inputs):
    profile_by_id = {
        row["source_profile_id"]: row
        for row in global_inputs["profiles"]["source_profile_rows"]
    }
    cell_by_key = {
        row["parameter_cell_key"]: row
        for row in global_inputs["cell_catalog"]["parameter_cells"]
    }
    result = {}
    for intent_key, source in persona_inputs["source_by_intent"].items():
        profile = profile_by_id.get(source["source_profile_id"])
        context = persona_inputs["context_by_intent"].get(intent_key)
        membership = persona_inputs["membership_by_intent"].get(intent_key)
        parameter_cell_key = persona_inputs["parameter_by_intent"].get(intent_key)
        cell = cell_by_key.get(parameter_cell_key)
        if (
            profile is None
            or context is None
            or membership is None
            or cell is None
            or cell["variant_id"] != profile["variant_id"]
        ):
            _fail("selected source joins do not resolve exactly")
        result[intent_key] = {
            "base_fact_profile_id": membership["fact_profile_id"],
            "base_language": context["language"],
            "base_logical_document_key": membership["logical_document_key"],
            "base_logical_revision_key": membership["logical_revision_key"],
            "base_topic_id": context["topic_id"],
            "family": profile["family"],
            "gate_role": profile["gate_role"],
            "intent_key": intent_key,
            "offline_disposition": profile["expected_offline_disposition"],
            "parameter_cell_key": parameter_cell_key,
            "source_profile_id": source["source_profile_id"],
            "target_bytes": cell["target_bytes"],
            "variant_id": profile["variant_id"],
        }
    return result


def _reservation_domains(persona_inputs, source_info):
    reservation = persona_inputs["reservation_origin"]
    anchor_by_intent = {
        row["intent_key"]: row for row in reservation["semantic_anchor_slots"]
    }
    overlay_reserved = set()
    for row in reservation["reservation_rows"]:
        if row["row_kind"] == "content-relation-reservation":
            overlay_reserved.update(
                (row["anchor_intent_key"], row["derivative_intent_key"])
            )
        elif row["row_kind"] == "attachment-membership-reservation":
            overlay_reserved.update(
                (row["host_intent_key"], row["standalone_member_intent_key"])
            )
        else:
            _fail("reservation contains an unknown row kind")
    anchor_keys = set(anchor_by_intent)
    if anchor_keys & overlay_reserved:
        _fail("semantic anchors overlap relation or attachment reservations")
    unreserved = set(source_info) - anchor_keys - overlay_reserved
    if len(anchor_keys) != 105:
        _fail("pilot semantic anchor count drifted")
    return anchor_by_intent, overlay_reserved, unreserved


def _cross_format_pairs(anchor_by_intent, unreserved, source_info):
    left = sorted(anchor_by_intent, key=lambda key: _domain_key("cross-anchor", key))
    right = sorted(
        (
            key
            for key in unreserved
            if source_info[key]["gate_role"] == "contract_contributor"
        ),
        key=lambda key: _domain_key("cross-candidate", key),
    )
    right_to_left = {}
    left_to_right = {}

    def eligible(anchor_key, candidate_key):
        anchor = source_info[anchor_key]
        candidate = source_info[candidate_key]
        return (
            anchor["base_topic_id"] == candidate["base_topic_id"]
            and anchor["base_language"] == candidate["base_language"]
            and anchor["family"] != candidate["family"]
        )

    def augment(anchor_key, seen_candidates):
        for candidate_key in right:
            if candidate_key in seen_candidates or not eligible(
                anchor_key, candidate_key
            ):
                continue
            seen_candidates.add(candidate_key)
            previous = right_to_left.get(candidate_key)
            if previous is None or augment(previous, seen_candidates):
                right_to_left[candidate_key] = anchor_key
                left_to_right[anchor_key] = candidate_key
                return True
        return False

    successful = 0
    for anchor_key in left:
        if augment(anchor_key, set()):
            successful += 1
        if successful == EXPECTED_COMPANION_MATCHES_PER_PERSONA:
            break
    if len(left_to_right) != EXPECTED_COMPANION_MATCHES_PER_PERSONA:
        _fail("cross-format bipartite match did not reach exact cardinality ten")
    return sorted(
        left_to_right.items(), key=lambda row: _domain_key("cross-anchor", row[0])
    )


def _primary_row(capability, info, *, semantic_anchor_slot_ordinal=None):
    value = {
        "allocation_class": capability["allocation_class"],
        "base_fact_profile_id": info["base_fact_profile_id"],
        "base_language": info["base_language"],
        "base_logical_document_key": info["base_logical_document_key"],
        "base_logical_revision_key": info["base_logical_revision_key"],
        "base_topic_id": info["base_topic_id"],
        "capability_class_key": capability["capability_class_key"],
        "capability_key": capability["capability_key"],
        "family": info["family"],
        "gate_role": info["gate_role"],
        "intent_key": info["intent_key"],
        "lifecycle_logical_document_slot_key": capability[
            "logical_document_slot_key"
        ],
        "origin": "pilot",
        "parameter_cell_key": info["parameter_cell_key"],
        "reservation_status": (
            "selected-pilot-semantic-anchor"
            if semantic_anchor_slot_ordinal is not None
            else "selected-pilot-overlay-unreserved-incidental"
        ),
        "source_profile_id": info["source_profile_id"],
        "variant_id": info["variant_id"],
    }
    if semantic_anchor_slot_ordinal is not None:
        value["semantic_anchor_slot_ordinal"] = semantic_anchor_slot_ordinal
        expected = CONTRIBUTOR_PRIMARY_MATCH_FIELDS
    else:
        expected = INCIDENTAL_PRIMARY_MATCH_FIELDS
    if set(value) != expected:
        _fail("primary source match row schema drifted")
    return value


def _companion_row(requirement, info):
    value = {
        "base_fact_profile_id": info["base_fact_profile_id"],
        "base_language": info["base_language"],
        "base_logical_document_key": info["base_logical_document_key"],
        "base_logical_revision_key": info["base_logical_revision_key"],
        "base_topic_id": info["base_topic_id"],
        "companion_requirement_key": requirement["companion_requirement_key"],
        "effective_membership_rule": (
            "replace-with-primary-lifecycle-logical-document-fact-revision-chain"
        ),
        "family": info["family"],
        "gate_role": info["gate_role"],
        "intent_key": info["intent_key"],
        "origin": "pilot",
        "parameter_cell_key": info["parameter_cell_key"],
        "primary_capability_key": requirement["primary_capability_key"],
        "rendition_group_key": requirement["rendition_group_key"],
        "reservation_status": "selected-pilot-overlay-unreserved-companion",
        "source_profile_id": info["source_profile_id"],
        "variant_id": info["variant_id"],
    }
    if set(value) != COMPANION_MATCH_FIELDS:
        _fail("companion source match row schema drifted")
    return value


def _select_source_matches(global_inputs, persona_inputs, persona_id):
    capabilities, requirements, use_case = _persona_rows(global_inputs, persona_id)
    source_info = _source_indexes(global_inputs, persona_inputs)
    anchor_by_intent, _overlay_reserved, unreserved = _reservation_domains(
        persona_inputs, source_info
    )
    cross_pairs = _cross_format_pairs(anchor_by_intent, unreserved, source_info)
    cross_capabilities = sorted(
        (row for row in capabilities if row["cross_format_companion_required"]),
        key=lambda row: _ascii(row["capability_key"]),
    )
    requirements = sorted(requirements, key=lambda row: _ascii(row["primary_capability_key"]))
    requirement_by_capability = {
        row["primary_capability_key"]: row for row in requirements
    }
    if [row["capability_key"] for row in cross_capabilities] != [
        row["primary_capability_key"] for row in requirements
    ]:
        _fail("cross-format capabilities and companion requirements disagree")

    primary_by_capability = {}
    companion_rows = []
    used = set()
    for capability, (anchor_key, candidate_key) in zip(
        cross_capabilities, cross_pairs, strict=True
    ):
        anchor = anchor_by_intent[anchor_key]
        primary_by_capability[capability["capability_key"]] = _primary_row(
            capability,
            source_info[anchor_key],
            semantic_anchor_slot_ordinal=anchor["semantic_anchor_slot_ordinal"],
        )
        companion_rows.append(
            _companion_row(
                requirement_by_capability[capability["capability_key"]],
                source_info[candidate_key],
            )
        )
        used.update((anchor_key, candidate_key))

    remaining_contributor_capabilities = sorted(
        (
            row
            for row in capabilities
            if row["gate_role_requirement"] == "contract_contributor"
            and row["capability_key"] not in primary_by_capability
        ),
        key=lambda row: _ascii(row["capability_key"]),
    )
    remaining_anchors = sorted(
        (key for key in anchor_by_intent if key not in used),
        key=lambda key: _domain_key("primary-anchor", key),
    )
    selected_remaining = remaining_anchors[: len(remaining_contributor_capabilities)]
    for capability, anchor_key in zip(
        remaining_contributor_capabilities, selected_remaining, strict=True
    ):
        anchor = anchor_by_intent[anchor_key]
        primary_by_capability[capability["capability_key"]] = _primary_row(
            capability,
            source_info[anchor_key],
            semantic_anchor_slot_ordinal=anchor["semantic_anchor_slot_ordinal"],
        )
        used.add(anchor_key)

    reserved_anchor_keys = set(anchor_by_intent) - {
        row["intent_key"] for row in primary_by_capability.values()
    }
    reserved_anchor_rows = [
        {
            "family": source_info[key]["family"],
            "intent_key": key,
            "semantic_anchor_slot_ordinal": anchor_by_intent[key][
                "semantic_anchor_slot_ordinal"
            ],
            "variant_id": source_info[key]["variant_id"],
        }
        for key in sorted(
            reserved_anchor_keys,
            key=lambda key: anchor_by_intent[key]["semantic_anchor_slot_ordinal"],
        )
    ]
    if len(reserved_anchor_rows) != 5 or any(
        set(row) != RESERVED_SEMANTIC_ANCHOR_FIELDS for row in reserved_anchor_rows
    ):
        _fail("reserved semantic anchor closure drifted")

    contributor_families = {
        row["family"] for row in primary_by_capability.values()
    }
    missing_required_families = [
        family
        for family in use_case["required_families"]
        if family in SEARCHABLE_POSITIVE_FAMILIES
        and family not in contributor_families
    ]
    incidental_pool = [
        key
        for key in unreserved
        if key not in used
        and source_info[key]["gate_role"] == "incidental_searchable"
        and source_info[key]["target_bytes"] <= 32_768
    ]
    selected_incidental = []
    for family in missing_required_families:
        candidates = sorted(
            (
                key
                for key in incidental_pool
                if key not in selected_incidental
                and source_info[key]["family"] == family
            ),
            key=lambda key: _domain_key("incidental-required", key),
        )
        if not candidates:
            _fail(
                f"required searchable family lacks a <=32768-byte I5 source: {family}"
            )
        selected_incidental.append(candidates[0])
    fill = sorted(
        (key for key in incidental_pool if key not in selected_incidental),
        key=lambda key: _domain_key("incidental-fill", key),
    )
    selected_incidental.extend(fill[: 5 - len(selected_incidental)])
    if len(selected_incidental) != 5:
        _fail("small-cell incidental source selection did not close at five")
    incidental_capabilities = sorted(
        (
            row
            for row in capabilities
            if row["gate_role_requirement"] == "incidental_searchable"
        ),
        key=lambda row: _ascii(row["capability_key"]),
    )
    for capability, intent_key in zip(
        incidental_capabilities, selected_incidental, strict=True
    ):
        primary_by_capability[capability["capability_key"]] = _primary_row(
            capability, source_info[intent_key]
        )
        used.add(intent_key)

    primary_rows = [
        primary_by_capability[row["capability_key"]]
        for row in sorted(capabilities, key=lambda row: _ascii(row["capability_key"]))
    ]
    companion_rows.sort(key=lambda row: _ascii(row["primary_capability_key"]))
    if (
        len(primary_rows) != EXPECTED_PRIMARY_MATCHES_PER_PERSONA
        or len(companion_rows) != EXPECTED_COMPANION_MATCHES_PER_PERSONA
        or len({row["intent_key"] for row in primary_rows + companion_rows})
        != EXPECTED_LIFECYCLE_SOURCE_REFS_PER_PERSONA
        or any(
            row["gate_role"] == "incidental_searchable"
            and source_info[row["intent_key"]]["target_bytes"] > 32_768
            for row in primary_rows
        )
    ):
        _fail("lifecycle source selection cardinality or I5 bound drifted")
    return {
        "companion_rows": companion_rows,
        "primary_rows": primary_rows,
        "reserved_anchor_rows": reserved_anchor_rows,
        "source_info": source_info,
        "unreserved": unreserved,
        "use_case": use_case,
        "used_lifecycle_intents": {row["intent_key"] for row in primary_rows + companion_rows},
    }


def _format_witness_rows(selection):
    primary_rows = selection["primary_rows"]
    source_info = selection["source_info"]
    use_case = selection["use_case"]
    used_extra = set(selection["used_lifecycle_intents"])
    rows = []
    for family in use_case["required_families"]:
        if family in SEARCHABLE_POSITIVE_FAMILIES:
            candidates = sorted(
                (row for row in primary_rows if row["family"] == family),
                key=lambda row: _ascii(row["capability_key"]),
            )
            if not candidates:
                _fail(f"searchable family lacks a lifecycle query anchor: {family}")
            match = candidates[0]
            row = {
                "classification": "searchable-positive",
                "family": family,
                "intent_key": match["intent_key"],
                "offline_disposition": source_info[match["intent_key"]][
                    "offline_disposition"
                ],
                "parameter_cell_key": match["parameter_cell_key"],
                "physical_witness_required": True,
                "primary_use_case_id": use_case["primary_use_case_id"],
                "query_answer_anchor_required": True,
                "query_anchor_ref": match["intent_key"],
                "source_profile_id": match["source_profile_id"],
                "source_selection_kind": "matched-lifecycle-primary",
                "variant_id": match["variant_id"],
            }
            expected = POSITIVE_FORMAT_WITNESS_FIELDS
        else:
            if family in PENDING_CONVERSION_FAMILIES:
                classification = "pending-conversion-negative"
                preferred = {"jpg", "png"} if family == "image" else None
            elif family in RAW_ONLY_FAMILIES:
                classification = "raw-only-structural-negative"
                preferred = None
            else:
                _fail(f"required family has no witness classification: {family}")
            candidates = [
                key
                for key in selection["unreserved"]
                if key not in used_extra
                and source_info[key]["family"] == family
                and source_info[key]["gate_role"] == "raw_only"
            ]
            if preferred is not None:
                preferred_candidates = [
                    key for key in candidates if source_info[key]["variant_id"] in preferred
                ]
                if preferred_candidates:
                    candidates = preferred_candidates
            candidates.sort(key=lambda key: _domain_key("format-witness", key))
            if not candidates:
                _fail(f"required negative family lacks an unreserved witness: {family}")
            intent_key = candidates[0]
            info = source_info[intent_key]
            expected_negative = (
                "awaiting_ocr"
                if family in {"pdf_scan", "image"}
                else "await_conversion"
                if family in {"docx", "xlsx", "pptx"}
                else "unsupported_binary"
            )
            if info["offline_disposition"] != expected_negative:
                _fail("negative witness disposition differs from classification policy")
            row = {
                "classification": classification,
                "family": family,
                "intent_key": intent_key,
                "negative_expectation": expected_negative,
                "offline_disposition": info["offline_disposition"],
                "parameter_cell_key": info["parameter_cell_key"],
                "physical_witness_required": True,
                "primary_use_case_id": use_case["primary_use_case_id"],
                "query_answer_anchor_required": False,
                "source_profile_id": info["source_profile_id"],
                "source_selection_kind": "extra-overlay-unreserved-pilot-witness",
                "variant_id": info["variant_id"],
            }
            expected = NEGATIVE_FORMAT_WITNESS_FIELDS
            used_extra.add(intent_key)
        if set(row) != expected:
            _fail("format witness row schema drifted")
        rows.append(row)
    if [row["family"] for row in rows] != use_case["required_families"]:
        _fail("format witnesses do not preserve exact required-family order")
    return rows


_EXPECTED_BASELINE_SUBTYPES = {
    "w1-typed-edit": 69,
    "w1-incidental-typed-edit": 1,
    "w2-rename": 5,
    "w2-move": 5,
    "w3-surface-edit": 54,
    "w4-archive": 10,
    "w4-delete": 20,
    "w4-create-x-prime": 20,
    "w5-export-x": 10,
    "w5-restore-x": 10,
    "w5-delete-x-prime": 10,
    "w5-create-p-prime": 15,
    "w5-purge-p": 15,
}


def _event_subject(operation_key, *, companion=False, diagnostic=False):
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


def _event_rules(operation_key):
    edit = operation_key in {
        "w1-typed-edit",
        "w1-incidental-typed-edit",
        "w3-surface-edit",
    }
    if edit:
        byte_rule = "bytes/new-disjoint"
        fact_rule = (
            "facts/typed-revision"
            if operation_key != "w3-surface-edit"
            else "facts/carry-forward"
        )
        before, after = "state/live", "state/live-plus-history"
    elif operation_key in {"w2-rename", "w2-move", "w4-archive"}:
        byte_rule = "bytes/preserved"
        fact_rule = "facts/preserved"
        before, after = "state/live-before-path", "state/live-after-path"
    elif operation_key == "w3-derive-diagnostic":
        byte_rule = "bytes/new-derived"
        fact_rule = "facts/derived-nondenom"
        before, after = "state/diag-absent", "state/derived-live"
    elif operation_key.startswith("w3-duplicate-diagnostic"):
        byte_rule = "bytes/reused"
        fact_rule = "facts/preserved-nondenom"
        before, after = "state/diag-absent", "state/duplicate-live"
    elif operation_key == "w4-delete":
        byte_rule = "bytes/history-retained"
        fact_rule = "facts/history-only"
        before, after = "state/live", "state/deleted-history"
    elif operation_key in {"w4-create-x-prime", "w5-create-p-prime"}:
        byte_rule = "bytes/new-distinct"
        fact_rule = "facts/repl-distinct"
        before, after = "state/repl-absent", "state/repl-live"
    elif operation_key == "w5-export-x":
        byte_rule = "bytes/exact-export"
        fact_rule = "facts/no-change"
        before, after = "state/deleted-history", "state/export-nonindexed"
    elif operation_key == "w5-restore-x":
        byte_rule = "bytes/cas-reuse"
        fact_rule = "facts/restored-current-history"
        before, after = "state/deleted-history", "state/restored-live"
    elif operation_key == "w5-delete-x-prime":
        byte_rule = "bytes/x-prime-history"
        fact_rule = "facts/x-prime-history-only"
        before, after = "state/x-prime-live", "state/x-prime-deleted"
    elif operation_key == "w5-purge-p":
        byte_rule = "bytes/two-p-versions-purged"
        fact_rule = "facts/p-witness-unreachable"
        before, after = "state/p-live-plus-history", "state/p-purged"
    elif operation_key == "w5-forced-purged-commit":
        byte_rule = "bytes/no-change"
        fact_rule = "facts/purge-committed"
        before, after = "state/p-purged", "state/p-purge-committed"
    else:
        _fail(f"event operation has no abstract transition rules: {operation_key}")
    return before, after, byte_rule, fact_rule


def _event_visibility(operation_key, capability_class_key):
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


def _event_anchor(operation_key):
    if operation_key == "w4-create-x-prime":
        return "anchor/x-prime-new"
    if operation_key == "w5-delete-x-prime":
        return "anchor/x-prime-existing"
    if operation_key == "w5-create-p-prime":
        return "anchor/p+-new"
    if operation_key == "w5-export-x":
        return "anchor/x-export"
    if operation_key == "w5-restore-x":
        return "anchor/x-plus-export"
    if operation_key in {"w5-purge-p", "w5-forced-purged-commit"}:
        return "anchor/p-purge-witness"
    if operation_key.startswith("w3-") and "diagnostic" in operation_key:
        return "anchor/stable-diagnostic"
    return "anchor/w0-capability"


def _symbol_domain(operation, symbol_order):
    used = {
        term["symbol"]
        for term in operation["delta_terms"]
        if term["symbol"] != "zero"
    }
    if not used:
        return "symbols:none"
    return "symbols:" + ",".join(symbol for symbol in symbol_order if symbol in used)


def _source_event_row(spec, ordinal, persona_id, operation, symbol_order):
    match = spec["match"]
    operation_key = spec["operation_key"]
    _before, _after, byte_rule, fact_rule = _event_rules(operation_key)
    value = {
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
        "scenario_visibility_rule": _event_visibility(
            operation_key, match["capability_class_key"]
        ),
        "scope_relation_rule_key": operation["scope_relation_rule_key"],
        "source_intent_key": spec["source_intent_key"],
        "symbol_domain_ref": _symbol_domain(operation, symbol_order),
        "variant_id": match["variant_id"],
        "wave": operation["wave"],
    }
    if set(value) != SOURCE_EVENT_ROW_FIELDS:
        _fail("source lifecycle event row schema drifted")
    return value


def _scope_event_row(spec, ordinal, persona_id):
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
    value = {
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
    if set(value) != SCOPE_EVENT_ROW_FIELDS:
        _fail("scope lifecycle event row schema drifted")
    return value


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
_IDENTITY_PRESERVING_PATH_OPERATIONS = frozenset(
    {"w2-move", "w2-rename", "w4-archive"}
)


def _event_intent_key(persona_id, ordinal):
    return f"{persona_id}-lifecycle-event-intent-{ordinal:04d}"


def _created_source_intent_key(persona_id, ordinal):
    return f"{persona_id}-pre-solve-source-intent-{ordinal:04d}"


def _capability_suffix(match):
    return match["capability_key"].rsplit("-", 1)[-1]


def _resolve_source_event_dependencies(combined, persona_id):
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
        subject_key = (
            match["capability_key"],
            match["intent_key"],
            operation_key,
        )
        if subject_key in by_subject_operation:
            _fail("source event subject/operation identity is not unique")
        by_subject_operation[subject_key] = entry
        if not spec.get("companion", False):
            primary_key = (match["capability_key"], operation_key)
            if primary_key in primary_by_capability_operation:
                _fail("primary capability operation identity is not unique")
            primary_by_capability_operation[primary_key] = entry
        entries.append(entry)

    def subject_entry(spec, operation_key, *, required=True):
        match = spec["match"]
        entry = by_subject_operation.get(
            (match["capability_key"], match["intent_key"], operation_key)
        )
        if entry is None and required:
            _fail(
                "required predecessor event is absent for "
                f"{match['capability_key']}/{operation_key}"
            )
        return entry

    def primary_entry(spec, operation_key):
        match = spec["match"]
        entry = primary_by_capability_operation.get(
            (match["capability_key"], operation_key)
        )
        if entry is None:
            _fail(
                "required primary mirror event is absent for "
                f"{match['capability_key']}/{operation_key}"
            )
        return entry

    for entry in entries:
        spec = entry["spec"]
        match = spec["match"]
        operation_key = spec["operation_key"]
        ordinal = entry["ordinal"]
        capability_suffix = _capability_suffix(match)
        capability_class = match["capability_class_key"]

        if operation_key in {"w4-delete", "w4-create-x-prime"}:
            group_key = f"{persona_id}-event-dependency-x4-{capability_suffix}"
        elif operation_key in {
            "w5-export-x",
            "w5-restore-x",
            "w5-delete-x-prime",
        }:
            group_key = f"{persona_id}-event-dependency-x5-{capability_suffix}"
        elif operation_key in {
            "w5-create-p-prime",
            "w5-purge-p",
            "w5-forced-purged-commit",
        }:
            group_key = f"{persona_id}-event-dependency-p5-{capability_suffix}"
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
            prior_spec = prior["spec"]
            source_intent_key = prior_spec["after_source_intent_key"]

        if spec.get("companion", False) and capability_class == (
            "replacement-current-cross-format"
        ):
            mirrored = primary_entry(spec, operation_key)
            predecessors.append(mirrored["event_intent_key"])

        predecessors = sorted(
            set(predecessors),
            key=lambda key: int(key.rsplit("-", 1)[-1]),
        )
        if operation_key in _CREATED_SOURCE_OPERATIONS:
            after_source_intent_key = _created_source_intent_key(
                persona_id, ordinal
            )
        elif operation_key in _IDENTITY_PRESERVING_PATH_OPERATIONS:
            after_source_intent_key = source_intent_key
        else:
            after_source_intent_key = source_intent_key
        spec["after_source_intent_key"] = after_source_intent_key
        spec["dependency_group_key"] = group_key
        spec["predecessor_event_intent_refs"] = predecessors
        spec["source_intent_key"] = source_intent_key

    multi_event_groups = {}
    event_ordinal_by_key = {
        entry["event_intent_key"]: entry["ordinal"] for entry in entries
    }
    for entry in entries:
        spec = entry["spec"]
        group_key = spec["dependency_group_key"]
        multi_event_groups[group_key] = multi_event_groups.get(group_key, 0) + 1
        if any(
            event_ordinal_by_key[predecessor] >= entry["ordinal"]
            for predecessor in spec["predecessor_event_intent_refs"]
        ):
            _fail("source event predecessor must be earlier in event order")
    if sum(size > 1 for size in multi_event_groups.values()) != 48:
        _fail("multi-event dependency group count must be exact forty-eight")
    created_count = sum(
        entry["spec"]["after_source_intent_key"]
        == _created_source_intent_key(persona_id, entry["ordinal"])
        for entry in entries
    )
    diagnostic_count = sum(
        entry["spec"]["operation_key"].startswith("w3-derive-diagnostic")
        or entry["spec"]["operation_key"].startswith(
            "w3-duplicate-diagnostic"
        )
        for entry in entries
    )
    if created_count != 179 + diagnostic_count:
        _fail("event-created pre-solve source intent count drifted")


def _event_rows(global_inputs, selection, persona_id):
    coverage = global_inputs["coverage"]
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
    primary_by_key = {
        row["capability_key"]: row for row in selection["primary_rows"]
    }
    companion_by_key = {
        row["primary_capability_key"]: row for row in selection["companion_rows"]
    }
    specs = []
    baseline_counts = {}
    for capability_key in sorted(primary_by_key, key=_ascii):
        capability = capability_by_key[capability_key]
        for operation_key in capability["required_event_profile_keys"]:
            specs.append(
                {
                    "match": primary_by_key[capability_key],
                    "operation_key": operation_key,
                }
            )
            baseline_counts[operation_key] = baseline_counts.get(operation_key, 0) + 1
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
    if baseline_counts != _EXPECTED_BASELINE_SUBTYPES or len(specs) != 244:
        _fail("baseline lifecycle event subtype counts drifted")

    diagnostic_count = (5 if persona_id in DERIVE_DIAGNOSTIC_PERSONAS else 0) + (
        5 if persona_id in DUPLICATE_DIAGNOSTIC_PERSONAS else 0
    )
    diagnostic_sources = sorted(
        (
            row
            for row in selection["primary_rows"]
            if row["capability_class_key"].startswith("stable-current-")
        ),
        key=lambda row: _domain_key("diagnostic-source", row["intent_key"]),
    )[:diagnostic_count]
    if len(diagnostic_sources) != diagnostic_count:
        _fail("stable-current diagnostic source pool is insufficient")
    cursor = 0
    if persona_id in DERIVE_DIAGNOSTIC_PERSONAS:
        for match in diagnostic_sources[cursor : cursor + 5]:
            specs.append(
                {
                    "diagnostic": True,
                    "match": match,
                    "operation_key": "w3-derive-diagnostic",
                }
            )
        cursor += 5
    if persona_id in DUPLICATE_DIAGNOSTIC_PERSONAS:
        for index, match in enumerate(
            diagnostic_sources[cursor : cursor + 5], start=1
        ):
            operation_key = (
                "w3-duplicate-diagnostic-same-scope"
                if index in {1, 3, 5}
                else "w3-duplicate-diagnostic-cross-scope"
            )
            specs.append(
                {
                    "diagnostic": True,
                    "match": match,
                    "operation_key": operation_key,
                }
            )

    purged_matches = [
        row
        for row in selection["primary_rows"]
        if row["capability_class_key"] == "purged-negative"
    ]
    if len(purged_matches) != 15:
        _fail("forced purge commit source count drifted")
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
            _ascii(spec["match"]["capability_key"]),
            spec.get("companion", False),
            _ascii(spec["match"]["intent_key"]),
        )
    )
    scope_specs = []
    for wave in ("W1", "W2", "W3", "W4", "W5-pre-purge"):
        for scope_slot_ordinal in range(1, 21):
            scope_specs.append(
                {
                    "operation_key": "ordinary-scope-index",
                    "scope_slot_ordinal": scope_slot_ordinal,
                    "wave": wave,
                }
            )
    for scope_slot_ordinal in range(1, 21):
        scope_specs.append(
            {
                "operation_key": "w5-post-purge-noop-index",
                "scope_slot_ordinal": scope_slot_ordinal,
                "wave": "W5-final",
            }
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
    _resolve_source_event_dependencies(combined, persona_id)
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
            _fail(f"scope index barrier lacks source events for {wave}")
        spec["dependency_group_key"] = (
            f"{persona_id}-event-dependency-index-barrier-{wave.lower()}"
        )
        spec["predecessor_event_intent_refs"] = [predecessor]
    rows = []
    for ordinal, (kind, spec) in enumerate(combined, start=1):
        if kind == "source":
            rows.append(
                _source_event_row(
                    spec,
                    ordinal,
                    persona_id,
                    operations[spec["operation_key"]],
                    symbol_order,
                )
            )
        else:
            rows.append(_scope_event_row(spec, ordinal, persona_id))
    expected = EXPECTED_EVENT_BASELINE_PER_PERSONA + diagnostic_count
    if (
        len(rows) != expected
        or sum(row["row_kind"] == "source" for row in rows)
        != 259 + diagnostic_count
        or sum(row["event_profile_key"] == "ordinary-scope-index" for row in rows)
        != 100
        or sum(
            row["event_profile_key"] == "w5-post-purge-noop-index" for row in rows
        )
        != 20
    ):
        _fail("expanded lifecycle event inventory count drifted")
    return rows


def _event_receipt(rows, persona_id):
    parts = [_jsonl_row_bytes(row) for row in rows]
    body = b"".join(parts)
    if len(body) > MAX_EVENT_BODY_BYTES:
        _fail("expanded lifecycle event body exceeds its cap")
    value = {
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
    if set(value) != EVENT_RECEIPT_FIELDS:
        _fail("expanded lifecycle event receipt schema drifted")
    return value


def _postflight_origin_providers(
    persona_id,
    persona_inputs,
    *,
    source_origin_provider,
    reservation_origin_provider,
    semantic_origin_provider,
    assignment_origin_provider,
):
    checks = (
        (
            source_origin_provider,
            persona_inputs["source_origin"],
            source_package.canonical_json_bytes,
            "source",
        ),
        (
            reservation_origin_provider,
            persona_inputs["reservation_origin"],
            reservation_layout.canonical_json_bytes,
            "reservation",
        ),
        (
            semantic_origin_provider,
            persona_inputs["semantic_origin"],
            semantics.canonical_json_bytes,
            "semantic",
        ),
    )
    for provider, opening, canonical, label in checks:
        try:
            closing = copy.deepcopy(provider(persona_id))
            opening_raw = canonical(opening)
            closing_raw = canonical(closing)
        except Exception as error:
            raise PersonaV2SourceMatchedLifecycleInventoryError(
                f"{label} origin postflight provider failed"
            ) from error
        if not hmac.compare_digest(opening_raw, closing_raw):
            _fail(f"{label} origin provider changed during construction")
    if assignment_origin_provider is not _default_assignment_origin_provider:
        closing_payload = copy.deepcopy(assignment_origin_provider(persona_id))
        closing_manifest, closing_map = _authenticate_assignment_payload(
            persona_id,
            closing_payload,
            list(persona_inputs["source_by_intent"].values()),
        )
        if (
            not hmac.compare_digest(
                assignments.canonical_json_bytes(persona_inputs["assignment_origin"]),
                assignments.canonical_json_bytes(closing_manifest),
            )
            or closing_map != persona_inputs["parameter_by_intent"]
        ):
            _fail("assignment origin provider changed during construction")


def _construct_persona(
    persona_id,
    *,
    dependency_observer=None,
    source_origin_provider=None,
    reservation_origin_provider=None,
    semantic_origin_provider=None,
    assignment_origin_provider=None,
):
    _require_persona_id(persona_id)
    source_origin_provider = (
        _default_source_origin_provider
        if source_origin_provider is None
        else source_origin_provider
    )
    reservation_origin_provider = (
        _default_reservation_origin_provider
        if reservation_origin_provider is None
        else reservation_origin_provider
    )
    semantic_origin_provider = (
        _default_semantic_origin_provider
        if semantic_origin_provider is None
        else semantic_origin_provider
    )
    assignment_origin_provider = (
        _default_assignment_origin_provider
        if assignment_origin_provider is None
        else assignment_origin_provider
    )
    global_inputs = _detached_global_inputs(dependency_observer)
    persona_inputs = _load_persona_inputs(
        persona_id,
        source_origin_provider=source_origin_provider,
        reservation_origin_provider=reservation_origin_provider,
        semantic_origin_provider=semantic_origin_provider,
        assignment_origin_provider=assignment_origin_provider,
    )
    if assignment_origin_provider is not _default_assignment_origin_provider:
        try:
            assignments.validate_source_parameter_assignment_origin_manifest(
                persona_id, "pilot", persona_inputs["assignment_origin"]
            )
        except Exception as error:
            raise PersonaV2SourceMatchedLifecycleInventoryError(
                "custom assignment origin is not exact upstream regeneration"
            ) from error
    selection = _select_source_matches(global_inputs, persona_inputs, persona_id)
    witness_rows = _format_witness_rows(selection)
    event_rows = _event_rows(global_inputs, selection, persona_id)
    event_receipt = _event_receipt(event_rows, persona_id)

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
        selection["source_info"][row["intent_key"]]["target_bytes"]
        for row in selection["primary_rows"]
        if row["gate_role"] == "incidental_searchable"
    ]
    bindings = [*global_inputs["bindings"], *persona_inputs["bindings"]]
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
        "event_receipt": event_receipt,
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "input_binding_order": [row["name"] for row in bindings],
        "input_bindings": bindings,
        "orders": {
            "companion_match_rows": "primary-capability-key-ascii",
            "event_rows_nonpersisted": "wave-operation-capability-source-then-scope-slot",
            "primary_match_rows": "capability-key-ascii",
            "reserved_semantic_anchor_rows": "semantic-anchor-slot-ordinal",
            "use_case_family_witness_rows": "primary-use-case-required-family-order",
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
            "full_profile_source_selection": "byte-identical-pilot-reuse-no-residual",
            "incidental_assignment_cell_target_bytes_inclusive_maximum": 32_768,
            "incidental_observed_chunk_domain": {
                "inclusive_maximum": 70,
                "inclusive_minimum": 1,
                "observed_values_present": False,
            },
            "negative_family_sources": "extra-overlay-unreserved-pilot-raw-only",
            "positive_family_sources": "matched-lifecycle-primary-query-anchor",
            "semantic_anchor_selection": "ten-cross-first-then-ninety-primary-hash-order",
            "semantic_anchor_slots_reserved_unused": 5,
            "source_or_event_final_identity_present": False,
        },
        "primary_match_rows": selection["primary_rows"],
        "companion_match_rows": selection["companion_rows"],
        "reserved_semantic_anchor_rows": selection["reserved_anchor_rows"],
        "use_case_family_witness_rows": witness_rows,
        "remaining_blockers": [
            "effective-lifecycle-fact-and-rendition-overlay-not-built",
            "scope-bucket-cohort-quota-solver-solution-and-proof-not-built",
            "solution-compiled-history-plan-and-pre-w2-patch-not-built",
            "query-render-evaluation-target-and-relevance-not-built",
            "filesystem-render-index-history-kio-receipts-and-g0-not-built",
        ],
        "summary": {
            "companion_source_match_count": len(selection["companion_rows"]),
            "contributor_primary_source_match_count": sum(
                row["gate_role"] == "contract_contributor"
                for row in selection["primary_rows"]
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
                for row in selection["primary_rows"]
            ),
            "incidental_selected_target_bytes_maximum": max(incidental_targets),
            "lifecycle_source_ref_count": EXPECTED_LIFECYCLE_SOURCE_REFS_PER_PERSONA,
            "negative_extra_physical_witness_count": sum(
                not row["query_answer_anchor_required"] for row in witness_rows
            ),
            "primary_source_match_count": len(selection["primary_rows"]),
            "reserved_unused_semantic_anchor_count": len(
                selection["reserved_anchor_rows"]
            ),
            "selected_pilot_parameter_assignment_resolution_count": len(
                {
                    row["intent_key"]
                    for row in selection["primary_rows"]
                    + selection["companion_rows"]
                    + witness_rows
                }
            ),
        },
    }
    _reject_prohibited_keys(value)
    raw = canonical_json_bytes(value)
    if len(raw) > MAX_PERSONA_BYTES:
        _fail("persona match owner exceeds its cap")
    _postflight_origin_providers(
        persona_id,
        persona_inputs,
        source_origin_provider=source_origin_provider,
        reservation_origin_provider=reservation_origin_provider,
        semantic_origin_provider=semantic_origin_provider,
        assignment_origin_provider=assignment_origin_provider,
    )
    return value, tuple(event_rows)


def _build_source_matched_lifecycle_persona(
    persona_id,
    *,
    dependency_observer=None,
    source_origin_provider=None,
    reservation_origin_provider=None,
    semantic_origin_provider=None,
    assignment_origin_provider=None,
):
    """Provider-aware construction hook used by focused adversarial tests."""

    value, _rows = _construct_persona(
        persona_id,
        dependency_observer=dependency_observer,
        source_origin_provider=source_origin_provider,
        reservation_origin_provider=reservation_origin_provider,
        semantic_origin_provider=semantic_origin_provider,
        assignment_origin_provider=assignment_origin_provider,
    )
    return value


@functools.lru_cache(maxsize=20)
def _cached_persona_state(persona_id):
    return _construct_persona(persona_id)


def build_source_matched_lifecycle_persona(persona_id):
    """Return one detached compact match owner and event receipt."""

    value, _rows = _cached_persona_state(persona_id)
    return copy.deepcopy(value)


def iter_source_matched_lifecycle_event_rows(persona_id):
    """Yield one persona's deterministic nonpersisted lifecycle event view."""

    _value, rows = _cached_persona_state(persona_id)
    for row in rows:
        yield copy.deepcopy(row)


def source_matched_lifecycle_event_body_bytes(persona_id):
    body = b"".join(
        _jsonl_row_bytes(row)
        for row in iter_source_matched_lifecycle_event_rows(persona_id)
    )
    if len(body) > MAX_EVENT_BODY_BYTES:
        _fail("expanded lifecycle event body exceeds its cap")
    return body


def _persona_binding(value):
    return _origin_binding(
        "persona-v2-source-matched-lifecycle-persona",
        "one-persona-compact-source-match-and-event-receipt-owner",
        value,
        canonical=canonical_json_bytes,
        coordinates=("persona_id",),
    )


@functools.lru_cache(maxsize=1)
def _canonical_suite_descriptor():
    global_inputs = _detached_global_inputs()
    personas = [
        build_source_matched_lifecycle_persona(persona_id)
        for persona_id in envelope.PERSONA_IDS
    ]
    persona_bindings = [_persona_binding(value) for value in personas]
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
    event_count = sum(value["summary"]["event_intent_count"] for value in personas)
    witness_count = sum(value["summary"]["format_witness_count"] for value in personas)
    if (
        event_count != EXPECTED_EVENT_SUITE_COUNT
        or witness_count != EXPECTED_FORMAT_WITNESS_COUNT
        or witness_counts
        != {
            "searchable-positive": EXPECTED_SEARCHABLE_WITNESS_COUNT,
            "pending-conversion-negative": EXPECTED_PENDING_WITNESS_COUNT,
            "raw-only-structural-negative": EXPECTED_RAW_ONLY_WITNESS_COUNT,
        }
    ):
        _fail("suite event or format-witness exact totals drifted")
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
        "input_binding_order": [row["name"] for row in global_inputs["bindings"]],
        "input_bindings": global_inputs["bindings"],
        "orders": {
            "persona_bindings": "persona-id",
            "persona_local_rows": "owned-by-bound-persona-manifest",
        },
        "persona_bindings": persona_bindings,
        "policy": {
            "diagnostic_derive_personas": sorted(DERIVE_DIAGNOSTIC_PERSONAS),
            "diagnostic_duplicate_personas": sorted(DUPLICATE_DIAGNOSTIC_PERSONAS),
            "duplicate_branch_pattern": [
                "same-scope",
                "cross-scope",
                "same-scope",
                "cross-scope",
                "same-scope",
            ],
            "event_baseline_per_persona": EXPECTED_EVENT_BASELINE_PER_PERSONA,
            "format_witness_classification": {
                "pending-conversion-negative": sorted(PENDING_CONVERSION_FAMILIES),
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
                value["summary"]["companion_source_match_count"] for value in personas
            ),
            "event_intent_count": event_count,
            "format_witness_count": witness_count,
            "format_witness_counts": witness_counts,
            "lifecycle_source_ref_count": sum(
                value["summary"]["lifecycle_source_ref_count"] for value in personas
            ),
            "maximum_event_body_bytes_nonpersisted": max(
                value["event_receipt"]["body_bytes"] for value in personas
            ),
            "maximum_event_row_bytes_including_lf": max(
                value["event_receipt"]["maximum_row_bytes_including_lf"]
                for value in personas
            ),
            "maximum_persona_match_owner_bytes": max(
                len(canonical_json_bytes(value)) for value in personas
            ),
            "persona_count": len(personas),
            "primary_source_match_count": sum(
                value["summary"]["primary_source_match_count"] for value in personas
            ),
            "reserved_unused_semantic_anchor_count": sum(
                value["summary"]["reserved_unused_semantic_anchor_count"]
                for value in personas
            ),
        },
    }
    _reject_prohibited_keys(value)
    canonical_json_bytes(value)
    return value


def build_source_matched_lifecycle_suite_descriptor():
    """Return the detached twenty-person suite descriptor."""

    return copy.deepcopy(_canonical_suite_descriptor())


def _content_projection_value(persona_id):
    persona = build_source_matched_lifecycle_persona(persona_id)
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
        comparable = {key: value for key, value in existing.items() if key != "selection_role_refs"}
        candidate = {
            "family": row["family"],
            "gate_role": existing["gate_role"],
            "intent_key": intent_key,
            "parameter_cell_key": row["parameter_cell_key"],
            "source_profile_id": row["source_profile_id"],
            "variant_id": row["variant_id"],
        }
        if comparable != candidate:
            _fail("content projection reused one intent with conflicting content metadata")
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
    for intent_key in sorted(by_intent, key=_ascii):
        row = by_intent[intent_key]
        row["selection_role_refs"].sort(key=_ascii)
        if set(row) != CONTENT_ROW_FIELDS:
            _fail("content-only projection row schema drifted")
        source_selection_rows.append(row)

    source_event_rows = []
    scope_event_rows = []
    source_event_count = 0
    scope_event_count = 0
    created_source_intent_count = 0
    dependency_group_counts = {}
    for event in iter_source_matched_lifecycle_event_rows(persona_id):
        if set(event) == SOURCE_EVENT_ROW_FIELDS:
            projected = {
                key: event[key] for key in CONTENT_SOURCE_EVENT_ROW_FIELDS
            }
            source_event_count += 1
            if event["after_source_intent_key"] == _created_source_intent_key(
                persona_id, event["event_sequence_ordinal"]
            ):
                created_source_intent_count += 1
            source_event_rows.append(projected)
        elif set(event) == SCOPE_EVENT_ROW_FIELDS:
            projected = {
                key: event[key] for key in CONTENT_SCOPE_EVENT_ROW_FIELDS
            }
            scope_event_count += 1
            scope_event_rows.append(projected)
        else:
            _fail("content projection received an unknown lifecycle event row")
        group_key = event["dependency_group_key"]
        dependency_group_counts[group_key] = (
            dependency_group_counts.get(group_key, 0) + 1
        )

    content_sections = {
        "scope_event_rows": scope_event_rows,
        "source_event_rows": source_event_rows,
        "source_selection_rows": source_selection_rows,
    }
    if set(content_sections) != CONTENT_SECTIONS_FIELDS:
        _fail("content-only projection section schema drifted")
    multi_event_dependency_group_count = sum(
        count > 1 for count in dependency_group_counts.values()
    )
    if multi_event_dependency_group_count != 54:
        _fail("content projection multi-event dependency group count drifted")
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
            "full_profile_selection": "exact-pilot-intent-reuse-no-residual-selection",
            "lifecycle_event_order": "event-sequence-ordinal",
            "parameter_cell_identity": "authenticated-upstream-parameter-cell-key",
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
            "source_event_content_row_count": source_event_count,
            "source_selection_content_row_count": len(source_selection_rows),
            "scope_event_content_row_count": scope_event_count,
            "unique_selected_intent_count": len(source_selection_rows),
        },
    }
    raw = canonical_json_bytes(value)
    if len(raw) > TARGET_CONTENT_PROJECTION_BYTES:
        _fail("content-only projection exceeds its 256-KiB target")
    return value


def build_source_matched_lifecycle_content_projection(persona_id):
    """Return the normalized content-only projection without derivation pins."""

    _require_persona_id(persona_id)
    return copy.deepcopy(_content_projection_value(persona_id))


def canonical_json_bytes(value):
    if type(value) is not dict:
        _fail("source-matched lifecycle artifact must be an object")
    schema = value.get("artifact_schema")
    labels = {
        PERSONA_SCHEMA: (
            "persona v2 source-matched lifecycle persona",
            MAX_PERSONA_BYTES,
        ),
        SUITE_SCHEMA: (
            "persona v2 source-matched lifecycle suite",
            MAX_SUITE_BYTES,
        ),
        PROJECTION_SCHEMA: (
            "persona v2 source-matched lifecycle content projection",
            MAX_CONTENT_PROJECTION_BYTES,
        ),
    }
    if schema not in labels:
        _fail(f"unknown source-matched lifecycle schema: {schema!r}")
    label, maximum = labels[schema]
    return _canonical_fragment(value, label=label, max_bytes=maximum)


def validate_source_matched_lifecycle_persona(persona_id, value):
    _require_persona_id(persona_id)
    try:
        from . import persona_v2_source_matched_lifecycle_inventory_validator as independent
    except ImportError:  # pragma: no cover - direct-script compatibility
        try:
            import persona_v2_source_matched_lifecycle_inventory_validator as independent
        except ImportError:
            independent = None
    if independent is not None:
        try:
            independent.validate_source_matched_lifecycle_persona(
                persona_id,
                value,
                event_body_provider=source_matched_lifecycle_event_body_bytes,
            )
        except independent.PersonaV2SourceMatchedLifecycleInventoryValidationError as error:
            raise PersonaV2SourceMatchedLifecycleInventoryError(str(error)) from None
        return True
    expected = build_source_matched_lifecycle_persona(persona_id)
    if canonical_json_bytes(value) != canonical_json_bytes(expected):
        _fail("persona artifact differs from exact regeneration")
    return True


def validate_source_matched_lifecycle_suite_descriptor(value):
    try:
        from . import persona_v2_source_matched_lifecycle_inventory_validator as independent
    except ImportError:  # pragma: no cover - direct-script compatibility
        try:
            import persona_v2_source_matched_lifecycle_inventory_validator as independent
        except ImportError:
            independent = None
    if independent is not None:
        try:
            independent.validate_source_matched_lifecycle_suite_descriptor(value)
        except independent.PersonaV2SourceMatchedLifecycleInventoryValidationError as error:
            raise PersonaV2SourceMatchedLifecycleInventoryError(str(error)) from None
        return True
    expected = build_source_matched_lifecycle_suite_descriptor()
    if canonical_json_bytes(value) != canonical_json_bytes(expected):
        _fail("suite artifact differs from exact regeneration")
    return True


def validate_source_matched_lifecycle_content_projection(persona_id, value):
    _require_persona_id(persona_id)
    try:
        from . import persona_v2_source_matched_lifecycle_inventory_validator as independent
    except ImportError:  # pragma: no cover - direct-script compatibility
        try:
            import persona_v2_source_matched_lifecycle_inventory_validator as independent
        except ImportError:
            independent = None
    if independent is not None:
        try:
            independent.validate_source_matched_lifecycle_content_projection(
                persona_id, value
            )
        except independent.PersonaV2SourceMatchedLifecycleInventoryValidationError as error:
            raise PersonaV2SourceMatchedLifecycleInventoryError(str(error)) from None
        return True
    expected = build_source_matched_lifecycle_content_projection(persona_id)
    if canonical_json_bytes(value) != canonical_json_bytes(expected):
        _fail("content projection differs from exact regeneration")
    return True


def source_matched_lifecycle_persona_sha256(persona_id, value=None):
    if value is None:
        value = build_source_matched_lifecycle_persona(persona_id)
    validate_source_matched_lifecycle_persona(persona_id, value)
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def source_matched_lifecycle_suite_sha256(value=None):
    if value is None:
        value = build_source_matched_lifecycle_suite_descriptor()
    validate_source_matched_lifecycle_suite_descriptor(value)
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def source_matched_lifecycle_content_projection_sha256(persona_id, value=None):
    if value is None:
        value = build_source_matched_lifecycle_content_projection(persona_id)
    validate_source_matched_lifecycle_content_projection(persona_id, value)
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def require_compiled_history_and_solution():
    raise PersonaV2SourceMatchedLifecycleInventoryError(
        "source matching and pre-solve event intents are complete, but effective "
        "lifecycle membership, scope/quota solving, compiled history, query/render, "
        "execution receipts, observations, and G0 remain absent"
    )


__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "ASSIGNMENT_SUITE_CANONICAL_BYTES",
    "ASSIGNMENT_SUITE_SHA256",
    "AUTHORITY_FIELDS",
    "COMPANION_MATCH_FIELDS",
    "CONTENT_SCOPE_EVENT_ROW_FIELDS",
    "CONTENT_ROW_FIELDS",
    "CONTENT_SECTIONS_FIELDS",
    "CONTENT_SOURCE_EVENT_ROW_FIELDS",
    "CONTRIBUTOR_PRIMARY_MATCH_FIELDS",
    "EVENT_RECEIPT_FIELDS",
    "EXPECTED_SUITE_CANONICAL_BYTES",
    "EXPECTED_SUITE_SHA256",
    "INCIDENTAL_PRIMARY_MATCH_FIELDS",
    "MAX_CONTENT_PROJECTION_BYTES",
    "MAX_EVENT_BODY_BYTES",
    "MAX_EVENT_ROW_BYTES_INCLUDING_LF",
    "MAX_PERSONA_BYTES",
    "MAX_SUITE_BYTES",
    "NEGATIVE_FORMAT_WITNESS_FIELDS",
    "PERSONA_KIND",
    "PERSONA_SCHEMA",
    "POSITIVE_FORMAT_WITNESS_FIELDS",
    "PROJECTION_KIND",
    "PROJECTION_SCHEMA",
    "RESERVED_SEMANTIC_ANCHOR_FIELDS",
    "SCOPE_EVENT_ROW_FIELDS",
    "SOURCE_EVENT_ROW_FIELDS",
    "SUITE_KIND",
    "SUITE_SCHEMA",
    "TARGET_CONTENT_PROJECTION_BYTES",
    "PersonaV2SourceMatchedLifecycleInventoryError",
    "build_source_matched_lifecycle_content_projection",
    "build_source_matched_lifecycle_persona",
    "build_source_matched_lifecycle_suite_descriptor",
    "canonical_json_bytes",
    "iter_source_matched_lifecycle_event_rows",
    "require_compiled_history_and_solution",
    "source_matched_lifecycle_content_projection_sha256",
    "source_matched_lifecycle_event_body_bytes",
    "source_matched_lifecycle_persona_sha256",
    "source_matched_lifecycle_suite_sha256",
    "validate_source_matched_lifecycle_content_projection",
    "validate_source_matched_lifecycle_persona",
    "validate_source_matched_lifecycle_suite_descriptor",
]
