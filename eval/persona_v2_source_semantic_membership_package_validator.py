"""Builder-independent validation for persona-PC v2 source semantics.

The target package binds compact content-context and source-owned fact-
membership policy to the already materialized 203,000 structural source rows.
This module deliberately does not import
``persona_v2_source_semantic_membership_package``.  It reconstructs the
admissible semantic domain from independently validated upstream artifacts and
checks compact and expanded JSONL one bounded shard at a time.

Successful validation is evidence about this non-authorizing metadata package
only.  It grants no renderer, writer, solver, history, query, KCS, or G0
authority.
"""

from __future__ import annotations

import copy
import gc
import functools
import hashlib
import io

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_bounded_jsonl as bounded_jsonl
    from . import persona_v2_contract as envelope
    from . import persona_v2_fact_graph as fact_graph
    from . import persona_v2_overlay_reservation_layout as reservation_layout
    from . import persona_v2_overlay_reservation_validator as reservation_validator
    from . import persona_v2_realism_profile as realism
    from . import persona_v2_source_inventory_layout as source_layout
    from . import persona_v2_source_inventory_package_validator as source_validator
    from . import persona_v2_source_inventory_profile as inventory_profile
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_bounded_jsonl as bounded_jsonl
    import persona_v2_contract as envelope
    import persona_v2_fact_graph as fact_graph
    import persona_v2_overlay_reservation_layout as reservation_layout
    import persona_v2_overlay_reservation_validator as reservation_validator
    import persona_v2_realism_profile as realism
    import persona_v2_source_inventory_layout as source_layout
    import persona_v2_source_inventory_package_validator as source_validator
    import persona_v2_source_inventory_profile as inventory_profile


ORIGIN_ORDER = ("pilot", "full-residual")
PROFILE_ORDER = ("pilot", "full")
TOPIC_SLOT_ORDER = ("g01", "g02", "g03", "g04")
GATE_ROLE_ORDER = (
    "contract_contributor",
    "incidental_searchable",
    "raw_only",
)

EXPECTED_PERSONA_COUNT = 20
EXPECTED_SOURCE_COUNT = 203_000
EXPECTED_SOURCE_SHARD_COUNT = 73
EXPECTED_ORIGIN_COUNT = 40
EXPECTED_PROFILE_COUNT = 40
EXPECTED_FACT_PROFILE_COUNT_PER_PERSONA = 45
EXPECTED_FACT_PROFILE_COUNT = 900
EXPECTED_RANGE_ROW_COUNT = 73
EXPECTED_ANCHOR_ROW_COUNT = 2_100
EXPECTED_CONFLICT_ROW_COUNT = 1_560
EXPECTED_CONFLICT_ENDPOINT_COUNT = 2 * EXPECTED_CONFLICT_ROW_COUNT
EXPECTED_COMPACT_ROW_COUNT = 3_733
EXPECTED_OVERRIDE_SOURCE_COUNT = 5_220
EXPECTED_OVERLAY_REFERENCE_COUNT = 46_840
EXPECTED_NEAR_REVISION_COUNT = 13_230
EXPECTED_VERSION_ONE_COUNT = EXPECTED_SOURCE_COUNT - EXPECTED_NEAR_REVISION_COUNT
EXPECTED_COMPACT_BODY_BYTES = 1_006_627
EXPECTED_EXPANDED_CONTEXT_BODY_BYTES = 121_020_941
EXPECTED_EXPANDED_MEMBERSHIP_BODY_BYTES = 135_741_615
EXPECTED_PRESENT_FACT_REFERENCE_COUNT = 1_019_380
EXPECTED_MAXIMUM_COMPACT_ROW_BYTES = 734
EXPECTED_MAXIMUM_CONTEXT_ROW_BYTES = 633
EXPECTED_MAXIMUM_MEMBERSHIP_ROW_BYTES = 743
EXPECTED_MAXIMUM_CONTEXT_SHARD_BODY_BYTES = 2_484_590
EXPECTED_MAXIMUM_MEMBERSHIP_SHARD_BODY_BYTES = 3_030_632
EXPECTED_SUITE_DESCRIPTOR_BYTES = 49_837
EXPECTED_SUITE_SHA256 = (
    "62394dd2a3544f7d6c332652e6799b7a60353e8e3aa6a87f80e0ff21590a2e28"
)
EXPECTED_P12_CURRENT_COMPONENT_BYTES = 12_070_092

MAX_COMPACT_ROW_BYTES_INCLUDING_LF = 768
MAX_COMPACT_ORIGIN_BODY_BYTES = 4 * 2**20
MAX_COMPACT_ROWS_PER_ORIGIN = 4_096
MAX_EXPANDED_ROW_BYTES_INCLUDING_LF = 768
MAX_EXPANDED_SHARD_BODY_BYTES = 4 * 2**20
MAX_EXPANDED_ROWS_PER_SHARD = 4_096
MAX_CATALOG_BYTES = 2 * 2**20
MAX_ORIGIN_MANIFEST_BYTES = 256 * 1024
MAX_PROFILE_MANIFEST_BYTES = 256 * 1024
MAX_SUITE_DESCRIPTOR_BYTES = 512 * 1024
MAX_PERSONA_PACKAGE_BYTES = 16 * 2**20

CATALOG_ARTIFACT_SCHEMA = "kcs.persona.pc-source-semantic-membership-catalog/v2"
CATALOG_ARTIFACT_KIND = "persona-pc-v2-source-semantic-membership-catalog"
ORIGIN_ARTIFACT_SCHEMA = (
    "kcs.persona.pc-source-semantic-membership-origin-manifest/v2"
)
ORIGIN_ARTIFACT_KIND = "persona-pc-v2-source-semantic-membership-origin-manifest"
PROFILE_ARTIFACT_SCHEMA = (
    "kcs.persona.pc-source-semantic-membership-profile-manifest/v2"
)
PROFILE_ARTIFACT_KIND = "persona-pc-v2-source-semantic-membership-profile-manifest"
SUITE_ARTIFACT_SCHEMA = "kcs.persona.pc-source-semantic-membership-suite/v2"
SUITE_ARTIFACT_KIND = "persona-pc-v2-source-semantic-membership-suite"
ARTIFACT_SCHEMA_VERSION = 2

AUTHORITY_FIELDS = frozenset(
    {
        "actual_chunks_attested",
        "authorizes_final_source_identifiers",
        "authorizes_g0_freeze",
        "authorizes_history_mutation",
        "authorizes_kcs_execution",
        "authorizes_physical_write",
        "authorizes_renderer_execution",
        "authorizes_solver_execution",
        "authorizes_source_plan",
        "filesystem_writer_available",
        "formal_capacity_gate_satisfied",
        "formal_complete_persona_package_cap_proved",
        "history_executor_available",
        "kcs_execution_available",
        "query_instances_rendered",
        "query_spec_hashed",
        "renderer_available",
    }
)

PROHIBITED_KEY_TOKENS = frozenset(
    {"answer", "distractor", "final", "oracle", "query", "relevance", "retrieval"}
)

FACT_PROFILE_FIELDS = frozenset(
    {
        "branch_role",
        "conflict_set_id",
        "conflict_template_key",
        "fact_profile_id",
        "graph_id",
        "persona_id",
        "present_fact_ids",
        "profile_kind",
        "project_or_case_id",
        "synthetic_entity_ids",
    }
)
TOPIC_FIELDS = frozenset(
    {"graph_id", "persona_id", "project_or_case_id", "topic_id", "topic_slot"}
)
SEMANTIC_PROFILE_FIELDS = frozenset(
    {
        "content_template_slot_id",
        "document_role",
        "family",
        "filename_template_slot_id",
        "formal_recipe_binding_status",
        "gate_role",
        "language_binding_mode",
        "semantic_profile_id",
        "source_profile_id",
        "variant_id",
    }
)
RANGE_ROW_FIELDS = frozenset(
    {
        "expanded_content_context_body_bytes",
        "expanded_content_context_max_row_bytes_including_lf",
        "expanded_content_context_sha256",
        "expanded_fact_membership_body_bytes",
        "expanded_fact_membership_max_row_bytes_including_lf",
        "expanded_fact_membership_sha256",
        "first_intent_key",
        "last_intent_key",
        "row_count",
        "row_kind",
        "source_body_sha256",
        "source_shard_id",
    }
)
ANCHOR_ROW_FIELDS = frozenset(
    {"fact_profile_id", "intent_key", "row_kind", "semantic_anchor_slot_ordinal"}
)
CONFLICT_ROW_FIELDS = frozenset(
    {
        "anchor_fact_profile_id",
        "anchor_intent_key",
        "cluster_key",
        "derivative_fact_profile_id",
        "derivative_intent_key",
        "row_kind",
    }
)
EXPANDED_CONTEXT_ROW_FIELDS = frozenset(
    {
        "container_role_ids",
        "content_context_id",
        "content_relation_role",
        "deterministic_payload_seed",
        "intent_key",
        "language",
        "logical_period_id",
        "membership_status",
        "origin",
        "payload_equivalence_key",
        "persona_id",
        "semantic_anchor_capacity",
        "semantic_profile_id",
        "semantic_version",
        "topic_id",
    }
)
EXPANDED_MEMBERSHIP_ROW_FIELDS = frozenset(
    {
        "fact_profile_id",
        "intent_key",
        "logical_branch_key",
        "logical_document_key",
        "logical_revision_key",
        "origin",
        "persona_id",
        "present_fact_ids",
        "present_fact_set_key",
        "projection_mode",
        "semantic_section_key",
    }
)

CATALOG_TOP_LEVEL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "assignment_contract",
        "authority",
        "canonical_limits",
        "completion_claims",
        "completion_scope",
        "dependency_direction_contract",
        "fact_profiles",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
        "hypothesis_status",
        "input_binding_order",
        "input_bindings",
        "orders",
        "remaining_blockers",
        "semantic_profiles",
        "semantic_topics",
        "summary",
    }
)
ORIGIN_BODY_DESCRIPTOR_FIELDS = frozenset(
    {
        "body_bytes",
        "body_sha256",
        "file_name",
        "maximum_row_bytes_including_lf",
        "row_count",
    }
)
ORIGIN_TOP_LEVEL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "body_descriptor",
        "canonical_limits",
        "completion_claims",
        "completion_scope",
        "dependency_direction_contract",
        "fact_profile_assignment_counts",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
        "hypothesis_status",
        "input_binding_order",
        "input_bindings",
        "language_quota_counts",
        "origin",
        "persona_id",
        "remaining_blockers",
        "summary",
        "topic_quota_counts",
    }
)
ORIGIN_SUMMARY_FIELDS = frozenset(
    {
        "compact_anchor_row_count",
        "compact_conflict_pair_row_count",
        "compact_range_receipt_row_count",
        "component_count",
        "expanded_content_context_body_bytes",
        "expanded_fact_membership_body_bytes",
        "maximum_component_source_count",
        "maximum_expanded_content_context_row_bytes_including_lf",
        "maximum_expanded_content_context_shard_body_bytes",
        "maximum_expanded_fact_membership_row_bytes_including_lf",
        "maximum_expanded_fact_membership_shard_body_bytes",
        "present_fact_reference_count",
        "semantic_version_source_counts",
        "source_count",
        "source_shard_count",
    }
)
FACT_PROFILE_ASSIGNMENT_COUNT_FIELDS = frozenset(
    {"fact_profile_id", "source_count"}
)
LANGUAGE_QUOTA_COUNT_FIELDS = frozenset({"language", "source_count"})
TOPIC_QUOTA_COUNT_FIELDS = frozenset({"source_count", "topic_id"})
PROFILE_TOP_LEVEL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "canonical_limits",
        "catalog_binding",
        "completion_claims",
        "completion_scope",
        "dependency_direction_contract",
        "fact_profile_assignment_counts",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
        "hypothesis_status",
        "language_quota_counts",
        "origin_manifest_bindings",
        "origin_order",
        "persona_id",
        "profile",
        "remaining_blockers",
        "summary",
        "topic_quota_counts",
    }
)
PROFILE_SUMMARY_FIELDS = frozenset(
    {
        "compact_body_bytes",
        "compact_row_count",
        "expanded_content_context_body_bytes",
        "expanded_fact_membership_body_bytes",
        "origin_manifest_count",
        "present_fact_reference_count",
        "semantic_version_source_counts",
        "source_count",
        "source_shard_count",
    }
)
SUITE_TOP_LEVEL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "canonical_limits",
        "catalog_binding",
        "completion_claims",
        "completion_scope",
        "dependency_direction_contract",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
        "hypothesis_status",
        "input_binding_order",
        "input_bindings",
        "orders",
        "origin_manifest_bindings",
        "persona_current_component_byte_ledgers",
        "profile_manifest_bindings",
        "remaining_blockers",
        "summary",
    }
)
PERSONA_COMPONENT_LEDGER_FIELDS = frozenset(
    {
        "catalog_bytes_conservatively_charged_in_full",
        "compact_semantic_origin_body_bytes",
        "current_component_bytes",
        "current_component_cap_satisfied",
        "existing_source_inventory_component_bytes",
        "formal_complete_persona_package_cap_proved",
        "headroom_bytes",
        "matching_reservation_origin_bytes",
        "max_current_component_bytes",
        "persona_id",
        "semantic_origin_manifest_bytes",
        "semantic_profile_manifest_bytes",
    }
)
SUITE_SUMMARY_FIELDS = frozenset(
    {
        "compact_anchor_row_count",
        "compact_body_bytes",
        "compact_conflict_pair_row_count",
        "compact_range_receipt_row_count",
        "compact_row_count",
        "expanded_content_context_body_bytes",
        "expanded_fact_membership_body_bytes",
        "fact_profile_kind_source_counts",
        "maximum_compact_row_bytes_including_lf",
        "maximum_component_source_count",
        "maximum_expanded_content_context_row_bytes_including_lf",
        "maximum_expanded_content_context_shard_body_bytes",
        "maximum_expanded_fact_membership_row_bytes_including_lf",
        "maximum_expanded_fact_membership_shard_body_bytes",
        "origin_manifest_count",
        "present_fact_reference_count",
        "profile_manifest_count",
        "semantic_version_source_counts",
        "source_count",
        "source_shard_count",
    }
)


class PersonaV2SourceSemanticMembershipPackageValidationError(ValueError):
    """Raised when a semantic-membership package fails independent checks."""


def _fail(message):
    raise PersonaV2SourceSemanticMembershipPackageValidationError(message)


def _ascii_key(value):
    if type(value) is not str:
        _fail("canonical identifiers must be exact strings")
    try:
        return value.encode("ascii", "strict")
    except UnicodeEncodeError:
        _fail("canonical identifiers must be ASCII")


def _require_exact_int(value, *, label, minimum=0, maximum=None):
    if type(value) is not int or value < minimum:
        _fail(f"{label} must be an exact integer >= {minimum}")
    if maximum is not None and value > maximum:
        _fail(f"{label} exceeds its maximum")
    return value


def _require_exact_fields(value, fields, *, label):
    if type(value) is not dict or set(value) != set(fields):
        _fail(f"{label} field set drifted")


def _require_sha256(value, *, label):
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _fail(f"{label} must be a lowercase SHA-256 digest")


def _canonical_bytes(value, *, label, max_bytes):
    try:
        return artifact_common.canonical_json_bytes(
            value, label=label, max_bytes=max_bytes
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _require_canonical_equal(actual, expected, *, label, max_bytes):
    if _canonical_bytes(actual, label=label, max_bytes=max_bytes) != _canonical_bytes(
        expected, label=f"expected {label}", max_bytes=max_bytes
    ):
        _fail(f"{label} differs from its exact expected value")


def _reject_prohibited_fields(value, *, path=()):
    if type(value) is dict:
        for key, child in value.items():
            if type(key) is not str:
                _fail("artifact object keys must be exact strings")
            lowered = key.lower()
            authority_exception = path == ("authority",) and key in AUTHORITY_FIELDS
            if not authority_exception and any(
                token in lowered for token in PROHIBITED_KEY_TOKENS
            ):
                _fail(
                    "semantic package contains a prohibited downstream field: "
                    + ".".join(path + (key,))
                )
            _reject_prohibited_fields(child, path=path + (key,))
    elif type(value) is list:
        for child in value:
            _reject_prohibited_fields(child, path=path + ("[]",))


def _sha256_paths(value, path=()):
    result = set()
    if type(value) is dict:
        for key, child in value.items():
            child_path = path + (key,)
            if type(key) is str and key.endswith("sha256"):
                result.add(child_path)
            result.update(_sha256_paths(child, child_path))
    elif type(value) is list:
        for child in value:
            result.update(_sha256_paths(child, path + ("[]",)))
    return frozenset(result)


def _require_all_false_authority(value, *, label):
    if type(value) is not dict or value.get("g0_contract_frozen") is not False:
        _fail(f"{label} must remain exact non-G0")
    authority = value.get("authority")
    if type(authority) is not dict or set(authority) != AUTHORITY_FIELDS:
        _fail(f"{label} authority field set drifted")
    if any(type(flag) is not bool or flag is not False for flag in authority.values()):
        _fail(f"{label} authority must contain exact all-false booleans")


def _validate_common_envelope(value, *, kind, schema, label):
    if (
        type(value) is not dict
        or value.get("artifact_kind") != kind
        or value.get("artifact_schema") != schema
        or value.get("artifact_schema_version") != ARTIFACT_SCHEMA_VERSION
        or value.get("fixture_id") != envelope.FIXTURE_ID
        or value.get("fixture_schema_version") != envelope.FIXTURE_SCHEMA_VERSION
    ):
        _fail(f"{label} identity or fixture binding drifted")
    _require_all_false_authority(value, label=label)


def _provider_bytes(provider, coordinates, *, label):
    if not callable(provider):
        _fail(f"{label} provider must be callable")
    try:
        body = provider(*coordinates)
    except Exception as error:
        raise PersonaV2SourceSemanticMembershipPackageValidationError(
            f"{label} provider failed for {'/'.join(map(str, coordinates))}"
        ) from error
    if type(body) is not bytes:
        _fail(f"{label} provider must return exact bytes")
    return body


def _canonical_jsonl(rows, *, label, row_cap, body_cap):
    if type(rows) is not list or not rows:
        _fail(f"{label} must contain at least one row")
    parts = []
    maximum = 0
    for index, row in enumerate(rows, start=1):
        raw = _canonical_bytes(
            row,
            label=f"{label} row {index}",
            max_bytes=row_cap - 1,
        ) + b"\n"
        if len(raw) > row_cap:
            _fail(f"{label} row exceeds its LF-inclusive cap")
        parts.append(raw)
        maximum = max(maximum, len(raw))
    body = b"".join(parts)
    if len(body) > body_cap:
        _fail(f"{label} body exceeds its cap")
    return body, maximum


def _load_source_shard(descriptor, provider):
    coordinates = (
        descriptor["persona_id"],
        descriptor["origin"],
        descriptor["shard_ordinal"],
    )
    body = _provider_bytes(provider, coordinates, label="source shard body")
    if (
        len(body) != descriptor["body_bytes"]
        or hashlib.sha256(body).hexdigest() != descriptor["body_sha256"]
    ):
        _fail("source shard provider bytes differ from the validated descriptor")
    try:
        rows = bounded_jsonl.load_declared_canonical_jsonl(
            io.BytesIO(body),
            declared_body_bytes=len(body),
            descriptor={
                "body_sha256": descriptor["body_sha256"],
                "first_key": descriptor["first_intent_key"],
                "last_key": descriptor["last_intent_key"],
                "row_count": descriptor["row_count"],
            },
            key_field="intent_key",
            max_body_bytes=source_layout.MAX_SHARD_BODY_BYTES,
            max_row_bytes_including_lf=source_layout.MAX_INTENT_JSONL_RECORD_BYTES,
            max_rows=source_layout.MAX_INTENTS_PER_SHARD,
        )
    except bounded_jsonl.PersonaV2BoundedJsonlError as error:
        _fail(str(error))
    return body, rows


def _public_binding(name, role, value, *, canonical):
    required = {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
    }
    if type(value) is not dict or not required <= set(value):
        _fail(f"{name} binding target lacks its required artifact identity")
    raw = canonical(value)
    return {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "dependency_role": role,
        "name": name,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _coordinate_binding(
    name, role, value, *, canonical, coordinate_fields=()
):
    result = _public_binding(name, role, value, canonical=canonical)
    for field in coordinate_fields:
        if field not in value:
            _fail(f"{name} binding lacks coordinate field {field}")
        result[field] = value[field]
    return result


def _canonical_unbounded_manifest(value, *, label, max_bytes):
    return _canonical_bytes(value, label=label, max_bytes=max_bytes)


def _validate_upstream_envelope(
    value,
    *,
    fields,
    kind,
    schema,
    authority_fields,
    label,
    max_bytes,
):
    _canonical_bytes(value, label=label, max_bytes=max_bytes)
    _require_exact_fields(value, fields, label=label)
    if (
        value.get("artifact_kind") != kind
        or value.get("artifact_schema") != schema
        or value.get("artifact_schema_version")
        != source_validator.ARTIFACT_SCHEMA_VERSION
        or value.get("fixture_id") != envelope.FIXTURE_ID
        or value.get("fixture_schema_version") != envelope.FIXTURE_SCHEMA_VERSION
        or value.get("g0_contract_frozen") is not False
    ):
        _fail(f"{label} common artifact identity drifted")
    authority = value.get("authority")
    if type(authority) is not dict or set(authority) != set(authority_fields):
        _fail(f"{label} authority field set drifted")
    if any(type(flag) is not bool or flag is not False for flag in authority.values()):
        _fail(f"{label} authority must remain exact all-false")


def _prevalidate_source_upstream_metadata(
    source_suite, source_origin_manifests, source_profile_manifests
):
    """Check source DAG identities before semantic binding reconstruction."""

    _validate_upstream_envelope(
        source_suite,
        fields=source_validator.SUITE_TOP_LEVEL_FIELDS,
        kind=source_validator.SUITE_ARTIFACT_KIND,
        schema=source_validator.SUITE_ARTIFACT_SCHEMA,
        authority_fields=source_validator.AUTHORITY_FIELDS,
        label="bound source inventory suite",
        max_bytes=source_validator.MAX_SUITE_DESCRIPTOR_BYTES,
    )
    expected_origins = [
        (persona_id, origin)
        for persona_id in envelope.PERSONA_IDS
        for origin in ORIGIN_ORDER
    ]
    expected_profiles = [
        (persona_id, profile)
        for persona_id in envelope.PERSONA_IDS
        for profile in PROFILE_ORDER
    ]
    for manifest, coordinate in zip(source_origin_manifests, expected_origins):
        _validate_upstream_envelope(
            manifest,
            fields=source_validator.ORIGIN_TOP_LEVEL_FIELDS,
            kind=source_validator.ORIGIN_ARTIFACT_KIND,
            schema=source_validator.ORIGIN_ARTIFACT_SCHEMA,
            authority_fields=source_validator.AUTHORITY_FIELDS,
            label="bound source inventory origin manifest",
            max_bytes=source_validator.MAX_ORIGIN_MANIFEST_BYTES,
        )
        if (manifest.get("persona_id"), manifest.get("origin")) != coordinate:
            _fail("source origin manifests are not in persona/origin order")
    for manifest, coordinate in zip(source_profile_manifests, expected_profiles):
        _validate_upstream_envelope(
            manifest,
            fields=source_validator.PROFILE_TOP_LEVEL_FIELDS,
            kind=source_validator.PROFILE_ARTIFACT_KIND,
            schema=source_validator.PROFILE_ARTIFACT_SCHEMA,
            authority_fields=source_validator.AUTHORITY_FIELDS,
            label="bound source inventory profile manifest",
            max_bytes=source_validator.MAX_PROFILE_MANIFEST_BYTES,
        )
        if (manifest.get("persona_id"), manifest.get("profile")) != coordinate:
            _fail("source profile manifests are not in persona/profile order")


@functools.lru_cache(maxsize=1)
def _validated_base_inputs():
    layout = source_layout.build_source_inventory_layout()
    profiles = inventory_profile.build_source_inventory_profile_catalog()
    realism_value = realism.build_realism_profile()
    graph_values = fact_graph.build_fact_graph_suite()
    source_layout.validate_source_inventory_layout(layout)
    inventory_profile.validate_source_inventory_profile_catalog(profiles)
    realism.validate_realism_profile(realism_value)
    if (
        type(graph_values) is not list
        or [row.get("persona_id") for row in graph_values]
        != list(envelope.PERSONA_IDS)
    ):
        _fail("typed fact graph suite persona order drifted")
    graph_by_persona = {}
    for persona_id, value in zip(envelope.PERSONA_IDS, graph_values):
        fact_graph.validate_fact_graph(persona_id, value)
        graph_by_persona[persona_id] = value
    persona_layouts = {row["persona_id"]: row for row in layout["personas"]}
    realism_by_persona = {
        row["persona_id"]: row for row in realism_value["personas"]
    }
    profile_by_id = {
        row["source_profile_id"]: row for row in profiles["source_profile_rows"]
    }
    if (
        tuple(persona_layouts) != envelope.PERSONA_IDS
        or tuple(realism_by_persona) != envelope.PERSONA_IDS
        or len(profile_by_id) != inventory_profile.EXPECTED_PROFILE_COUNT
    ):
        _fail("upstream source/realism/profile coverage drifted")
    return {
        "fact_graph_by_persona": graph_by_persona,
        "fact_graph_values": graph_values,
        "layout": layout,
        "persona_layouts": persona_layouts,
        "profile_by_id": profile_by_id,
        "profiles": profiles,
        "realism": realism_value,
        "realism_by_persona": realism_by_persona,
    }


def _fact_state_at_checkpoint(fact, checkpoint):
    rows = [
        row["state"]
        for row in fact.get("visibility_by_checkpoint", [])
        if row.get("checkpoint") == checkpoint
    ]
    if len(rows) != 1:
        _fail(f"fact has non-total visibility at {checkpoint}: {fact.get('fact_id')}")
    return rows[0]


def _entity_closure(graph, fact_ids):
    facts = {row["fact_id"]: row for row in graph["facts"]}
    entities = {row["entity_id"] for row in graph["entities"]}
    referenced = set()
    for fact_id in fact_ids:
        fact = facts.get(fact_id)
        if fact is None:
            _fail(f"fact profile references a foreign fact: {fact_id}")
        referenced.add(fact["subject_entity_id"])
        typed_value = fact["typed_value"]
        if typed_value.get("kind") == "entity-reference":
            referenced.add(typed_value["entity_id"])
    if not referenced <= entities:
        _fail("fact profile entity closure references a foreign entity")
    return sorted(referenced, key=_ascii_key)


@functools.lru_cache(maxsize=20)
def _expected_fact_profile_semantics(persona_id):
    """Return the exact 45 semantic profiles keyed by their semantic tuple."""

    graph_value = _validated_base_inputs()["fact_graph_by_persona"][persona_id]
    result = {
        ("empty", "none", "none"): {
            "branch_role": "not-applicable",
            "conflict_set_id": "not-applicable",
            "conflict_template_key": "not-applicable",
            "fact_profile_id": f"{persona_id}-source-fact-profile-empty-v2",
            "graph_id": "not-applicable",
            "persona_id": persona_id,
            "present_fact_ids": [],
            "profile_kind": "empty",
            "project_or_case_id": "not-applicable",
            "synthetic_entity_ids": [],
        }
    }
    ordered_graphs = sorted(graph_value["graphs"], key=lambda row: _ascii_key(row["graph_id"]))
    if len(ordered_graphs) != 4:
        _fail(f"{persona_id} must expose exactly four typed fact graphs")
    for graph_ordinal, graph in enumerate(ordered_graphs, start=1):
        graph_slot = TOPIC_SLOT_ORDER[graph_ordinal - 1]
        current = sorted(
            (
                row["fact_id"]
                for row in graph["facts"]
                if _fact_state_at_checkpoint(row, "W0") == "current"
            ),
            key=_ascii_key,
        )
        if len(current) != 8:
            _fail(f"{persona_id}/{graph['graph_id']} must expose exact eight W0 facts")
        common = {
            "branch_role": "not-applicable",
            "conflict_set_id": "not-applicable",
            "conflict_template_key": "not-applicable",
            "graph_id": graph["graph_id"],
            "persona_id": persona_id,
            "project_or_case_id": graph["project_or_case_id"],
        }
        result[("graph-normal-w0", graph["graph_id"], "all")] = {
            **common,
            "fact_profile_id": (
                f"{persona_id}-source-fact-profile-{graph_slot}-normal-v2"
            ),
            "present_fact_ids": current,
            "profile_kind": "graph-normal-w0",
            "synthetic_entity_ids": _entity_closure(graph, current),
        }
        for fact_slot, fact_id in enumerate(current, start=1):
            result[("w0-singleton", graph["graph_id"], fact_id)] = {
                **common,
                "fact_profile_id": (
                    f"{persona_id}-source-fact-profile-{graph_slot}-"
                    f"singleton-s{fact_slot:02d}-v2"
                ),
                "present_fact_ids": [fact_id],
                "profile_kind": "w0-singleton",
                "synthetic_entity_ids": _entity_closure(graph, [fact_id]),
            }
        conflict_sets = graph["conflict_sets"]
        if len(conflict_sets) != 1:
            _fail(f"{persona_id}/{graph['graph_id']} conflict-set cardinality drifted")
        conflict_set = conflict_sets[0]
        pair = sorted(conflict_set["member_fact_ids"], key=_ascii_key)
        common_facts = [fact_id for fact_id in current if fact_id not in pair]
        if len(pair) != 2 or len(common_facts) != 6:
            _fail(f"{persona_id}/{graph['graph_id']} conflict fact shape drifted")
        template_key = f"{persona_id}-conflict-fact-template-syn-{graph_ordinal:02d}"
        for branch_role, selected in zip(("a", "b"), pair):
            present = sorted(common_facts + [selected], key=_ascii_key)
            result[("conflict-branch", graph["graph_id"], branch_role)] = {
                "branch_role": branch_role,
                "conflict_set_id": conflict_set["conflict_set_id"],
                "conflict_template_key": template_key,
                "fact_profile_id": (
                    f"{persona_id}-source-fact-profile-{graph_slot}-"
                    f"branch-{branch_role}-v2"
                ),
                "graph_id": graph["graph_id"],
                "persona_id": persona_id,
                "present_fact_ids": present,
                "profile_kind": "conflict-branch",
                "project_or_case_id": graph["project_or_case_id"],
                "synthetic_entity_ids": _entity_closure(graph, present),
            }
    if len(result) != EXPECTED_FACT_PROFILE_COUNT_PER_PERSONA:
        _fail(f"{persona_id} fact profile semantic cardinality drifted")
    return result


def _validate_fact_profiles(rows):
    if type(rows) is not list or len(rows) != EXPECTED_FACT_PROFILE_COUNT:
        _fail("semantic catalog must contain exactly 900 fact profiles")
    expected_rows = []
    for persona_id in envelope.PERSONA_IDS:
        semantics = _expected_fact_profile_semantics(persona_id)
        expected_rows.append(semantics[("empty", "none", "none")])
        graph_value = _validated_base_inputs()["fact_graph_by_persona"][persona_id]
        graphs = sorted(graph_value["graphs"], key=lambda row: _ascii_key(row["graph_id"]))
        current_by_graph = {
            graph["graph_id"]: sorted(
                (
                    fact["fact_id"]
                    for fact in graph["facts"]
                    if _fact_state_at_checkpoint(fact, "W0") == "current"
                ),
                key=_ascii_key,
            )
            for graph in graphs
        }
        for fact_index in range(8):
            for graph in graphs:
                expected_rows.append(
                    semantics[
                        (
                            "w0-singleton",
                            graph["graph_id"],
                            current_by_graph[graph["graph_id"]][fact_index],
                        )
                    ]
                )
        for graph in graphs:
            expected_rows.append(
                semantics[("graph-normal-w0", graph["graph_id"], "all")]
            )
        for graph in graphs:
            for branch_role in ("a", "b"):
                expected_rows.append(
                    semantics[("conflict-branch", graph["graph_id"], branch_role)]
                )
    for row in rows:
        _require_exact_fields(row, FACT_PROFILE_FIELDS, label="fact profile")
    if rows != expected_rows:
        _fail("fact profiles differ from the exact typed-graph projection or order")
    ids = [row["fact_profile_id"] for row in rows]
    if len(ids) != len(set(ids)):
        _fail("fact profile IDs must be globally unique")
    by_id = {}
    semantic_index = {}
    counts = {persona_id: 0 for persona_id in envelope.PERSONA_IDS}
    for row in rows:
        persona_id = row["persona_id"]
        if persona_id not in counts:
            _fail("fact profile references a foreign persona")
        expected_semantics = _expected_fact_profile_semantics(persona_id)
        kind = row["profile_kind"]
        if kind == "empty":
            semantic_key = (kind, "none", "none")
        elif kind == "graph-normal-w0":
            semantic_key = (kind, row["graph_id"], "all")
        elif kind == "w0-singleton":
            present = row["present_fact_ids"]
            if type(present) is not list or len(present) != 1:
                _fail("singleton fact profile must contain exactly one fact")
            semantic_key = (kind, row["graph_id"], present[0])
        elif kind == "conflict-branch":
            semantic_key = (kind, row["graph_id"], row["branch_role"])
        else:
            _fail(f"unknown fact profile kind: {kind!r}")
        expected = expected_semantics.get(semantic_key)
        if expected is None or row != expected:
            _fail(f"fact profile has a foreign semantic tuple: {row['fact_profile_id']}")
        compound_key = (persona_id,) + semantic_key
        if compound_key in semantic_index:
            _fail(f"duplicate semantic fact profile: {row['fact_profile_id']}")
        semantic_index[compound_key] = row["fact_profile_id"]
        by_id[row["fact_profile_id"]] = row
        counts[persona_id] += 1
    if any(value != EXPECTED_FACT_PROFILE_COUNT_PER_PERSONA for value in counts.values()):
        _fail("fact profile persona marginals drifted")
    for persona_id in envelope.PERSONA_IDS:
        expected_keys = {
            (persona_id,) + key for key in _expected_fact_profile_semantics(persona_id)
        }
        if {key for key in semantic_index if key[0] == persona_id} != expected_keys:
            _fail(f"{persona_id} has missing or unused semantic fact profiles")
    return {"by_id": by_id, "semantic_index": semantic_index}


def _expected_semantic_topics():
    rows = []
    for persona_id in envelope.PERSONA_IDS:
        graph_value = _validated_base_inputs()["fact_graph_by_persona"][persona_id]
        graphs = sorted(graph_value["graphs"], key=lambda row: _ascii_key(row["graph_id"]))
        for graph_slot, graph in zip(TOPIC_SLOT_ORDER, graphs):
            rows.append(
                {
                    "graph_id": graph["graph_id"],
                    "persona_id": persona_id,
                    "project_or_case_id": graph["project_or_case_id"],
                    "topic_id": f"{persona_id}-semantic-topic-{graph_slot}-v2",
                    "topic_slot": graph_slot,
                }
            )
    return rows


def _validate_semantic_topics(rows):
    expected = _expected_semantic_topics()
    if type(rows) is not list or len(rows) != 80:
        _fail("semantic catalog must contain exact eighty topic rows")
    for row in rows:
        _require_exact_fields(row, TOPIC_FIELDS, label="semantic topic")
    if rows != expected:
        _fail("semantic topic graph/project/persona bijection or order drifted")
    return {
        "by_graph": {
            (row["persona_id"], row["graph_id"]): row for row in rows
        },
        "by_id": {row["topic_id"]: row for row in rows},
    }


def _expected_semantic_profiles():
    document_roles = {
        "code": "source-code",
        "csv_tsv": "tabular-record",
        "docx": "word-processing-document",
        "domain_binary": "domain-binary-record",
        "html_eml": "web-or-message",
        "image": "image-asset",
        "ipynb": "notebook",
        "md": "narrative-document",
        "media": "media-asset",
        "pdf_scan": "scanned-document",
        "pdf_text": "text-pdf-document",
        "pptx": "presentation",
        "structured_text": "structured-record",
        "txt_log": "plain-text-record",
        "xlsx": "spreadsheet",
    }
    rows = []
    for source_profile in _validated_base_inputs()["profiles"]["source_profile_rows"]:
        family = source_profile["family"]
        if family not in document_roles:
            _fail(f"semantic profile has no exact document role: {family}")
        variant_id = source_profile["variant_id"]
        rows.append(
            {
                "content_template_slot_id": (
                    f"persona-v2-content-template-slot-{variant_id}-v2"
                ),
                "document_role": document_roles[family],
                "family": family,
                "filename_template_slot_id": (
                    f"persona-v2-filename-template-slot-{variant_id}-v2"
                ),
                "formal_recipe_binding_status": source_profile["source_recipe"][
                    "binding_status"
                ],
                "gate_role": source_profile["gate_role"],
                "language_binding_mode": "origin-component-language",
                "semantic_profile_id": (
                    f"persona-v2-source-semantic-profile-{variant_id}-v2"
                ),
                "source_profile_id": source_profile["source_profile_id"],
                "variant_id": variant_id,
            }
        )
    return rows


def _validate_semantic_profiles(rows):
    expected = _expected_semantic_profiles()
    if type(rows) is not list or len(rows) != inventory_profile.EXPECTED_PROFILE_COUNT:
        _fail("semantic catalog must contain exact 71 semantic profiles")
    for row in rows:
        _require_exact_fields(row, SEMANTIC_PROFILE_FIELDS, label="semantic profile")
    if rows != expected:
        _fail("semantic profiles differ from exact inventory-profile projection")
    if any(
        row["formal_recipe_binding_status"] != "reserved-unbound"
        for row in rows
    ):
        _fail("semantic profiles may not escalate formal recipe binding")
    return {
        "by_semantic_id": {row["semantic_profile_id"]: row for row in rows},
        "by_source_id": {row["source_profile_id"]: row for row in rows},
    }


def _expected_catalog_input_bindings():
    inputs = _validated_base_inputs()
    rows = [
        _public_binding(
            "persona-v2-source-inventory-profile-catalog",
            "source-semantic-profile-foreign-keys",
            inputs["profiles"],
            canonical=inventory_profile.canonical_json_bytes,
        ),
        _public_binding(
            "persona-v2-realism-profile",
            "persona-language-weight-owner",
            inputs["realism"],
            canonical=realism.canonical_json_bytes,
        ),
    ]
    for persona_id, value in zip(envelope.PERSONA_IDS, inputs["fact_graph_values"]):
        row = _public_binding(
            "persona-v2-fact-graph",
            "typed-fact-profile-source",
            value,
            canonical=fact_graph.canonical_json_bytes,
        )
        row["persona_id"] = persona_id
        rows.append(row)
    return rows


def _validate_catalog(catalog):
    raw = _canonical_bytes(
        catalog,
        label="persona v2 source semantic membership catalog",
        max_bytes=MAX_CATALOG_BYTES,
    )
    _require_exact_fields(catalog, CATALOG_TOP_LEVEL_FIELDS, label="semantic catalog")
    _reject_prohibited_fields(catalog)
    _validate_common_envelope(
        catalog,
        kind=CATALOG_ARTIFACT_KIND,
        schema=CATALOG_ARTIFACT_SCHEMA,
        label="semantic catalog",
    )
    expected_bindings = _expected_catalog_input_bindings()
    if catalog["input_binding_order"] != [row["name"] for row in expected_bindings]:
        _fail("semantic catalog input binding order drifted")
    _require_canonical_equal(
        catalog["input_bindings"],
        expected_bindings,
        label="semantic catalog exact input bindings",
        max_bytes=MAX_CATALOG_BYTES,
    )
    expected_assignment_contract = {
        "component_edges": [
            "content-relation-anchor-to-derivative",
            "attachment-host-to-standalone-member",
        ],
        "conflict_anchor_maps_branch_a": True,
        "conflict_derivative_maps_branch_b": True,
        "empty_profile_allowed_gate_role": "raw_only",
        "fixed_topic_components": ["semantic-anchor", "conflict-copy"],
        "free_component_order": (
            "source-count-descending-then-minimum-intent-key-ascii"
        ),
        "label_choice_score": (
            "target-count-times-assigned-total-plus-component-size-minus-"
            "assigned-label-count-times-origin-source-count"
        ),
        "label_tie_break": "ascii-label",
        "language_fixed_components_present": False,
        "normal_conflict_presentation_mode": (
            "explicit-unordered-current-alternatives"
        ),
        "normal_profile_present_fact_count": 8,
        "quota_algorithm_id": envelope.APPORTIONMENT_ALGORITHM_ID,
        "quota_profiles": (
            "pilot-Hamilton-full-Hamilton-residual-equals-full-minus-pilot"
        ),
        "raw_only_present_fact_count": 0,
        "searchable_default_profile_kind": "graph-normal-w0",
        "singleton_anchor_profile_cycle": (
            "singleton-index-equals-semantic-anchor-slot-ordinal-minus-one-"
            "modulo-32-in-fact-slot-then-graph-slot-order"
        ),
    }
    _require_canonical_equal(
        catalog["assignment_contract"],
        expected_assignment_contract,
        label="semantic catalog assignment contract",
        max_bytes=MAX_CATALOG_BYTES,
    )
    _require_canonical_equal(
        catalog["canonical_limits"],
        {
            "max_body_bytes": MAX_CATALOG_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        label="semantic catalog canonical limits",
        max_bytes=MAX_CATALOG_BYTES,
    )
    _require_canonical_equal(
        catalog["completion_claims"],
        {
            "all_900_fact_profiles_bound": True,
            "all_71_semantic_profiles_bound": True,
            "all_80_semantic_topics_bound": True,
            "all_w0_profile_fact_ids_typed_graph_owned": True,
            "concrete_source_membership_bound": False,
            "formal_complete_persona_package_cap_proved": False,
            "history_membership_bound": False,
        },
        label="semantic catalog completion claims",
        max_bytes=MAX_CATALOG_BYTES,
    )
    _require_canonical_equal(
        catalog["dependency_direction_contract"],
        {
            "catalog_may_bind_origin_profile_or_suite_manifest": False,
            "fact_graphs_inventory_profiles_and_realism_are_strictly_upstream": True,
            "source_membership_manifests_must_bind_catalog": True,
        },
        label="semantic catalog dependency direction",
        max_bytes=MAX_CATALOG_BYTES,
    )
    _require_canonical_equal(
        catalog["completion_scope"],
        (
            "exact-w0-source-semantic-profile-and-topic-catalog-only-no-render-"
            "no-solver-no-history-no-execution-no-g0"
        ),
        label="semantic catalog completion scope",
        max_bytes=MAX_CATALOG_BYTES,
    )
    _require_canonical_equal(
        catalog["hypothesis_status"],
        "authored-benchmark-stress-design-not-observed-user-statistics",
        label="semantic catalog hypothesis status",
        max_bytes=MAX_CATALOG_BYTES,
    )
    _require_canonical_equal(
        catalog["orders"],
        {
            "fact_profiles": (
                "persona-then-empty-then-singleton-fact-then-graph-then-"
                "normal-then-conflict-graph-then-branch"
            ),
            "persona": list(envelope.PERSONA_IDS),
            "semantic_topics": "persona-then-graph-id-ascii",
            "topic_slot": list(TOPIC_SLOT_ORDER),
        },
        label="semantic catalog orders",
        max_bytes=MAX_CATALOG_BYTES,
    )
    _require_canonical_equal(
        catalog["remaining_blockers"],
        [
            "formal-source-recipes-and-missing-renderer-validator-implementations",
            "concrete-logical-overlay-materialization",
            "history-and-checkpoint-transition-membership",
            "scope-placement-allocation-and-proof",
            "render-write-chunk-observation-and-kcs-execution",
            "future-complete-persona-package-cap-proof",
        ],
        label="semantic catalog blocker ledger",
        max_bytes=MAX_CATALOG_BYTES,
    )
    if _sha256_paths(catalog) != frozenset({("input_bindings", "[]", "sha256")}):
        _fail("semantic catalog SHA dependency paths drifted")
    fact_profiles = _validate_fact_profiles(catalog["fact_profiles"])
    topics = _validate_semantic_topics(catalog["semantic_topics"])
    semantic_profiles = _validate_semantic_profiles(catalog["semantic_profiles"])
    _require_canonical_equal(
        catalog["summary"],
        {
            "conflict_branch_profile_count": 160,
            "empty_profile_count": 20,
            "fact_profile_count": EXPECTED_FACT_PROFILE_COUNT,
            "normal_profile_count": 80,
            "persona_count": EXPECTED_PERSONA_COUNT,
            "semantic_profile_count": inventory_profile.EXPECTED_PROFILE_COUNT,
            "semantic_topic_count": 80,
            "singleton_profile_count": 640,
        },
        label="semantic catalog summary",
        max_bytes=MAX_CATALOG_BYTES,
    )
    return {
        "fact_profiles": fact_profiles,
        "raw": raw,
        "semantic_profiles": semantic_profiles,
        "topics": topics,
    }


def validate_source_semantic_membership_catalog(catalog):
    """Validate the reusable 900-fact-profile semantic catalog independently."""

    _validate_catalog(catalog)
    return True


def _expected_origin_input_bindings(catalog, source_manifest, projection):
    persona_id = projection["artifact"]["persona_id"]
    origin = projection["artifact"]["origin"]
    graph_value = _validated_base_inputs()["fact_graph_by_persona"][persona_id]
    return [
        _coordinate_binding(
            "persona-v2-source-semantic-membership-catalog",
            "semantic-profile-topic-and-fact-profile-owner",
            catalog,
            canonical=lambda value: _canonical_bytes(
                value,
                label="semantic catalog binding target",
                max_bytes=MAX_CATALOG_BYTES,
            ),
        ),
        _coordinate_binding(
            "persona-v2-source-inventory-origin-manifest",
            "immutable-source-row-owner",
            source_manifest,
            canonical=lambda value: _canonical_bytes(
                value,
                label="source inventory origin binding target",
                max_bytes=source_validator.MAX_ORIGIN_MANIFEST_BYTES,
            ),
            coordinate_fields=("persona_id", "origin"),
        ),
        _coordinate_binding(
            "persona-v2-overlay-reservation-origin",
            "matching-relation-container-anchor-and-conflict-reservation",
            projection["artifact"],
            canonical=reservation_layout.canonical_json_bytes,
            coordinate_fields=("persona_id", "origin"),
        ),
        _coordinate_binding(
            "persona-v2-fact-graph",
            "direct-persona-typed-fact-owner",
            graph_value,
            canonical=fact_graph.canonical_json_bytes,
            coordinate_fields=("persona_id",),
        ),
    ]


def _expected_topic_quota_rows(projection, catalog_projection, persona_id):
    result = []
    for graph_id, count in projection["topic_targets"].items():
        topic = catalog_projection["topics"]["by_graph"].get((persona_id, graph_id))
        if topic is None:
            _fail("origin topic target does not resolve through the catalog")
        result.append({"source_count": count, "topic_id": topic["topic_id"]})
    return sorted(result, key=lambda row: _ascii_key(row["topic_id"]))


def _prevalidate_origin_manifest(
    manifest, *, persona_id, origin, catalog, catalog_projection, source_manifest
):
    raw = _canonical_bytes(
        manifest,
        label="persona v2 source semantic membership origin manifest",
        max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
    )
    _require_exact_fields(
        manifest, ORIGIN_TOP_LEVEL_FIELDS, label="source semantic origin manifest"
    )
    _reject_prohibited_fields(manifest)
    _validate_common_envelope(
        manifest,
        kind=ORIGIN_ARTIFACT_KIND,
        schema=ORIGIN_ARTIFACT_SCHEMA,
        label="source semantic origin manifest",
    )
    if manifest.get("persona_id") != persona_id or manifest.get("origin") != origin:
        _fail("source semantic origin manifests are not in persona/origin order")
    if (
        type(source_manifest) is not dict
        or source_manifest.get("persona_id") != persona_id
        or source_manifest.get("origin") != origin
    ):
        _fail("semantic origin was paired with a rethreaded source origin")

    projection = _origin_reservation_projection(
        persona_id,
        origin,
        catalog_projection["fact_profiles"]["semantic_index"],
    )
    expected_bindings = _expected_origin_input_bindings(
        catalog, source_manifest, projection
    )
    if manifest["input_binding_order"] != [row["name"] for row in expected_bindings]:
        _fail("source semantic origin input binding order drifted")
    _require_canonical_equal(
        manifest["input_bindings"],
        expected_bindings,
        label=f"source semantic origin bindings {persona_id}/{origin}",
        max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
    )
    _require_canonical_equal(
        manifest["canonical_limits"],
        {
            "max_compact_body_bytes": MAX_COMPACT_ORIGIN_BODY_BYTES,
            "max_compact_row_bytes_including_lf": MAX_COMPACT_ROW_BYTES_INCLUDING_LF,
            "max_compact_rows": MAX_COMPACT_ROWS_PER_ORIGIN,
            "max_expanded_context_row_bytes_including_lf": MAX_EXPANDED_ROW_BYTES_INCLUDING_LF,
            "max_expanded_fact_membership_row_bytes_including_lf": MAX_EXPANDED_ROW_BYTES_INCLUDING_LF,
            "max_expanded_rows_per_shard": MAX_EXPANDED_ROWS_PER_SHARD,
            "max_expanded_shard_body_bytes": MAX_EXPANDED_SHARD_BODY_BYTES,
            "max_manifest_bytes": MAX_ORIGIN_MANIFEST_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        label=f"source semantic origin limits {persona_id}/{origin}",
        max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
    )
    _require_canonical_equal(
        manifest["completion_claims"],
        {
            "all_origin_content_context_ids_resolved": True,
            "all_origin_present_fact_set_keys_resolved": True,
            "compact_override_and_range_body_complete": True,
            "expanded_context_and_membership_receipts_complete": True,
            "formal_complete_persona_package_cap_proved": False,
            "matching_reservation_exactly_projected": True,
            "source_inventory_rows_modified": False,
        },
        label=f"source semantic origin completion claims {persona_id}/{origin}",
        max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
    )
    _require_canonical_equal(
        manifest["completion_scope"],
        (
            "one-origin-source-owned-w0-semantic-context-and-fact-membership-"
            "with-streaming-receipts-no-render-no-solver-no-history-no-"
            "execution-no-g0"
        ),
        label=f"source semantic origin completion scope {persona_id}/{origin}",
        max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
    )
    _require_canonical_equal(
        manifest["dependency_direction_contract"],
        {
            "matching_source_and_reservation_origins_are_strictly_upstream": True,
            "origin_manifest_owns_fact_profile_assignment": True,
            "source_inventory_origin_may_bind_this_manifest": False,
            "streamed_expansions_may_redefine_catalog_fact_sets": False,
        },
        label=f"source semantic origin dependency direction {persona_id}/{origin}",
        max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
    )
    _require_canonical_equal(
        manifest["hypothesis_status"],
        "authored-benchmark-stress-design-not-observed-user-statistics",
        label=f"source semantic origin hypothesis status {persona_id}/{origin}",
        max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
    )
    _require_canonical_equal(
        manifest["remaining_blockers"],
        [
            "formal-source-recipes-and-renderer-validator-implementations",
            "concrete-overlay-materialization",
            "history-checkpoint-membership",
            "scope-placement-allocation-and-proof",
            "render-write-chunk-observation-and-kcs-execution",
            "future-complete-persona-package-cap-proof",
        ],
        label=f"source semantic origin blocker ledger {persona_id}/{origin}",
        max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
    )

    descriptors = source_manifest.get("shard_descriptors")
    if type(descriptors) is not list or not descriptors:
        _fail("bound source origin has no shard descriptors")
    expected_row_count = (
        len(descriptors)
        + len(projection["expected_anchor_rows"])
        + len(projection["expected_conflict_rows"])
    )
    if not 1 <= expected_row_count <= MAX_COMPACT_ROWS_PER_ORIGIN:
        _fail("compact semantic origin exceeds 4,096 rows")
    descriptor = manifest["body_descriptor"]
    _require_exact_fields(
        descriptor,
        ORIGIN_BODY_DESCRIPTOR_FIELDS,
        label="source semantic compact body descriptor",
    )
    if (
        descriptor.get("file_name")
        != f"{persona_id}-source-semantic-membership-{origin}.jsonl"
        or descriptor.get("row_count") != expected_row_count
    ):
        _fail("source semantic compact body descriptor identity drifted")
    _require_exact_int(
        descriptor.get("body_bytes"),
        label="source semantic compact body bytes",
        minimum=1,
        maximum=MAX_COMPACT_ORIGIN_BODY_BYTES,
    )
    _require_exact_int(
        descriptor.get("maximum_row_bytes_including_lf"),
        label="source semantic compact maximum row bytes",
        minimum=1,
        maximum=MAX_COMPACT_ROW_BYTES_INCLUDING_LF,
    )
    _require_sha256(descriptor.get("body_sha256"), label="compact body SHA-256")

    expected_languages = [
        {"language": label, "source_count": count}
        for label, count in sorted(
            projection["language_targets"].items(), key=lambda item: _ascii_key(item[0])
        )
    ]
    expected_topics = _expected_topic_quota_rows(
        projection, catalog_projection, persona_id
    )
    for row in manifest["language_quota_counts"]:
        _require_exact_fields(
            row, LANGUAGE_QUOTA_COUNT_FIELDS, label="origin language quota row"
        )
    for row in manifest["topic_quota_counts"]:
        _require_exact_fields(
            row, TOPIC_QUOTA_COUNT_FIELDS, label="origin topic quota row"
        )
    _require_canonical_equal(
        manifest["language_quota_counts"],
        expected_languages,
        label=f"origin language quotas {persona_id}/{origin}",
        max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
    )
    _require_canonical_equal(
        manifest["topic_quota_counts"],
        expected_topics,
        label=f"origin topic quotas {persona_id}/{origin}",
        max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
    )

    assignment_rows = manifest["fact_profile_assignment_counts"]
    if type(assignment_rows) is not list or not assignment_rows:
        _fail("origin fact-profile assignment counts must be a non-empty list")
    previous_id = None
    assignment_total = 0
    known_profiles = catalog_projection["fact_profiles"]["by_id"]
    for row in assignment_rows:
        _require_exact_fields(
            row,
            FACT_PROFILE_ASSIGNMENT_COUNT_FIELDS,
            label="origin fact-profile assignment-count row",
        )
        profile_id = row["fact_profile_id"]
        count = _require_exact_int(
            row["source_count"], label="fact-profile source count", minimum=1
        )
        profile = known_profiles.get(profile_id)
        if profile is None or profile["persona_id"] != persona_id:
            _fail("origin assignment count references a foreign fact profile")
        if previous_id is not None and _ascii_key(previous_id) >= _ascii_key(profile_id):
            _fail("origin fact-profile assignment rows are not strictly ASCII sorted")
        previous_id = profile_id
        assignment_total += count
    if assignment_total != _origin_source_count(persona_id, origin):
        _fail("origin fact-profile assignment counts do not close source total")

    summary = manifest["summary"]
    _require_exact_fields(summary, ORIGIN_SUMMARY_FIELDS, label="origin summary")
    fixed_summary = {
        "compact_anchor_row_count": len(projection["expected_anchor_rows"]),
        "compact_conflict_pair_row_count": len(projection["expected_conflict_rows"]),
        "compact_range_receipt_row_count": len(descriptors),
        "component_count": len(projection["components"]),
        "maximum_component_source_count": max(map(len, projection["components"])),
        "source_count": _origin_source_count(persona_id, origin),
        "source_shard_count": len(descriptors),
    }
    for key, expected in fixed_summary.items():
        if summary.get(key) != expected:
            _fail(f"source semantic origin summary field drifted: {key}")
    for key in (
        "expanded_content_context_body_bytes",
        "expanded_fact_membership_body_bytes",
        "present_fact_reference_count",
    ):
        _require_exact_int(summary.get(key), label=f"origin summary {key}")
    for key in (
        "maximum_expanded_content_context_row_bytes_including_lf",
        "maximum_expanded_fact_membership_row_bytes_including_lf",
    ):
        _require_exact_int(
            summary.get(key),
            label=f"origin summary {key}",
            minimum=1,
            maximum=MAX_EXPANDED_ROW_BYTES_INCLUDING_LF,
        )
    for key in (
        "maximum_expanded_content_context_shard_body_bytes",
        "maximum_expanded_fact_membership_shard_body_bytes",
    ):
        _require_exact_int(
            summary.get(key),
            label=f"origin summary {key}",
            minimum=1,
            maximum=MAX_EXPANDED_SHARD_BODY_BYTES,
        )
    _require_canonical_equal(
        summary["semantic_version_source_counts"],
        {
            "v1": _origin_source_count(persona_id, origin)
            - len(projection["near_revision_derivatives"]),
            "v2": len(projection["near_revision_derivatives"]),
        },
        label=f"origin semantic version counts {persona_id}/{origin}",
        max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
    )
    expected_sha_paths = frozenset(
        {
            ("body_descriptor", "body_sha256"),
            ("input_bindings", "[]", "sha256"),
        }
    )
    if _sha256_paths(manifest) != expected_sha_paths:
        _fail("source semantic origin SHA dependency paths drifted")
    return raw


def _sum_count_rows(manifests, field, label_field):
    result = {}
    for manifest in manifests:
        for row in manifest[field]:
            label = row[label_field]
            result[label] = result.get(label, 0) + row["source_count"]
    return result


def _semantic_manifest_binding(name, role, manifest, coordinate_fields):
    return _coordinate_binding(
        name,
        role,
        manifest,
        canonical=lambda value: _canonical_bytes(
            value,
            label=f"{name} binding target",
            max_bytes=(
                MAX_ORIGIN_MANIFEST_BYTES
                if "origin" in name
                else MAX_PROFILE_MANIFEST_BYTES
            ),
        ),
        coordinate_fields=coordinate_fields,
    )


def _expected_profile_manifest(
    persona_id, profile, *, catalog, origin_by_key
):
    if profile not in PROFILE_ORDER:
        _fail(f"unknown semantic membership profile: {profile!r}")
    origin_order = ("pilot",) if profile == "pilot" else ORIGIN_ORDER
    origins = [origin_by_key[(persona_id, origin)] for origin in origin_order]
    origin_bindings = [
        _semantic_manifest_binding(
            "persona-v2-source-semantic-membership-origin-manifest",
            "immutable-source-semantic-origin-owner",
            manifest,
            ("persona_id", "origin"),
        )
        for manifest in origins
    ]
    catalog_binding = _coordinate_binding(
        "persona-v2-source-semantic-membership-catalog",
        "semantic-profile-topic-and-fact-profile-owner",
        catalog,
        canonical=lambda value: _canonical_bytes(
            value, label="semantic catalog binding target", max_bytes=MAX_CATALOG_BYTES
        ),
    )
    profile_counts = _sum_count_rows(
        origins, "fact_profile_assignment_counts", "fact_profile_id"
    )
    language_counts = _sum_count_rows(origins, "language_quota_counts", "language")
    topic_counts = _sum_count_rows(origins, "topic_quota_counts", "topic_id")
    source_count = sum(row["summary"]["source_count"] for row in origins)
    value = {
        "artifact_kind": PROFILE_ARTIFACT_KIND,
        "artifact_schema": PROFILE_ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {field: False for field in sorted(AUTHORITY_FIELDS)},
        "canonical_limits": {
            "max_manifest_bytes": MAX_PROFILE_MANIFEST_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "catalog_binding": catalog_binding,
        "completion_claims": {
            "all_profile_content_contexts_bound": True,
            "all_profile_present_fact_sets_bound": True,
            "formal_complete_persona_package_cap_proved": False,
            "full_profile_exact_pilot_origin_reuse_proved": profile == "full",
            "pilot_profile_single_origin_bound": profile == "pilot",
            "source_inventory_rows_modified": False,
        },
        "completion_scope": (
            "one-persona-pilot-or-full-w0-source-semantic-membership-"
            "composition-with-exact-pilot-reuse-no-render-no-solver-no-history-"
            "no-execution-no-g0"
        ),
        "dependency_direction_contract": {
            "full_profile_origin_order_is_pilot_then-full-residual": True,
            "full_profile_must_reuse_exact_pilot_origin_manifest": True,
            "origin_manifests_are_strictly_upstream": True,
            "profile_may_bind_future_execution_artifact": False,
        },
        "fact_profile_assignment_counts": [
            {"fact_profile_id": label, "source_count": count}
            for label, count in sorted(
                profile_counts.items(), key=lambda item: _ascii_key(item[0])
            )
        ],
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "hypothesis_status": "authored-benchmark-stress-design-not-observed-user-statistics",
        "language_quota_counts": [
            {"language": label, "source_count": count}
            for label, count in sorted(
                language_counts.items(), key=lambda item: _ascii_key(item[0])
            )
        ],
        "origin_manifest_bindings": origin_bindings,
        "origin_order": list(origin_order),
        "persona_id": persona_id,
        "profile": profile,
        "remaining_blockers": [
            "formal-source-recipes-and-renderer-validator-implementations",
            "concrete-overlay-materialization",
            "history-checkpoint-membership",
            "scope-placement-allocation-and-proof",
            "render-write-chunk-observation-and-kcs-execution",
            "future-complete-persona-package-cap-proof",
        ],
        "summary": {
            "compact_body_bytes": sum(
                row["body_descriptor"]["body_bytes"] for row in origins
            ),
            "compact_row_count": sum(
                row["body_descriptor"]["row_count"] for row in origins
            ),
            "expanded_content_context_body_bytes": sum(
                row["summary"]["expanded_content_context_body_bytes"]
                for row in origins
            ),
            "expanded_fact_membership_body_bytes": sum(
                row["summary"]["expanded_fact_membership_body_bytes"]
                for row in origins
            ),
            "origin_manifest_count": len(origins),
            "present_fact_reference_count": sum(
                row["summary"]["present_fact_reference_count"] for row in origins
            ),
            "semantic_version_source_counts": {
                version: sum(
                    row["summary"]["semantic_version_source_counts"][version]
                    for row in origins
                )
                for version in ("v1", "v2")
            },
            "source_count": source_count,
            "source_shard_count": sum(
                row["summary"]["source_shard_count"] for row in origins
            ),
        },
        "topic_quota_counts": [
            {"source_count": count, "topic_id": label}
            for label, count in sorted(
                topic_counts.items(), key=lambda item: _ascii_key(item[0])
            )
        ],
    }
    if source_count != envelope.profile_file_count(persona_id, profile):
        _fail("semantic profile source count differs from the frozen persona total")
    return value


def _prevalidate_profile_manifest(
    manifest, *, persona_id, profile, catalog, origin_by_key
):
    raw = _canonical_bytes(
        manifest,
        label="persona v2 source semantic membership profile manifest",
        max_bytes=MAX_PROFILE_MANIFEST_BYTES,
    )
    _require_exact_fields(
        manifest, PROFILE_TOP_LEVEL_FIELDS, label="source semantic profile manifest"
    )
    _reject_prohibited_fields(manifest)
    _validate_common_envelope(
        manifest,
        kind=PROFILE_ARTIFACT_KIND,
        schema=PROFILE_ARTIFACT_SCHEMA,
        label="source semantic profile manifest",
    )
    if manifest.get("persona_id") != persona_id or manifest.get("profile") != profile:
        _fail("source semantic profile manifests are not in persona/profile order")
    expected = _expected_profile_manifest(
        persona_id, profile, catalog=catalog, origin_by_key=origin_by_key
    )
    _require_exact_fields(expected["summary"], PROFILE_SUMMARY_FIELDS, label="profile summary")
    _require_canonical_equal(
        manifest,
        expected,
        label=f"source semantic profile manifest {persona_id}/{profile}",
        max_bytes=MAX_PROFILE_MANIFEST_BYTES,
    )
    expected_sha_paths = frozenset(
        {
            ("catalog_binding", "sha256"),
            ("origin_manifest_bindings", "[]", "sha256"),
        }
    )
    if _sha256_paths(manifest) != expected_sha_paths:
        _fail("source semantic profile SHA dependency paths drifted")
    return raw


def _expected_suite_descriptor(
    *,
    catalog,
    source_suite,
    origin_manifests,
    profile_manifests,
    catalog_projection,
):
    reservation_suite = reservation_layout.build_overlay_reservation_suite()
    try:
        reservation_layout.validate_overlay_reservation_suite(reservation_suite)
    except reservation_layout.PersonaV2OverlayReservationError as error:
        _fail(str(error))
    origins = list(origin_manifests)
    profiles = list(profile_manifests)
    origin_bindings = [
        _semantic_manifest_binding(
            "persona-v2-source-semantic-membership-origin-manifest",
            "source-semantic-origin-owner",
            manifest,
            ("persona_id", "origin"),
        )
        for manifest in origins
    ]
    profile_bindings = [
        _semantic_manifest_binding(
            "persona-v2-source-semantic-membership-profile-manifest",
            "source-semantic-profile-composition",
            manifest,
            ("persona_id", "profile"),
        )
        for manifest in profiles
    ]
    catalog_binding = _coordinate_binding(
        "persona-v2-source-semantic-membership-catalog",
        "semantic-profile-topic-and-fact-profile-owner",
        catalog,
        canonical=lambda value: _canonical_bytes(
            value, label="semantic catalog binding target", max_bytes=MAX_CATALOG_BYTES
        ),
    )
    input_bindings = [
        _coordinate_binding(
            "persona-v2-source-inventory-suite",
            "global-immutable-source-inventory",
            source_suite,
            canonical=lambda value: _canonical_bytes(
                value,
                label="source inventory suite binding target",
                max_bytes=source_validator.MAX_SUITE_DESCRIPTOR_BYTES,
            ),
        ),
        _coordinate_binding(
            "persona-v2-overlay-reservation-suite",
            "global-overlay-reservation-index",
            reservation_suite,
            canonical=reservation_layout.overlay_reservation_suite_bytes,
        ),
    ]

    profile_kind_by_id = {
        profile_id: row["profile_kind"]
        for profile_id, row in catalog_projection["fact_profiles"]["by_id"].items()
    }
    kind_counts = {
        kind: 0
        for kind in (
            "empty",
            "graph-normal-w0",
            "w0-singleton",
            "conflict-branch",
        )
    }
    for manifest in origins:
        for row in manifest["fact_profile_assignment_counts"]:
            kind = profile_kind_by_id.get(row["fact_profile_id"])
            if kind is None:
                _fail("suite origin assignment references a foreign fact profile")
            kind_counts[kind] += row["source_count"]

    if type(source_suite) is not dict:
        _fail("bound source suite must be an object")
    source_ledger_rows = source_suite.get("persona_current_component_byte_ledgers")
    if type(source_ledger_rows) is not list:
        _fail("bound source suite has no persona component ledgers")
    source_ledgers = {}
    for row in source_ledger_rows:
        if type(row) is not dict or type(row.get("persona_id")) is not str:
            _fail("bound source suite component ledger is malformed")
        source_ledgers[row["persona_id"]] = row
    if tuple(source_ledgers) != envelope.PERSONA_IDS:
        _fail("bound source suite component ledger persona order drifted")
    reservation_origin_bindings = reservation_suite.get("origin_bindings")
    if type(reservation_origin_bindings) is not list:
        _fail("reservation suite has no origin bindings")
    reservation_bytes = {persona_id: 0 for persona_id in envelope.PERSONA_IDS}
    for binding in reservation_origin_bindings:
        persona_id = binding.get("persona_id") if type(binding) is dict else None
        if persona_id not in reservation_bytes:
            _fail("reservation suite origin binding references a foreign persona")
        reservation_bytes[persona_id] += _require_exact_int(
            binding.get("canonical_bytes"),
            label="reservation origin canonical bytes",
            minimum=1,
        )
    origin_by_persona = {
        persona_id: [row for row in origins if row["persona_id"] == persona_id]
        for persona_id in envelope.PERSONA_IDS
    }
    profile_by_persona = {
        persona_id: [row for row in profiles if row["persona_id"] == persona_id]
        for persona_id in envelope.PERSONA_IDS
    }
    catalog_bytes = len(
        _canonical_bytes(
            catalog, label="semantic catalog ledger", max_bytes=MAX_CATALOG_BYTES
        )
    )
    ledgers = []
    for persona_id in envelope.PERSONA_IDS:
        persona_origins = origin_by_persona[persona_id]
        persona_profiles = profile_by_persona[persona_id]
        if len(persona_origins) != 2 or len(persona_profiles) != 2:
            _fail("suite persona manifest composition is incomplete")
        compact_body_bytes = sum(
            row["body_descriptor"]["body_bytes"] for row in persona_origins
        )
        semantic_origin_manifest_bytes = sum(
            len(
                _canonical_bytes(
                    row,
                    label="semantic origin ledger target",
                    max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
                )
            )
            for row in persona_origins
        )
        semantic_profile_manifest_bytes = sum(
            len(
                _canonical_bytes(
                    row,
                    label="semantic profile ledger target",
                    max_bytes=MAX_PROFILE_MANIFEST_BYTES,
                )
            )
            for row in persona_profiles
        )
        source_ledger = source_ledgers[persona_id]
        existing_source_component_bytes = _require_exact_int(
            source_ledger.get("current_component_bytes"),
            label="source inventory current component bytes",
            minimum=1,
        )
        current = (
            existing_source_component_bytes
            + reservation_bytes[persona_id]
            + catalog_bytes
            + compact_body_bytes
            + semantic_origin_manifest_bytes
            + semantic_profile_manifest_bytes
        )
        if current > MAX_PERSONA_PACKAGE_BYTES:
            _fail(f"semantic current component exceeds 16 MiB for {persona_id}")
        ledgers.append(
            {
                "catalog_bytes_conservatively_charged_in_full": catalog_bytes,
                "compact_semantic_origin_body_bytes": compact_body_bytes,
                "current_component_bytes": current,
                "current_component_cap_satisfied": True,
                "existing_source_inventory_component_bytes": existing_source_component_bytes,
                "formal_complete_persona_package_cap_proved": False,
                "headroom_bytes": MAX_PERSONA_PACKAGE_BYTES - current,
                "matching_reservation_origin_bytes": reservation_bytes[persona_id],
                "max_current_component_bytes": MAX_PERSONA_PACKAGE_BYTES,
                "persona_id": persona_id,
                "semantic_origin_manifest_bytes": semantic_origin_manifest_bytes,
                "semantic_profile_manifest_bytes": semantic_profile_manifest_bytes,
            }
        )

    semantic_version_counts = {
        version: sum(
            row["summary"]["semantic_version_source_counts"][version]
            for row in origins
        )
        for version in ("v1", "v2")
    }
    value = {
        "artifact_kind": SUITE_ARTIFACT_KIND,
        "artifact_schema": SUITE_ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {field: False for field in sorted(AUTHORITY_FIELDS)},
        "canonical_limits": {
            "max_body_bytes": MAX_SUITE_DESCRIPTOR_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_persona_current_component_bytes": MAX_PERSONA_PACKAGE_BYTES,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "catalog_binding": catalog_binding,
        "completion_claims": {
            "all_203000_content_context_ids_resolved": True,
            "all_203000_present_fact_set_keys_resolved": True,
            "all_40_origin_manifests_bound": True,
            "all_40_profile_manifests_bound": True,
            "all_73_source_shard_expansion_receipts_bound": True,
            "current_semantic_membership_component_cap_satisfied": True,
            "formal_complete_persona_package_cap_proved": False,
            "full_profiles_exactly_reuse_pilot_origins": True,
            "source_inventory_rows_modified": False,
        },
        "completion_scope": (
            "all-203000-w0-source-semantic-contexts-and-owned-fact-memberships-"
            "with-compact-owner-bodies-and-streaming-receipts-no-render-no-"
            "solver-no-history-no-execution-no-g0"
        ),
        "dependency_direction_contract": {
            "catalog_and_origin_manifests_are_strictly_upstream": True,
            "global_source_and_reservation_suites_are_directly_bound": True,
            "profile_manifests_compose_without_regeneration": True,
            "suite_may_bind_future_execution_artifact": False,
        },
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "hypothesis_status": "authored-benchmark-stress-design-not-observed-user-statistics",
        "input_binding_order": [row["name"] for row in input_bindings],
        "input_bindings": input_bindings,
        "orders": {
            "compact_origin_rows": (
                "source-shard-total-projection-then-fact-semantic-anchor-"
                "override-then-fact-conflict-pair-override"
            ),
            "origin": list(ORIGIN_ORDER),
            "origin_manifests": "persona-then-origin",
            "persona": list(envelope.PERSONA_IDS),
            "profile": list(PROFILE_ORDER),
            "profile_manifests": "persona-then-profile",
        },
        "origin_manifest_bindings": origin_bindings,
        "persona_current_component_byte_ledgers": ledgers,
        "profile_manifest_bindings": profile_bindings,
        "remaining_blockers": [
            "formal-source-recipes-and-missing-renderer-validator-implementations",
            "concrete-logical-overlay-materialization",
            "history-and-checkpoint-transition-membership",
            "scope-placement-allocation-and-proof",
            "render-write-chunk-observation-and-kcs-execution",
            "future-complete-persona-package-cap-proof",
        ],
        "summary": {
            "compact_anchor_row_count": sum(
                row["summary"]["compact_anchor_row_count"] for row in origins
            ),
            "compact_body_bytes": sum(
                row["body_descriptor"]["body_bytes"] for row in origins
            ),
            "compact_conflict_pair_row_count": sum(
                row["summary"]["compact_conflict_pair_row_count"] for row in origins
            ),
            "compact_range_receipt_row_count": sum(
                row["summary"]["compact_range_receipt_row_count"] for row in origins
            ),
            "compact_row_count": sum(
                row["body_descriptor"]["row_count"] for row in origins
            ),
            "expanded_content_context_body_bytes": sum(
                row["summary"]["expanded_content_context_body_bytes"]
                for row in origins
            ),
            "expanded_fact_membership_body_bytes": sum(
                row["summary"]["expanded_fact_membership_body_bytes"]
                for row in origins
            ),
            "fact_profile_kind_source_counts": kind_counts,
            "maximum_compact_row_bytes_including_lf": max(
                row["body_descriptor"]["maximum_row_bytes_including_lf"]
                for row in origins
            ),
            "maximum_component_source_count": max(
                row["summary"]["maximum_component_source_count"] for row in origins
            ),
            "maximum_expanded_content_context_row_bytes_including_lf": max(
                row["summary"]["maximum_expanded_content_context_row_bytes_including_lf"]
                for row in origins
            ),
            "maximum_expanded_content_context_shard_body_bytes": max(
                row["summary"]["maximum_expanded_content_context_shard_body_bytes"]
                for row in origins
            ),
            "maximum_expanded_fact_membership_row_bytes_including_lf": max(
                row["summary"]["maximum_expanded_fact_membership_row_bytes_including_lf"]
                for row in origins
            ),
            "maximum_expanded_fact_membership_shard_body_bytes": max(
                row["summary"]["maximum_expanded_fact_membership_shard_body_bytes"]
                for row in origins
            ),
            "origin_manifest_count": len(origins),
            "present_fact_reference_count": sum(
                row["summary"]["present_fact_reference_count"] for row in origins
            ),
            "profile_manifest_count": len(profiles),
            "semantic_version_source_counts": semantic_version_counts,
            "source_count": sum(row["summary"]["source_count"] for row in origins),
            "source_shard_count": sum(
                row["summary"]["source_shard_count"] for row in origins
            ),
        },
    }
    return value


def _prevalidate_suite_descriptor(
    suite,
    *,
    catalog,
    source_suite,
    origin_manifests,
    profile_manifests,
    catalog_projection,
):
    raw = _canonical_bytes(
        suite,
        label="persona v2 source semantic membership suite",
        max_bytes=MAX_SUITE_DESCRIPTOR_BYTES,
    )
    _require_exact_fields(
        suite, SUITE_TOP_LEVEL_FIELDS, label="source semantic membership suite"
    )
    _reject_prohibited_fields(suite)
    _validate_common_envelope(
        suite,
        kind=SUITE_ARTIFACT_KIND,
        schema=SUITE_ARTIFACT_SCHEMA,
        label="source semantic membership suite",
    )
    expected = _expected_suite_descriptor(
        catalog=catalog,
        source_suite=source_suite,
        origin_manifests=origin_manifests,
        profile_manifests=profile_manifests,
        catalog_projection=catalog_projection,
    )
    for ledger in expected["persona_current_component_byte_ledgers"]:
        _require_exact_fields(
            ledger, PERSONA_COMPONENT_LEDGER_FIELDS, label="persona component ledger"
        )
    _require_exact_fields(expected["summary"], SUITE_SUMMARY_FIELDS, label="suite summary")
    _require_canonical_equal(
        suite,
        expected,
        label="source semantic membership suite",
        max_bytes=MAX_SUITE_DESCRIPTOR_BYTES,
    )
    expected_sha_paths = frozenset(
        {
            ("catalog_binding", "sha256"),
            ("input_bindings", "[]", "sha256"),
            ("origin_manifest_bindings", "[]", "sha256"),
            ("profile_manifest_bindings", "[]", "sha256"),
        }
    )
    if _sha256_paths(suite) != expected_sha_paths:
        _fail("source semantic suite SHA dependency paths drifted")
    if (
        len(raw) != EXPECTED_SUITE_DESCRIPTOR_BYTES
        or hashlib.sha256(raw).hexdigest() != EXPECTED_SUITE_SHA256
    ):
        _fail("semantic suite canonical bytes or frozen SHA-256 drifted")
    return raw


def _clear_upstream_working_caches():
    """Release derivation caches; none of them are part of artifact identity."""

    for module, names in (
        (
            reservation_layout,
            (
                "_attachment_host_count",
                "_canonical_origin",
                "_canonical_suite",
                "_intent_slot_tuples_by_variant",
                "_persona_layout",
                "_persona_targets",
                "_shared_inputs",
                "_variant_roles",
            ),
        ),
        (
            reservation_validator,
            (
                "_expected_conflict_inputs",
                "_expected_fact_graph_binding",
                "_pilot_host_count",
                "_source_domain",
                "_upstream_inputs",
            ),
        ),
        (
            source_validator,
            ("_reservation_inputs", "_upstream_inputs", "_variant_ranges"),
        ),
    ):
        for name in names:
            clear = getattr(getattr(module, name, None), "cache_clear", None)
            if callable(clear):
                clear()
    _expected_fact_profile_semantics.cache_clear()
    _validated_base_inputs.cache_clear()


class _DisjointSet:
    def __init__(self, values):
        self._parent = {value: value for value in values}

    def find(self, value):
        parent = self._parent.get(value)
        if parent is None:
            _fail(f"reservation references a foreign source intent: {value}")
        while parent != self._parent[parent]:
            self._parent[parent] = self._parent[self._parent[parent]]
            parent = self._parent[parent]
        while value != parent:
            next_value = self._parent[value]
            self._parent[value] = parent
            value = next_value
        return parent

    def union(self, left, right):
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if _ascii_key(left_root) <= _ascii_key(right_root):
            self._parent[right_root] = left_root
        else:
            self._parent[left_root] = right_root

    def components(self):
        result = {}
        for value in self._parent:
            result.setdefault(self.find(value), []).append(value)
        rows = []
        for members in result.values():
            members.sort(key=_ascii_key)
            rows.append(tuple(members))
        rows.sort(key=lambda members: _ascii_key(members[0]))
        return rows


def _hamilton(total, weights):
    """Allocate an exact integer total using ASCII-tied largest remainders."""

    _require_exact_int(total, label="Hamilton total")
    if type(weights) is not dict or not weights:
        _fail("Hamilton weights must be a non-empty object")
    labels = sorted(weights, key=_ascii_key)
    if any(type(weights[label]) is not int or weights[label] < 0 for label in labels):
        _fail("Hamilton weights must be non-negative exact integers")
    denominator = sum(weights.values())
    if denominator <= 0:
        _fail("Hamilton weight denominator must be positive")
    result = {
        label: total * weights[label] // denominator
        for label in labels
    }
    remaining = total - sum(result.values())
    remainder_order = sorted(
        labels,
        key=lambda label: (
            -(total * weights[label] % denominator),
            _ascii_key(label),
        ),
    )
    for label in remainder_order[:remaining]:
        result[label] += 1
    if sum(result.values()) != total:
        _fail("Hamilton allocation lost mass")
    return result


def _origin_targets(pilot_count, full_count, weights):
    pilot = _hamilton(pilot_count, weights)
    full = _hamilton(full_count, weights)
    residual = {label: full[label] - pilot[label] for label in full}
    if any(value < 0 for value in residual.values()):
        _fail("full-minus-pilot Hamilton target became negative")
    if sum(residual.values()) != full_count - pilot_count:
        _fail("full-minus-pilot Hamilton target lost mass")
    return {"pilot": pilot, "full": full, "full-residual": residual}


def _assign_components(components, targets, fixed_labels):
    """Independently repeat the fixed-first deficit allocator."""

    if type(targets) is not dict or not targets:
        _fail("component targets must be a non-empty object")
    labels = sorted(targets, key=_ascii_key)
    total = sum(targets.values())
    if any(type(value) is not int or value < 0 for value in targets.values()):
        _fail("component targets must be non-negative exact integers")
    by_key = {members[0]: members for members in components}
    component_for_intent = {
        intent_key: members[0]
        for members in components
        for intent_key in members
    }
    if sum(len(members) for members in components) != total:
        _fail("component partition does not equal the target total")
    fixed_by_component = {}
    for intent_key, label in fixed_labels.items():
        if label not in targets:
            _fail(f"fixed assignment references a foreign label: {label}")
        component_key = component_for_intent.get(intent_key)
        if component_key is None:
            _fail(f"fixed assignment does not resolve exactly once: {intent_key}")
        previous = fixed_by_component.setdefault(component_key, label)
        if previous != label:
            _fail(f"component has conflicting fixed labels: {component_key}")

    fixed_components = sorted(
        (
            (by_key[key], label)
            for key, label in fixed_by_component.items()
        ),
        key=lambda row: (-len(row[0]), _ascii_key(row[0][0])),
    )
    free_components = sorted(
        (
            members
            for key, members in by_key.items()
            if key not in fixed_by_component
        ),
        key=lambda members: (-len(members), _ascii_key(members[0])),
    )

    assigned = {label: 0 for label in labels}
    assignment = {}
    processed = 0

    def apply(members, label):
        nonlocal processed
        size = len(members)
        if targets[label] - assigned[label] < size:
            _fail(f"fixed/selected component exceeds target capacity: {label}")
        for intent_key in members:
            if intent_key in assignment:
                _fail(f"component assignment is not disjoint: {intent_key}")
            assignment[intent_key] = label
        assigned[label] += size
        processed += size

    for members, label in fixed_components:
        apply(members, label)
    for members in free_components:
        size = len(members)
        next_processed = processed + size
        candidates = [
            label for label in labels if targets[label] - assigned[label] >= size
        ]
        if not candidates:
            _fail(f"component allocator has no remaining label for {members[0]}")
        chosen = min(
            candidates,
            key=lambda label: (
                -(targets[label] * next_processed - assigned[label] * total),
                _ascii_key(label),
            ),
        )
        apply(members, chosen)
    if processed != total or assigned != targets or len(assignment) != total:
        _fail("component allocator did not close its exact targets")
    return assignment


def _origin_layout(persona_id, origin):
    row = _validated_base_inputs()["persona_layouts"][persona_id]
    shards = [candidate for candidate in row["shards"] if candidate["origin"] == origin]
    if not shards:
        _fail(f"source layout has no shards for {persona_id}/{origin}")
    return shards


def _origin_source_count(persona_id, origin):
    row = _validated_base_inputs()["persona_layouts"][persona_id]
    return (
        row["pilot_source_count"]
        if origin == "pilot"
        else row["full_residual_source_count"]
    )


def _source_intent_keys(persona_id, origin):
    return [
        source_layout.intent_key(persona_id, origin, ordinal)
        for ordinal in range(1, _origin_source_count(persona_id, origin) + 1)
    ]


def _semantic_identity_projection(identity):
    fields = (
        "logical_branch_key",
        "logical_document_key",
        "logical_revision_key",
        "payload_equivalence_key",
        "semantic_section_key",
    )
    if type(identity) is not dict or set(identity) != set(fields):
        _fail("overlay semantic identity field set drifted")
    return {field: identity[field] for field in fields}


def _origin_reservation_projection(persona_id, origin, profile_index):
    """Build one compact independently checked reservation/source projection."""

    artifact = reservation_layout.build_overlay_reservation_origin(persona_id, origin)
    try:
        reservation_validator.validate_overlay_reservation_origin(artifact)
    except reservation_validator.PersonaV2OverlayReservationValidationError as error:
        _fail(str(error))
    source_keys = _source_intent_keys(persona_id, origin)
    source_key_set = set(source_keys)
    disjoint = _DisjointSet(source_keys)
    anchor_by_key = {}
    identity_by_key = {}
    relation_by_key = {}
    container_roles = {key: set() for key in source_keys}
    conflict_profile_by_key = {}
    fixed_topic_by_key = {}
    near_revision_derivatives = set()
    overlay_keys = set()

    graph_value = _validated_base_inputs()["fact_graph_by_persona"][persona_id]
    graphs = sorted(graph_value["graphs"], key=lambda row: _ascii_key(row["graph_id"]))
    graph_slot_by_id = {row["graph_id"]: index for index, row in enumerate(graphs)}
    current_by_graph = {
        graph["graph_id"]: sorted(
            (
                row["fact_id"]
                for row in graph["facts"]
                if _fact_state_at_checkpoint(row, "W0") == "current"
            ),
            key=_ascii_key,
        )
        for graph in graphs
    }
    singleton_semantics = [
        ("w0-singleton", graph["graph_id"], current_by_graph[graph["graph_id"]][fact_index])
        for fact_index in range(8)
        for graph in graphs
    ]
    if len(singleton_semantics) != 32:
        _fail("semantic anchor singleton cycle must contain exact 32 profiles")

    expected_anchor_rows = []
    for slot in artifact["semantic_anchor_slots"]:
        intent_key = slot["intent_key"]
        if intent_key not in source_key_set or intent_key in anchor_by_key:
            _fail(f"semantic anchor is duplicate or foreign: {intent_key}")
        ordinal = slot["semantic_anchor_slot_ordinal"]
        _require_exact_int(ordinal, label="semantic anchor slot ordinal", minimum=1)
        semantic_key = singleton_semantics[(ordinal - 1) % len(singleton_semantics)]
        profile_id = profile_index[(persona_id,) + semantic_key]
        graph_id = semantic_key[1]
        anchor_by_key[intent_key] = {
            "fact_profile_id": profile_id,
            "semantic_anchor_slot_ordinal": ordinal,
        }
        fixed_topic_by_key[intent_key] = graph_id
        expected_anchor_rows.append(
            {
                "fact_profile_id": profile_id,
                "intent_key": intent_key,
                "row_kind": "fact-semantic-anchor-override",
                "semantic_anchor_slot_ordinal": ordinal,
            }
        )

    expected_conflict_rows = []

    def bind_identity(intent_key, identity):
        projected = _semantic_identity_projection(identity)
        previous = identity_by_key.setdefault(intent_key, projected)
        if previous != projected:
            _fail(f"reservation semantic identity disagrees for {intent_key}")
        overlay_keys.add(intent_key)

    for row in artifact["reservation_rows"]:
        row_kind = row["row_kind"]
        if row_kind == "content-relation-reservation":
            anchor_key = row["anchor_intent_key"]
            derivative_key = row["derivative_intent_key"]
            disjoint.union(anchor_key, derivative_key)
            relation_kind = row["relation_kind"]
            bind_identity(anchor_key, row["anchor_identity"])
            bind_identity(derivative_key, row["derivative_identity"])
            relation_prefix = {
                "exact-duplicate": "exact",
                "near-revision": "near",
                "conflict-copy": "conflict",
            }.get(relation_kind)
            if relation_prefix is None:
                _fail(f"unknown content relation kind: {relation_kind!r}")
            for intent_key, role in (
                (anchor_key, f"{relation_prefix}-anchor"),
                (derivative_key, f"{relation_prefix}-derivative"),
            ):
                previous = relation_by_key.setdefault(intent_key, role)
                if previous != role:
                    _fail(f"source has multiple content-relation roles: {intent_key}")
            if relation_kind == "near-revision":
                near_revision_derivatives.add(derivative_key)
            if relation_kind == "conflict-copy":
                binding = row["conflict_fact_binding"]
                graph_id = binding["graph_id"]
                if graph_id not in graph_slot_by_id:
                    _fail("conflict reservation references a foreign graph")
                anchor_profile = profile_index[
                    (persona_id, "conflict-branch", graph_id, "a")
                ]
                derivative_profile = profile_index[
                    (persona_id, "conflict-branch", graph_id, "b")
                ]
                semantics = _expected_fact_profile_semantics(persona_id)
                branch_a = semantics[("conflict-branch", graph_id, "a")]
                branch_b = semantics[("conflict-branch", graph_id, "b")]
                if (
                    branch_a["present_fact_ids"]
                    != binding["branch_a_present_fact_ids"]
                    or branch_b["present_fact_ids"]
                    != binding["branch_b_present_fact_ids"]
                    or branch_a["conflict_set_id"] != binding["conflict_set_id"]
                    or branch_b["conflict_set_id"] != binding["conflict_set_id"]
                    or branch_a["conflict_template_key"] != binding["template_key"]
                    or branch_b["conflict_template_key"] != binding["template_key"]
                ):
                    _fail("conflict reservation and exact branch profiles disagree")
                conflict_profile_by_key[anchor_key] = anchor_profile
                conflict_profile_by_key[derivative_key] = derivative_profile
                fixed_topic_by_key[anchor_key] = graph_id
                fixed_topic_by_key[derivative_key] = graph_id
                expected_conflict_rows.append(
                    {
                        "anchor_fact_profile_id": anchor_profile,
                        "anchor_intent_key": anchor_key,
                        "cluster_key": row["cluster_key"],
                        "derivative_fact_profile_id": derivative_profile,
                        "derivative_intent_key": derivative_key,
                        "row_kind": "fact-conflict-pair-override",
                    }
                )
        elif row_kind == "attachment-membership-reservation":
            host_key = row["host_intent_key"]
            member_key = row["standalone_member_intent_key"]
            disjoint.union(host_key, member_key)
            bind_identity(host_key, row["host_identity"])
            bind_identity(member_key, row["standalone_member_identity"])
            container_roles[host_key].add("attachment-host")
            container_roles[member_key].add("attachment-member")
        else:
            _fail(f"unknown overlay reservation row kind: {row_kind!r}")

    components = disjoint.components()
    if max(map(len, components)) > 7:
        _fail("reservation connected component exceeds the fixed maximum of seven")
    for intent_key, graph_id in fixed_topic_by_key.items():
        if intent_key not in source_key_set or graph_id not in graph_slot_by_id:
            _fail("fixed topic assignment is outside the origin domain")

    persona_layout = _validated_base_inputs()["persona_layouts"][persona_id]
    pilot_count = persona_layout["pilot_source_count"]
    full_count = persona_layout["full_source_count"]
    topic_weights = {graph["graph_id"]: 2_500 for graph in graphs}
    topic_targets = _origin_targets(pilot_count, full_count, topic_weights)[origin]
    topic_assignment = _assign_components(
        components, topic_targets, fixed_topic_by_key
    )
    language_weights = {
        row["language"]: row["weight_bp"]
        for row in _validated_base_inputs()["realism_by_persona"][persona_id][
            "language_weights_bp"
        ]
    }
    language_targets = _origin_targets(
        pilot_count, full_count, language_weights
    )[origin]
    language_assignment = _assign_components(components, language_targets, {})

    if set(anchor_by_key) & overlay_keys:
        _fail("semantic anchors must remain disjoint from overlay references")
    if (
        len(expected_conflict_rows)
        != artifact["target_marginals"]["conflict_copy_cluster_count"]
    ):
        _fail("conflict compact-row cardinality differs from reservation")
    container_roles = {
        key: sorted(roles, key=_ascii_key) for key, roles in container_roles.items()
    }
    return {
        "anchor_by_key": anchor_by_key,
        "artifact": artifact,
        "components": components,
        "conflict_profile_by_key": conflict_profile_by_key,
        "container_roles": container_roles,
        "expected_anchor_rows": expected_anchor_rows,
        "expected_conflict_rows": expected_conflict_rows,
        "identity_by_key": identity_by_key,
        "language_assignment": language_assignment,
        "language_targets": language_targets,
        "near_revision_derivatives": near_revision_derivatives,
        "overlay_keys": overlay_keys,
        "relation_by_key": relation_by_key,
        "topic_assignment": topic_assignment,
        "topic_targets": topic_targets,
    }


def _source_local_identity(source_row):
    context_id = source_row["content_context_id"]
    return {
        "logical_branch_key": f"{context_id}-branch-v2",
        "logical_document_key": f"{context_id}-document-v2",
        "logical_revision_key": f"{context_id}-revision-v2",
        "payload_equivalence_key": source_row["deterministic_payload_seed"],
        "semantic_section_key": f"{context_id}-section-v2",
    }


def _expected_expanded_rows(source_row, origin_projection, catalog_projection):
    _require_exact_fields(
        source_row,
        source_validator.ROW_FIELDS,
        label="validated structural source row",
    )
    intent_key = source_row["intent_key"]
    persona_id = source_row["persona_id"]
    origin = source_row["origin"]
    if (
        persona_id != origin_projection["artifact"]["persona_id"]
        or origin != origin_projection["artifact"]["origin"]
    ):
        _fail("source row escaped its semantic origin projection")
    semantic_profile = catalog_projection["semantic_profiles"]["by_source_id"].get(
        source_row["source_profile_id"]
    )
    if semantic_profile is None:
        _fail("source row references an unknown semantic profile")
    graph_id = origin_projection["topic_assignment"].get(intent_key)
    language = origin_projection["language_assignment"].get(intent_key)
    topic = catalog_projection["topics"]["by_graph"].get((persona_id, graph_id))
    if topic is None or type(language) is not str:
        _fail("source row lacks a total topic/language assignment")

    semantic_index = catalog_projection["fact_profiles"]["semantic_index"]
    fact_profile_id = origin_projection["conflict_profile_by_key"].get(intent_key)
    if fact_profile_id is None:
        anchor = origin_projection["anchor_by_key"].get(intent_key)
        if anchor is not None:
            fact_profile_id = anchor["fact_profile_id"]
        elif semantic_profile["gate_role"] == "raw_only":
            fact_profile_id = semantic_index[(persona_id, "empty", "none", "none")]
        elif semantic_profile["gate_role"] in {
            "contract_contributor",
            "incidental_searchable",
        }:
            fact_profile_id = semantic_index[
                (persona_id, "graph-normal-w0", graph_id, "all")
            ]
        else:
            _fail("semantic source profile exposes an unknown gate role")
    profile = catalog_projection["fact_profiles"]["by_id"].get(fact_profile_id)
    if profile is None or profile["persona_id"] != persona_id:
        _fail("source fact membership references a foreign fact profile")
    if profile["profile_kind"] == "empty":
        if semantic_profile["gate_role"] != "raw_only" or profile["present_fact_ids"]:
            _fail("only raw_only sources may use the exact empty fact profile")
    else:
        if semantic_profile["gate_role"] == "raw_only":
            _fail("raw_only source received evidence-bearing facts")
        if profile["graph_id"] != graph_id or not profile["present_fact_ids"]:
            _fail("source fact profile and assigned semantic topic disagree")

    identity = origin_projection["identity_by_key"].get(intent_key)
    if identity is None:
        identity = _source_local_identity(source_row)
    anchor_capacity = intent_key in origin_projection["anchor_by_key"]
    context = {
        "container_role_ids": origin_projection["container_roles"][intent_key],
        "content_context_id": source_row["content_context_id"],
        "content_relation_role": origin_projection["relation_by_key"].get(
            intent_key, "independent"
        ),
        "deterministic_payload_seed": source_row["deterministic_payload_seed"],
        "intent_key": intent_key,
        "language": language,
        "logical_period_id": "W0",
        "membership_status": "current",
        "origin": origin,
        "payload_equivalence_key": identity["payload_equivalence_key"],
        "persona_id": persona_id,
        "semantic_anchor_capacity": anchor_capacity,
        "semantic_profile_id": semantic_profile["semantic_profile_id"],
        "semantic_version": (
            "v2"
            if intent_key in origin_projection["near_revision_derivatives"]
            else "v1"
        ),
        "topic_id": topic["topic_id"],
    }
    _require_exact_fields(
        context, EXPANDED_CONTEXT_ROW_FIELDS, label="expanded content context row"
    )
    present_fact_ids = list(profile["present_fact_ids"])
    empty = not present_fact_ids
    membership = {
        "fact_profile_id": fact_profile_id,
        "intent_key": intent_key,
        "logical_branch_key": identity["logical_branch_key"],
        "logical_document_key": identity["logical_document_key"],
        "logical_revision_key": identity["logical_revision_key"],
        "origin": origin,
        "persona_id": persona_id,
        "present_fact_ids": present_fact_ids,
        "present_fact_set_key": source_row["present_fact_set_key"],
        "projection_mode": (
            "no-present-facts"
            if empty
            else "all-present-facts-single-semantic-section"
        ),
        "semantic_section_key": (
            "not-applicable-no-present-facts"
            if empty
            else identity["semantic_section_key"]
        ),
    }
    _require_exact_fields(
        membership,
        EXPANDED_MEMBERSHIP_ROW_FIELDS,
        label="expanded fact membership row",
    )
    if present_fact_ids != sorted(set(present_fact_ids), key=_ascii_key):
        _fail("expanded present facts must remain sorted, unique, and exact")
    return context, membership


def _validate_origin_bodies(
    manifest,
    source_manifest,
    origin_projection,
    catalog_projection,
    *,
    compact_origin_body_provider,
    expanded_context_body_provider,
    expanded_membership_body_provider,
    source_shard_body_provider,
):
    persona_id = manifest["persona_id"]
    origin = manifest["origin"]
    expected_range_rows = []
    profile_counts = {}
    profile_kind_counts = {
        "conflict-branch": 0,
        "empty": 0,
        "graph-normal-w0": 0,
        "w0-singleton": 0,
    }
    present_fact_reference_count = 0
    expanded_context_body_bytes = 0
    expanded_membership_body_bytes = 0
    maximum_context_row_bytes = 0
    maximum_membership_row_bytes = 0
    maximum_context_shard_body_bytes = 0
    maximum_membership_shard_body_bytes = 0
    version_counts = {"v1": 0, "v2": 0}
    seen_intent_keys = set()

    descriptors = source_manifest["shard_descriptors"]
    for descriptor in descriptors:
        if (
            descriptor.get("persona_id") != persona_id
            or descriptor.get("origin") != origin
        ):
            _fail("source shard descriptor was rethreaded across semantic origins")
        _source_body, source_rows = _load_source_shard(
            descriptor, source_shard_body_provider
        )
        if not 1 <= len(source_rows) <= MAX_EXPANDED_ROWS_PER_SHARD:
            _fail("expanded semantic shard row count exceeds 4,096")
        context_rows = []
        membership_rows = []
        for source_row in source_rows:
            intent_key = source_row.get("intent_key")
            if intent_key in seen_intent_keys:
                _fail("source semantic expansion encountered a duplicate intent key")
            seen_intent_keys.add(intent_key)
            context, membership = _expected_expanded_rows(
                source_row, origin_projection, catalog_projection
            )
            context_rows.append(context)
            membership_rows.append(membership)
            version_counts[context["semantic_version"]] += 1
            profile_id = membership["fact_profile_id"]
            profile_counts[profile_id] = profile_counts.get(profile_id, 0) + 1
            profile = catalog_projection["fact_profiles"]["by_id"][profile_id]
            profile_kind_counts[profile["profile_kind"]] += 1
            present_fact_reference_count += len(membership["present_fact_ids"])

        context_body, context_maximum = _canonical_jsonl(
            context_rows,
            label=f"expanded content context {persona_id}/{origin}/{descriptor['shard_ordinal']}",
            row_cap=MAX_EXPANDED_ROW_BYTES_INCLUDING_LF,
            body_cap=MAX_EXPANDED_SHARD_BODY_BYTES,
        )
        membership_body, membership_maximum = _canonical_jsonl(
            membership_rows,
            label=f"expanded fact membership {persona_id}/{origin}/{descriptor['shard_ordinal']}",
            row_cap=MAX_EXPANDED_ROW_BYTES_INCLUDING_LF,
            body_cap=MAX_EXPANDED_SHARD_BODY_BYTES,
        )
        coordinates = (persona_id, origin, descriptor["shard_ordinal"])
        provided_context_body = _provider_bytes(
            expanded_context_body_provider,
            coordinates,
            label="expanded content-context shard body",
        )
        provided_membership_body = _provider_bytes(
            expanded_membership_body_provider,
            coordinates,
            label="expanded fact-membership shard body",
        )
        if provided_context_body != context_body:
            _fail("expanded content-context body differs from independent projection")
        if provided_membership_body != membership_body:
            _fail("expanded fact-membership body differs from independent projection")

        expanded_context_body_bytes += len(context_body)
        expanded_membership_body_bytes += len(membership_body)
        maximum_context_row_bytes = max(maximum_context_row_bytes, context_maximum)
        maximum_membership_row_bytes = max(
            maximum_membership_row_bytes, membership_maximum
        )
        maximum_context_shard_body_bytes = max(
            maximum_context_shard_body_bytes, len(context_body)
        )
        maximum_membership_shard_body_bytes = max(
            maximum_membership_shard_body_bytes, len(membership_body)
        )
        receipt = {
            "expanded_content_context_body_bytes": len(context_body),
            "expanded_content_context_max_row_bytes_including_lf": context_maximum,
            "expanded_content_context_sha256": hashlib.sha256(
                context_body
            ).hexdigest(),
            "expanded_fact_membership_body_bytes": len(membership_body),
            "expanded_fact_membership_max_row_bytes_including_lf": membership_maximum,
            "expanded_fact_membership_sha256": hashlib.sha256(
                membership_body
            ).hexdigest(),
            "first_intent_key": descriptor["first_intent_key"],
            "last_intent_key": descriptor["last_intent_key"],
            "row_count": descriptor["row_count"],
            "row_kind": "source-shard-total-projection",
            "source_body_sha256": descriptor["body_sha256"],
            "source_shard_id": descriptor["shard_id"],
        }
        _require_exact_fields(
            receipt, RANGE_ROW_FIELDS, label="compact source-shard receipt row"
        )
        expected_range_rows.append(receipt)
        del source_rows, context_rows, membership_rows
        del context_body, membership_body
        del provided_context_body, provided_membership_body

    if len(seen_intent_keys) != _origin_source_count(persona_id, origin):
        _fail("expanded semantic bodies do not cover the exact source origin")
    expected_compact_rows = (
        expected_range_rows
        + origin_projection["expected_anchor_rows"]
        + origin_projection["expected_conflict_rows"]
    )
    for row in origin_projection["expected_anchor_rows"]:
        _require_exact_fields(row, ANCHOR_ROW_FIELDS, label="compact anchor row")
    for row in origin_projection["expected_conflict_rows"]:
        _require_exact_fields(row, CONFLICT_ROW_FIELDS, label="compact conflict row")
    compact_body, maximum_compact_row_bytes = _canonical_jsonl(
        expected_compact_rows,
        label=f"compact source semantic membership {persona_id}/{origin}",
        row_cap=MAX_COMPACT_ROW_BYTES_INCLUDING_LF,
        body_cap=MAX_COMPACT_ORIGIN_BODY_BYTES,
    )
    provided_compact_body = _provider_bytes(
        compact_origin_body_provider,
        (persona_id, origin),
        label="compact source semantic origin body",
    )
    if provided_compact_body != compact_body:
        _fail("compact origin body differs from independent exact regeneration")

    expected_descriptor = {
        "body_bytes": len(compact_body),
        "body_sha256": hashlib.sha256(compact_body).hexdigest(),
        "file_name": f"{persona_id}-source-semantic-membership-{origin}.jsonl",
        "maximum_row_bytes_including_lf": maximum_compact_row_bytes,
        "row_count": len(expected_compact_rows),
    }
    _require_canonical_equal(
        manifest["body_descriptor"],
        expected_descriptor,
        label=f"compact origin body descriptor {persona_id}/{origin}",
        max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
    )
    expected_profile_counts = [
        {"fact_profile_id": profile_id, "source_count": count}
        for profile_id, count in sorted(
            profile_counts.items(), key=lambda item: _ascii_key(item[0])
        )
    ]
    _require_canonical_equal(
        manifest["fact_profile_assignment_counts"],
        expected_profile_counts,
        label=f"origin fact profile assignments {persona_id}/{origin}",
        max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
    )
    expected_summary = {
        "compact_anchor_row_count": len(origin_projection["expected_anchor_rows"]),
        "compact_conflict_pair_row_count": len(
            origin_projection["expected_conflict_rows"]
        ),
        "compact_range_receipt_row_count": len(expected_range_rows),
        "component_count": len(origin_projection["components"]),
        "expanded_content_context_body_bytes": expanded_context_body_bytes,
        "expanded_fact_membership_body_bytes": expanded_membership_body_bytes,
        "maximum_component_source_count": max(
            map(len, origin_projection["components"])
        ),
        "maximum_expanded_content_context_row_bytes_including_lf": maximum_context_row_bytes,
        "maximum_expanded_content_context_shard_body_bytes": maximum_context_shard_body_bytes,
        "maximum_expanded_fact_membership_row_bytes_including_lf": maximum_membership_row_bytes,
        "maximum_expanded_fact_membership_shard_body_bytes": maximum_membership_shard_body_bytes,
        "present_fact_reference_count": present_fact_reference_count,
        "semantic_version_source_counts": version_counts,
        "source_count": len(seen_intent_keys),
        "source_shard_count": len(expected_range_rows),
    }
    _require_canonical_equal(
        manifest["summary"],
        expected_summary,
        label=f"source semantic origin summary {persona_id}/{origin}",
        max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
    )
    return {
        "compact_body_bytes": len(compact_body),
        "compact_row_count": len(expected_compact_rows),
        "expanded_context_body_bytes": expanded_context_body_bytes,
        "expanded_membership_body_bytes": expanded_membership_body_bytes,
        "fact_profile_counts": profile_counts,
        "fact_profile_kind_counts": profile_kind_counts,
        "maximum_compact_row_bytes": maximum_compact_row_bytes,
        "maximum_component_source_count": max(
            map(len, origin_projection["components"])
        ),
        "maximum_context_row_bytes": maximum_context_row_bytes,
        "maximum_context_shard_body_bytes": maximum_context_shard_body_bytes,
        "maximum_membership_row_bytes": maximum_membership_row_bytes,
        "maximum_membership_shard_body_bytes": maximum_membership_shard_body_bytes,
        "present_fact_reference_count": present_fact_reference_count,
        "semantic_version_counts": version_counts,
        "source_count": len(seen_intent_keys),
        "source_shard_count": len(expected_range_rows),
    }


def _require_frozen_suite_metrics(suite, origin_metrics):
    totals = {
        "compact_body_bytes": sum(
            row["compact_body_bytes"] for row in origin_metrics.values()
        ),
        "compact_row_count": sum(
            row["compact_row_count"] for row in origin_metrics.values()
        ),
        "expanded_content_context_body_bytes": sum(
            row["expanded_context_body_bytes"] for row in origin_metrics.values()
        ),
        "expanded_fact_membership_body_bytes": sum(
            row["expanded_membership_body_bytes"] for row in origin_metrics.values()
        ),
        "maximum_compact_row_bytes_including_lf": max(
            row["maximum_compact_row_bytes"] for row in origin_metrics.values()
        ),
        "maximum_component_source_count": max(
            row["maximum_component_source_count"] for row in origin_metrics.values()
        ),
        "maximum_expanded_content_context_row_bytes_including_lf": max(
            row["maximum_context_row_bytes"] for row in origin_metrics.values()
        ),
        "maximum_expanded_content_context_shard_body_bytes": max(
            row["maximum_context_shard_body_bytes"]
            for row in origin_metrics.values()
        ),
        "maximum_expanded_fact_membership_row_bytes_including_lf": max(
            row["maximum_membership_row_bytes"] for row in origin_metrics.values()
        ),
        "maximum_expanded_fact_membership_shard_body_bytes": max(
            row["maximum_membership_shard_body_bytes"]
            for row in origin_metrics.values()
        ),
        "present_fact_reference_count": sum(
            row["present_fact_reference_count"] for row in origin_metrics.values()
        ),
        "source_count": sum(row["source_count"] for row in origin_metrics.values()),
        "source_shard_count": sum(
            row["source_shard_count"] for row in origin_metrics.values()
        ),
    }
    frozen = {
        "compact_body_bytes": EXPECTED_COMPACT_BODY_BYTES,
        "compact_row_count": EXPECTED_COMPACT_ROW_COUNT,
        "expanded_content_context_body_bytes": EXPECTED_EXPANDED_CONTEXT_BODY_BYTES,
        "expanded_fact_membership_body_bytes": EXPECTED_EXPANDED_MEMBERSHIP_BODY_BYTES,
        "maximum_compact_row_bytes_including_lf": EXPECTED_MAXIMUM_COMPACT_ROW_BYTES,
        "maximum_component_source_count": 7,
        "maximum_expanded_content_context_row_bytes_including_lf": EXPECTED_MAXIMUM_CONTEXT_ROW_BYTES,
        "maximum_expanded_content_context_shard_body_bytes": EXPECTED_MAXIMUM_CONTEXT_SHARD_BODY_BYTES,
        "maximum_expanded_fact_membership_row_bytes_including_lf": EXPECTED_MAXIMUM_MEMBERSHIP_ROW_BYTES,
        "maximum_expanded_fact_membership_shard_body_bytes": EXPECTED_MAXIMUM_MEMBERSHIP_SHARD_BODY_BYTES,
        "present_fact_reference_count": EXPECTED_PRESENT_FACT_REFERENCE_COUNT,
        "source_count": EXPECTED_SOURCE_COUNT,
        "source_shard_count": EXPECTED_SOURCE_SHARD_COUNT,
    }
    if totals != frozen:
        _fail("independently streamed semantic package metrics differ from frozen pins")
    for key, value in totals.items():
        if suite["summary"].get(key) != value:
            _fail(f"semantic suite summary differs from streamed bodies: {key}")

    kind_counts = {
        "conflict-branch": 0,
        "empty": 0,
        "graph-normal-w0": 0,
        "w0-singleton": 0,
    }
    version_counts = {"v1": 0, "v2": 0}
    for row in origin_metrics.values():
        for kind, count in row["fact_profile_kind_counts"].items():
            kind_counts[kind] += count
        for version, count in row["semantic_version_counts"].items():
            version_counts[version] += count
    if kind_counts != {
        "conflict-branch": EXPECTED_CONFLICT_ENDPOINT_COUNT,
        "empty": 73_350,
        "graph-normal-w0": 124_430,
        "w0-singleton": EXPECTED_ANCHOR_ROW_COUNT,
    }:
        _fail("streamed fact-profile-kind source marginals drifted")
    if version_counts != {
        "v1": EXPECTED_VERSION_ONE_COUNT,
        "v2": EXPECTED_NEAR_REVISION_COUNT,
    }:
        _fail("streamed semantic-version source marginals drifted")
    if suite["summary"]["fact_profile_kind_source_counts"] != kind_counts:
        _fail("semantic suite fact-profile-kind summary drifted")
    if suite["summary"]["semantic_version_source_counts"] != version_counts:
        _fail("semantic suite version summary drifted")
    ledgers = suite["persona_current_component_byte_ledgers"]
    p12 = [row for row in ledgers if row["persona_id"] == "p12"]
    if (
        len(p12) != 1
        or p12[0]["current_component_bytes"]
        != EXPECTED_P12_CURRENT_COMPONENT_BYTES
        or any(
            row["current_component_cap_satisfied"] is not True
            or row["formal_complete_persona_package_cap_proved"] is not False
            or row["current_component_bytes"] > MAX_PERSONA_PACKAGE_BYTES
            or row["headroom_bytes"]
            != MAX_PERSONA_PACKAGE_BYTES - row["current_component_bytes"]
            for row in ledgers
        )
    ):
        _fail("persona current-component cap ledger drifted")


def _validate_source_semantic_membership_package_snapshot(
    catalog,
    suite,
    origin_manifests,
    profile_manifests,
    compact_origin_body_provider,
    expanded_context_body_provider,
    expanded_membership_body_provider,
    *,
    source_suite,
    source_origin_manifests,
    source_profile_manifests,
    source_shard_body_provider,
):
    """Independently validate all semantic manifests and streamed sidecars.

    Semantic metadata is validated before any body provider is invoked.  Each
    provider must be deterministic and return exact ``bytes`` for the requested
    coordinate.  Expanded bodies are regenerated one validated source shard at
    a time, bounded to 4,096 rows, 768 bytes per LF-inclusive row, and 4 MiB.
    """

    try:
        catalog_projection = _validate_catalog(catalog)
        if (
            type(origin_manifests) is not list
            or type(profile_manifests) is not list
            or type(source_origin_manifests) is not list
            or type(source_profile_manifests) is not list
        ):
            _fail("semantic and source manifest collections must be exact lists")
        if (
            len(origin_manifests) != EXPECTED_ORIGIN_COUNT
            or len(profile_manifests) != EXPECTED_PROFILE_COUNT
            or len(source_origin_manifests) != EXPECTED_ORIGIN_COUNT
            or len(source_profile_manifests) != EXPECTED_PROFILE_COUNT
        ):
            _fail("semantic package requires exact forty origin and profile manifests")

        expected_origins = [
            (persona_id, origin)
            for persona_id in envelope.PERSONA_IDS
            for origin in ORIGIN_ORDER
        ]
        expected_profiles = [
            (persona_id, profile)
            for persona_id in envelope.PERSONA_IDS
            for profile in PROFILE_ORDER
        ]
        _prevalidate_source_upstream_metadata(
            source_suite, source_origin_manifests, source_profile_manifests
        )
        source_origin_by_key = {}
        for manifest, coordinate in zip(source_origin_manifests, expected_origins):
            if (
                type(manifest) is not dict
                or (manifest.get("persona_id"), manifest.get("origin")) != coordinate
            ):
                _fail("source origin manifests are not in persona/origin order")
            source_origin_by_key[coordinate] = manifest

        origin_by_key = {}
        for manifest, (persona_id, origin) in zip(
            origin_manifests, expected_origins
        ):
            source_manifest = source_origin_by_key[(persona_id, origin)]
            _prevalidate_origin_manifest(
                manifest,
                persona_id=persona_id,
                origin=origin,
                catalog=catalog,
                catalog_projection=catalog_projection,
                source_manifest=source_manifest,
            )
            origin_by_key[(persona_id, origin)] = manifest
            # A full projection contains total topic/language assignments for
            # the origin.  Metadata-first validation must not retain forty of
            # those maps simultaneously.
            clear = getattr(
                getattr(reservation_layout, "_canonical_origin", None),
                "cache_clear",
                None,
            )
            if callable(clear):
                clear()
            clear = getattr(
                getattr(
                    reservation_layout, "_intent_slot_tuples_by_variant", None
                ),
                "cache_clear",
                None,
            )
            if callable(clear):
                clear()
            clear = getattr(
                getattr(reservation_validator, "_source_domain", None),
                "cache_clear",
                None,
            )
            if callable(clear):
                clear()
            gc.collect()

        profile_by_key = {}
        for manifest, (persona_id, profile) in zip(
            profile_manifests, expected_profiles
        ):
            _prevalidate_profile_manifest(
                manifest,
                persona_id=persona_id,
                profile=profile,
                catalog=catalog,
                origin_by_key=origin_by_key,
            )
            profile_by_key[(persona_id, profile)] = manifest

        _prevalidate_suite_descriptor(
            suite,
            catalog=catalog,
            source_suite=source_suite,
            origin_manifests=origin_manifests,
            profile_manifests=profile_manifests,
            catalog_projection=catalog_projection,
        )

        # Only now may any provider be called.  First establish the complete
        # structural source package, then project semantic bodies from it.
        try:
            source_validator.validate_source_inventory_package(
                source_suite,
                source_origin_manifests,
                source_profile_manifests,
                source_shard_body_provider,
            )
        except source_validator.PersonaV2SourceInventoryPackageValidationError as error:
            _fail(str(error))

        # The source validator's all-origin reservation index is no longer
        # needed.  Body validation derives and releases one origin projection
        # at a time below.
        clear = getattr(
            getattr(source_validator, "_reservation_inputs", None),
            "cache_clear",
            None,
        )
        if callable(clear):
            clear()
        clear = getattr(
            getattr(reservation_layout, "_canonical_origin", None),
            "cache_clear",
            None,
        )
        if callable(clear):
            clear()
        clear = getattr(
            getattr(reservation_layout, "_intent_slot_tuples_by_variant", None),
            "cache_clear",
            None,
        )
        if callable(clear):
            clear()
        clear = getattr(
            getattr(reservation_validator, "_source_domain", None),
            "cache_clear",
            None,
        )
        if callable(clear):
            clear()
        gc.collect()

        origin_metrics = {}
        for persona_id, origin in expected_origins:
            manifest = origin_by_key[(persona_id, origin)]
            origin_projection = _origin_reservation_projection(
                persona_id,
                origin,
                catalog_projection["fact_profiles"]["semantic_index"],
            )
            origin_metrics[(persona_id, origin)] = _validate_origin_bodies(
                manifest,
                source_origin_by_key[(persona_id, origin)],
                origin_projection,
                catalog_projection,
                compact_origin_body_provider=compact_origin_body_provider,
                expanded_context_body_provider=expanded_context_body_provider,
                expanded_membership_body_provider=expanded_membership_body_provider,
                source_shard_body_provider=source_shard_body_provider,
            )
            del origin_projection
            clear = getattr(
                getattr(reservation_layout, "_canonical_origin", None),
                "cache_clear",
                None,
            )
            if callable(clear):
                clear()
            clear = getattr(
                getattr(
                    reservation_layout, "_intent_slot_tuples_by_variant", None
                ),
                "cache_clear",
                None,
            )
            if callable(clear):
                clear()
            clear = getattr(
                getattr(reservation_validator, "_source_domain", None),
                "cache_clear",
                None,
            )
            if callable(clear):
                clear()
            gc.collect()
        _require_frozen_suite_metrics(suite, origin_metrics)
        return True
    finally:
        _clear_upstream_working_caches()
        gc.collect()


def _snapshot_artifact(value, *, label, max_bytes):
    raw = _canonical_bytes(value, label=label, max_bytes=max_bytes)
    return copy.deepcopy(value), raw


def _snapshot_artifact_list(values, *, label, expected_count, max_bytes):
    if type(values) is not list or len(values) != expected_count:
        _fail(f"{label} must be an exact {expected_count}-item list")
    snapshots = []
    raws = []
    for value in values:
        snapshot, raw = _snapshot_artifact(
            value,
            label=label,
            max_bytes=max_bytes,
        )
        snapshots.append(snapshot)
        raws.append(raw)
    return snapshots, tuple(raws)


def _reauth_artifact(value, opening_raw, *, label, max_bytes):
    try:
        current_raw = _canonical_bytes(value, label=label, max_bytes=max_bytes)
    except PersonaV2SourceSemanticMembershipPackageValidationError:
        _fail(f"caller-owned {label} changed during provider callback")
    if current_raw != opening_raw:
        _fail(f"caller-owned {label} changed during provider callback")


def _reauth_artifact_list(
    values, opening_raws, *, label, expected_count, max_bytes
):
    if type(values) is not list or len(values) != expected_count:
        _fail(f"caller-owned {label} changed during provider callback")
    for value, opening_raw in zip(values, opening_raws, strict=True):
        _reauth_artifact(
            value,
            opening_raw,
            label=label,
            max_bytes=max_bytes,
        )


def validate_source_semantic_membership_package(
    catalog,
    suite,
    origin_manifests,
    profile_manifests,
    compact_origin_body_provider,
    expanded_context_body_provider,
    expanded_membership_body_provider,
    *,
    source_suite,
    source_origin_manifests,
    source_profile_manifests,
    source_shard_body_provider,
):
    """Validate detached metadata and reject provider callback TOCTOU."""

    catalog_snapshot, catalog_raw = _snapshot_artifact(
        catalog,
        label="persona v2 source semantic membership catalog",
        max_bytes=MAX_CATALOG_BYTES,
    )
    suite_snapshot, suite_raw = _snapshot_artifact(
        suite,
        label="persona v2 source semantic membership suite",
        max_bytes=MAX_SUITE_DESCRIPTOR_BYTES,
    )
    origin_snapshots, origin_raws = _snapshot_artifact_list(
        origin_manifests,
        label="persona v2 source semantic membership origin manifest",
        expected_count=EXPECTED_ORIGIN_COUNT,
        max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
    )
    profile_snapshots, profile_raws = _snapshot_artifact_list(
        profile_manifests,
        label="persona v2 source semantic membership profile manifest",
        expected_count=EXPECTED_PROFILE_COUNT,
        max_bytes=MAX_PROFILE_MANIFEST_BYTES,
    )
    source_suite_snapshot, source_suite_raw = _snapshot_artifact(
        source_suite,
        label="bound source inventory suite",
        max_bytes=source_validator.MAX_SUITE_DESCRIPTOR_BYTES,
    )
    source_origin_snapshots, source_origin_raws = _snapshot_artifact_list(
        source_origin_manifests,
        label="bound source inventory origin manifest",
        expected_count=EXPECTED_ORIGIN_COUNT,
        max_bytes=source_validator.MAX_ORIGIN_MANIFEST_BYTES,
    )
    source_profile_snapshots, source_profile_raws = _snapshot_artifact_list(
        source_profile_manifests,
        label="bound source inventory profile manifest",
        expected_count=EXPECTED_PROFILE_COUNT,
        max_bytes=source_validator.MAX_PROFILE_MANIFEST_BYTES,
    )
    try:
        return _validate_source_semantic_membership_package_snapshot(
            catalog_snapshot,
            suite_snapshot,
            origin_snapshots,
            profile_snapshots,
            compact_origin_body_provider,
            expanded_context_body_provider,
            expanded_membership_body_provider,
            source_suite=source_suite_snapshot,
            source_origin_manifests=source_origin_snapshots,
            source_profile_manifests=source_profile_snapshots,
            source_shard_body_provider=source_shard_body_provider,
        )
    finally:
        _reauth_artifact(
            catalog,
            catalog_raw,
            label="source semantic membership catalog",
            max_bytes=MAX_CATALOG_BYTES,
        )
        _reauth_artifact(
            suite,
            suite_raw,
            label="source semantic membership suite",
            max_bytes=MAX_SUITE_DESCRIPTOR_BYTES,
        )
        _reauth_artifact_list(
            origin_manifests,
            origin_raws,
            label="source semantic membership origin manifests",
            expected_count=EXPECTED_ORIGIN_COUNT,
            max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
        )
        _reauth_artifact_list(
            profile_manifests,
            profile_raws,
            label="source semantic membership profile manifests",
            expected_count=EXPECTED_PROFILE_COUNT,
            max_bytes=MAX_PROFILE_MANIFEST_BYTES,
        )
        _reauth_artifact(
            source_suite,
            source_suite_raw,
            label="bound source inventory suite",
            max_bytes=source_validator.MAX_SUITE_DESCRIPTOR_BYTES,
        )
        _reauth_artifact_list(
            source_origin_manifests,
            source_origin_raws,
            label="bound source inventory origin manifests",
            expected_count=EXPECTED_ORIGIN_COUNT,
            max_bytes=source_validator.MAX_ORIGIN_MANIFEST_BYTES,
        )
        _reauth_artifact_list(
            source_profile_manifests,
            source_profile_raws,
            label="bound source inventory profile manifests",
            expected_count=EXPECTED_PROFILE_COUNT,
            max_bytes=source_validator.MAX_PROFILE_MANIFEST_BYTES,
        )


__all__ = [
    "ANCHOR_ROW_FIELDS",
    "CATALOG_TOP_LEVEL_FIELDS",
    "CONFLICT_ROW_FIELDS",
    "EXPANDED_CONTEXT_ROW_FIELDS",
    "EXPANDED_MEMBERSHIP_ROW_FIELDS",
    "FACT_PROFILE_FIELDS",
    "MAX_COMPACT_ORIGIN_BODY_BYTES",
    "MAX_COMPACT_ROW_BYTES_INCLUDING_LF",
    "MAX_EXPANDED_ROW_BYTES_INCLUDING_LF",
    "MAX_EXPANDED_SHARD_BODY_BYTES",
    "ORIGIN_TOP_LEVEL_FIELDS",
    "PROFILE_TOP_LEVEL_FIELDS",
    "PersonaV2SourceSemanticMembershipPackageValidationError",
    "RANGE_ROW_FIELDS",
    "SEMANTIC_PROFILE_FIELDS",
    "SUITE_TOP_LEVEL_FIELDS",
    "TOPIC_FIELDS",
    "validate_source_semantic_membership_catalog",
    "validate_source_semantic_membership_package",
]
