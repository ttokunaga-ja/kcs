"""Deterministic source-owned semantic membership for persona-PC v2.

This package binds every immutable structural source slot to an authored
content context and W0 present-fact set without changing the upstream source
inventory.  Its persisted origin bodies are compact: one receipt row per
source shard plus explicit semantic-anchor and conflict-branch rows.  Exact
203,000-row content-context and fact-membership bodies are reproducible through
bounded streaming providers and are committed by per-shard SHA-256 receipts.

The artifact remains pre-render, pre-solver, pre-query, and non-authorizing.
In particular it contains no query/oracle/final-source identifiers and it does
not claim the future complete 16-MiB persona-package gate.
"""

from __future__ import annotations

import copy
import functools
import hashlib

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_fact_graph as fact_graph
    from . import persona_v2_overlay_reservation_layout as reservation_layout
    from . import persona_v2_realism_profile as realism_profile
    from . import persona_v2_source_inventory_package as source_package
    from . import persona_v2_source_inventory_profile as inventory_profile
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_fact_graph as fact_graph
    import persona_v2_overlay_reservation_layout as reservation_layout
    import persona_v2_realism_profile as realism_profile
    import persona_v2_source_inventory_package as source_package
    import persona_v2_source_inventory_profile as inventory_profile


CATALOG_ARTIFACT_SCHEMA = "kcs.persona.pc-source-semantic-membership-catalog/v2"
CATALOG_ARTIFACT_KIND = "persona-pc-v2-source-semantic-membership-catalog"
ORIGIN_ARTIFACT_SCHEMA = "kcs.persona.pc-source-semantic-membership-origin-manifest/v2"
ORIGIN_ARTIFACT_KIND = "persona-pc-v2-source-semantic-membership-origin-manifest"
PROFILE_ARTIFACT_SCHEMA = "kcs.persona.pc-source-semantic-membership-profile-manifest/v2"
PROFILE_ARTIFACT_KIND = "persona-pc-v2-source-semantic-membership-profile-manifest"
SUITE_ARTIFACT_SCHEMA = "kcs.persona.pc-source-semantic-membership-suite/v2"
SUITE_ARTIFACT_KIND = "persona-pc-v2-source-semantic-membership-suite"
ARTIFACT_SCHEMA_VERSION = 2

ORIGIN_ORDER = source_package.ORIGIN_ORDER
PROFILE_ORDER = source_package.PROFILE_ORDER
TOPIC_SLOT_ORDER = ("g01", "g02", "g03", "g04")

FACT_PROFILE_COUNT_PER_PERSONA = 45
EXPECTED_FACT_PROFILE_COUNT = 20 * FACT_PROFILE_COUNT_PER_PERSONA
EXPECTED_SOURCE_COUNT = source_package.EXPECTED_SOURCE_INTENT_COUNT
EXPECTED_ORIGIN_COUNT = source_package.EXPECTED_ORIGIN_MANIFEST_COUNT
EXPECTED_PROFILE_COUNT = source_package.EXPECTED_PROFILE_MANIFEST_COUNT
EXPECTED_SOURCE_SHARD_COUNT = source_package.EXPECTED_SHARD_COUNT
EXPECTED_SEMANTIC_ANCHOR_COUNT = 2_100
EXPECTED_CONFLICT_CLUSTER_COUNT = 1_560
EXPECTED_CONFLICT_ENDPOINT_COUNT = 2 * EXPECTED_CONFLICT_CLUSTER_COUNT

MAX_CATALOG_BYTES = 2 * 2**20
MAX_ORIGIN_BODY_BYTES = 4 * 2**20
MAX_COMPACT_ROWS_PER_ORIGIN = 4_096
MAX_ORIGIN_MANIFEST_BYTES = 256 * 1024
MAX_PROFILE_MANIFEST_BYTES = 256 * 1024
MAX_SUITE_DESCRIPTOR_BYTES = 512 * 1024
MAX_COMPACT_ROW_BYTES_INCLUDING_LF = 768
MAX_EXPANDED_CONTEXT_ROW_BYTES_INCLUDING_LF = 768
MAX_EXPANDED_MEMBERSHIP_ROW_BYTES_INCLUDING_LF = 768
MAX_EXPANDED_SHARD_BODY_BYTES = 4 * 2**20
MAX_EXPANDED_ROWS_PER_SHARD = 4_096
MAX_PERSONA_PACKAGE_BYTES = source_package.MAX_PERSONA_PACKAGE_BYTES

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
    {
        "fact_profile_id",
        "intent_key",
        "row_kind",
        "semantic_anchor_slot_ordinal",
    }
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

PROHIBITED_KEY_TOKENS = frozenset(
    {"answer", "distractor", "final", "oracle", "query", "relevance", "retrieval"}
)


class PersonaV2SourceSemanticMembershipPackageError(ValueError):
    """Raised when the source-owned semantic-membership contract is broken."""


def _require_persona_id(persona_id):
    if type(persona_id) is not str or persona_id not in envelope.PERSONA_IDS:
        raise PersonaV2SourceSemanticMembershipPackageError(
            f"unknown persona ID: {persona_id!r}"
        )


def _require_origin(origin):
    if type(origin) is not str or origin not in ORIGIN_ORDER:
        raise PersonaV2SourceSemanticMembershipPackageError(
            f"unknown source origin: {origin!r}"
        )


def _require_profile(profile):
    if type(profile) is not str or profile not in PROFILE_ORDER:
        raise PersonaV2SourceSemanticMembershipPackageError(
            f"unknown source profile: {profile!r}"
        )


def _negative_authority():
    return {field: False for field in sorted(AUTHORITY_FIELDS)}


def _require_negative_authority(value, *, label):
    if type(value) is not dict or value.get("g0_contract_frozen") is not False:
        raise PersonaV2SourceSemanticMembershipPackageError(
            f"{label} must remain non-G0"
        )
    authority = value.get("authority")
    if set(authority or {}) != AUTHORITY_FIELDS or any(
        type(flag) is not bool or flag is not False
        for flag in (authority or {}).values()
    ):
        raise PersonaV2SourceSemanticMembershipPackageError(
            f"{label} authority must be the exact all-false schema"
        )


def _ascii_key(value):
    return value.encode("ascii")


def _jsonl_row_bytes(row, *, label, cap):
    try:
        return artifact_common.canonical_json_bytes(
            row, label=label, max_bytes=cap - 1
        ) + b"\n"
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SourceSemanticMembershipPackageError(str(error)) from None


def _sha256(value):
    return hashlib.sha256(value).hexdigest()


def empty_fact_profile_id(persona_id):
    _require_persona_id(persona_id)
    return f"{persona_id}-source-fact-profile-empty-v2"


def singleton_fact_profile_id(persona_id, graph_slot, fact_slot):
    _require_persona_id(persona_id)
    if graph_slot not in TOPIC_SLOT_ORDER or type(fact_slot) is not int or not 1 <= fact_slot <= 8:
        raise PersonaV2SourceSemanticMembershipPackageError(
            "singleton fact-profile coordinate is out of range"
        )
    return f"{persona_id}-source-fact-profile-{graph_slot}-singleton-s{fact_slot:02d}-v2"


def normal_fact_profile_id(persona_id, graph_slot):
    _require_persona_id(persona_id)
    if graph_slot not in TOPIC_SLOT_ORDER:
        raise PersonaV2SourceSemanticMembershipPackageError("unknown topic slot")
    return f"{persona_id}-source-fact-profile-{graph_slot}-normal-v2"


def conflict_fact_profile_id(persona_id, graph_slot, branch_role):
    _require_persona_id(persona_id)
    if graph_slot not in TOPIC_SLOT_ORDER or branch_role not in {"branch-a", "branch-b"}:
        raise PersonaV2SourceSemanticMembershipPackageError(
            "conflict fact-profile coordinate is out of range"
        )
    return f"{persona_id}-source-fact-profile-{graph_slot}-{branch_role}-v2"


def semantic_topic_id(persona_id, graph_slot):
    _require_persona_id(persona_id)
    if graph_slot not in TOPIC_SLOT_ORDER:
        raise PersonaV2SourceSemanticMembershipPackageError("unknown topic slot")
    return f"{persona_id}-semantic-topic-{graph_slot}-v2"


def _artifact_binding(
    name,
    role,
    value,
    *,
    canonical,
    digest,
    coordinate_fields=(),
):
    authority = value.get("authority") if type(value) is dict else None
    if type(authority) is not dict or not authority or any(
        type(flag) is not bool or flag is not False for flag in authority.values()
    ):
        raise PersonaV2SourceSemanticMembershipPackageError(
            f"{name} dependency must remain all-false"
        )
    raw = canonical(value)
    actual = digest(value)
    if actual != _sha256(raw):
        raise PersonaV2SourceSemanticMembershipPackageError(
            f"{name} dependency digest drifted"
        )
    result = {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "dependency_role": role,
        "name": name,
        "sha256": actual,
    }
    for field in coordinate_fields:
        result[field] = value[field]
    return result


def _fact_state_at_checkpoint(fact, checkpoint):
    states = [
        row["state"]
        for row in fact["visibility_by_checkpoint"]
        if row["checkpoint"] == checkpoint
    ]
    if len(states) != 1:
        raise PersonaV2SourceSemanticMembershipPackageError(
            "fact visibility is not total at the requested checkpoint"
        )
    return states[0]


def _synthetic_entity_closure(graph, present_fact_ids):
    facts = {row["fact_id"]: row for row in graph["facts"]}
    graph_entity_ids = {row["entity_id"] for row in graph["entities"]}
    result = set()
    for fact_id in present_fact_ids:
        fact = facts.get(fact_id)
        if fact is None:
            raise PersonaV2SourceSemanticMembershipPackageError(
                "fact profile references a fact outside its graph"
            )
        result.add(fact["subject_entity_id"])
        typed_value = fact["typed_value"]
        if typed_value.get("kind") == "entity-reference":
            result.add(typed_value["entity_id"])
    if not result <= graph_entity_ids:
        raise PersonaV2SourceSemanticMembershipPackageError(
            "fact profile entity closure escaped its graph"
        )
    return sorted(result, key=_ascii_key)


def _profile_row(
    *,
    persona_id,
    fact_profile_id,
    graph,
    present_fact_ids,
    profile_kind,
    branch_role="not-applicable",
    conflict_set_id="not-applicable",
    conflict_template_key="not-applicable",
):
    present_fact_ids = sorted(present_fact_ids, key=_ascii_key)
    if graph is None:
        graph_id = "not-applicable"
        project_or_case_id = "not-applicable"
        entity_ids = []
    else:
        graph_id = graph["graph_id"]
        project_or_case_id = graph["project_or_case_id"]
        entity_ids = _synthetic_entity_closure(graph, present_fact_ids)
    row = {
        "branch_role": branch_role,
        "conflict_set_id": conflict_set_id,
        "conflict_template_key": conflict_template_key,
        "fact_profile_id": fact_profile_id,
        "graph_id": graph_id,
        "persona_id": persona_id,
        "present_fact_ids": present_fact_ids,
        "profile_kind": profile_kind,
        "project_or_case_id": project_or_case_id,
        "synthetic_entity_ids": entity_ids,
    }
    if set(row) != FACT_PROFILE_FIELDS:
        raise PersonaV2SourceSemanticMembershipPackageError(
            "fact-profile row schema drifted"
        )
    return row


def _persona_catalog_rows(persona_id, graph_value):
    graphs = sorted(graph_value["graphs"], key=lambda row: _ascii_key(row["graph_id"]))
    if len(graphs) != len(TOPIC_SLOT_ORDER):
        raise PersonaV2SourceSemanticMembershipPackageError(
            "each persona must expose exactly four fact graphs"
        )
    templates = []
    topics = []
    for graph_slot, graph in zip(TOPIC_SLOT_ORDER, graphs):
        current = sorted(
            [
                row["fact_id"]
                for row in graph["facts"]
                if _fact_state_at_checkpoint(row, "W0") == "current"
            ],
            key=_ascii_key,
        )
        conflict_sets = graph["conflict_sets"]
        if len(current) != 8 or len(conflict_sets) != 1:
            raise PersonaV2SourceSemanticMembershipPackageError(
                "each graph must expose eight W0-current facts and one conflict set"
            )
        conflict = conflict_sets[0]
        pair = sorted(conflict["member_fact_ids"], key=_ascii_key)
        common = [fact_id for fact_id in current if fact_id not in pair]
        if len(pair) != 2 or not set(pair) <= set(current) or len(common) != 6:
            raise PersonaV2SourceSemanticMembershipPackageError(
                "conflict template is not an exact 6+2 W0 partition"
            )
        graph_ordinal = TOPIC_SLOT_ORDER.index(graph_slot) + 1
        template_key = f"{persona_id}-conflict-fact-template-syn-{graph_ordinal:02d}"
        templates.append(
            {
                "common": common,
                "conflict": conflict,
                "current": current,
                "graph": graph,
                "graph_slot": graph_slot,
                "pair": pair,
                "template_key": template_key,
            }
        )
        topic = {
            "graph_id": graph["graph_id"],
            "persona_id": persona_id,
            "project_or_case_id": graph["project_or_case_id"],
            "topic_id": semantic_topic_id(persona_id, graph_slot),
            "topic_slot": graph_slot,
        }
        if set(topic) != TOPIC_FIELDS:
            raise PersonaV2SourceSemanticMembershipPackageError(
                "semantic-topic row schema drifted"
            )
        topics.append(topic)

    rows = [
        _profile_row(
            persona_id=persona_id,
            fact_profile_id=empty_fact_profile_id(persona_id),
            graph=None,
            present_fact_ids=[],
            profile_kind="empty",
        )
    ]
    # Fact-major then graph-major ordering gives each 105-slot anchor inventory
    # a deterministic 27/26/26/26 topic spread without importing evaluation data.
    for fact_slot in range(1, 9):
        for template in templates:
            rows.append(
                _profile_row(
                    persona_id=persona_id,
                    fact_profile_id=singleton_fact_profile_id(
                        persona_id, template["graph_slot"], fact_slot
                    ),
                    graph=template["graph"],
                    present_fact_ids=[template["current"][fact_slot - 1]],
                    profile_kind="w0-singleton",
                )
            )
    for template in templates:
        rows.append(
            _profile_row(
                persona_id=persona_id,
                fact_profile_id=normal_fact_profile_id(
                    persona_id, template["graph_slot"]
                ),
                graph=template["graph"],
                present_fact_ids=template["current"],
                profile_kind="graph-normal-w0",
            )
        )
    for template in templates:
        for branch_role, selected in zip(("branch-a", "branch-b"), template["pair"]):
            rows.append(
                _profile_row(
                    persona_id=persona_id,
                    fact_profile_id=conflict_fact_profile_id(
                        persona_id, template["graph_slot"], branch_role
                    ),
                    graph=template["graph"],
                    present_fact_ids=template["common"] + [selected],
                    profile_kind="conflict-branch",
                    branch_role=branch_role.removeprefix("branch-"),
                    conflict_set_id=template["conflict"]["conflict_set_id"],
                    conflict_template_key=template["template_key"],
                )
            )
    if len(rows) != FACT_PROFILE_COUNT_PER_PERSONA:
        raise PersonaV2SourceSemanticMembershipPackageError(
            "persona fact-profile cardinality drifted"
        )
    return rows, topics, templates


@functools.lru_cache(maxsize=1)
def _catalog_inputs():
    graph_values = fact_graph.build_fact_graph_suite()
    if [row["persona_id"] for row in graph_values] != list(envelope.PERSONA_IDS):
        raise PersonaV2SourceSemanticMembershipPackageError(
            "fact-graph suite persona order drifted"
        )
    realism = realism_profile.build_realism_profile()
    inventory = inventory_profile.build_source_inventory_profile_catalog()
    realism_profile.validate_realism_profile(realism)
    inventory_profile.validate_source_inventory_profile_catalog(inventory)
    profiles = []
    topics = []
    templates_by_persona = {}
    for persona_id, graph_value in zip(envelope.PERSONA_IDS, graph_values):
        persona_profiles, persona_topics, templates = _persona_catalog_rows(
            persona_id, graph_value
        )
        profiles.extend(persona_profiles)
        topics.extend(persona_topics)
        templates_by_persona[persona_id] = templates
    return {
        "fact_profiles": profiles,
        "fact_profiles_by_id": {row["fact_profile_id"]: row for row in profiles},
        "graph_values": graph_values,
        "graph_values_by_persona": {
            row["persona_id"]: row for row in graph_values
        },
        "inventory": inventory,
        "realism": realism,
        "realism_by_persona": {
            row["persona_id"]: row for row in realism["personas"]
        },
        "templates_by_persona": templates_by_persona,
        "topics": topics,
        "topics_by_id": {row["topic_id"]: row for row in topics},
    }


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


@functools.lru_cache(maxsize=1)
def _canonical_catalog():
    inputs = _catalog_inputs()
    realism = inputs["realism"]
    inventory = inputs["inventory"]
    graph_bindings = []
    for persona_id, graph_value in zip(envelope.PERSONA_IDS, inputs["graph_values"]):
        graph_bindings.append(
            _artifact_binding(
                "persona-v2-fact-graph",
                "typed-fact-profile-source",
                graph_value,
                canonical=fact_graph.canonical_json_bytes,
                digest=lambda value, persona_id=persona_id: fact_graph.fact_graph_sha256(
                    persona_id, value
                ),
                coordinate_fields=("persona_id",),
            )
        )
    input_bindings = [
        _artifact_binding(
            "persona-v2-source-inventory-profile-catalog",
            "source-semantic-profile-foreign-keys",
            inventory,
            canonical=inventory_profile.canonical_json_bytes,
            digest=inventory_profile.source_inventory_profile_catalog_sha256,
        ),
        _artifact_binding(
            "persona-v2-realism-profile",
            "persona-language-weight-owner",
            realism,
            canonical=realism_profile.canonical_json_bytes,
            digest=realism_profile.realism_profile_sha256,
        ),
        *graph_bindings,
    ]
    value = {
        "artifact_kind": CATALOG_ARTIFACT_KIND,
        "artifact_schema": CATALOG_ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "assignment_contract": {
            "component_edges": [
                "content-relation-anchor-to-derivative",
                "attachment-host-to-standalone-member",
            ],
            "conflict_anchor_maps_branch_a": True,
            "conflict_derivative_maps_branch_b": True,
            "empty_profile_allowed_gate_role": "raw_only",
            "fixed_topic_components": ["semantic-anchor", "conflict-copy"],
            "free_component_order": "source-count-descending-then-minimum-intent-key-ascii",
            "label_choice_score": (
                "target-count-times-assigned-total-plus-component-size-minus-"
                "assigned-label-count-times-origin-source-count"
            ),
            "label_tie_break": "ascii-label",
            "language_fixed_components_present": False,
            "normal_conflict_presentation_mode": "explicit-unordered-current-alternatives",
            "normal_profile_present_fact_count": 8,
            "quota_algorithm_id": envelope.APPORTIONMENT_ALGORITHM_ID,
            "quota_profiles": "pilot-Hamilton-full-Hamilton-residual-equals-full-minus-pilot",
            "raw_only_present_fact_count": 0,
            "searchable_default_profile_kind": "graph-normal-w0",
            "singleton_anchor_profile_cycle": (
                "singleton-index-equals-semantic-anchor-slot-ordinal-minus-one-"
                "modulo-32-in-fact-slot-then-graph-slot-order"
            ),
        },
        "authority": _negative_authority(),
        "canonical_limits": {
            "max_body_bytes": MAX_CATALOG_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_900_fact_profiles_bound": True,
            "all_71_semantic_profiles_bound": True,
            "all_80_semantic_topics_bound": True,
            "all_w0_profile_fact_ids_typed_graph_owned": True,
            "concrete_source_membership_bound": False,
            "formal_complete_persona_package_cap_proved": False,
            "history_membership_bound": False,
        },
        "completion_scope": (
            "exact-w0-source-semantic-profile-and-topic-catalog-only-no-render-"
            "no-solver-no-history-no-execution-no-g0"
        ),
        "dependency_direction_contract": {
            "catalog_may_bind_origin_profile_or_suite_manifest": False,
            "fact_graphs_inventory_profiles_and_realism_are_strictly_upstream": True,
            "source_membership_manifests_must_bind_catalog": True,
        },
        "fact_profiles": copy.deepcopy(inputs["fact_profiles"]),
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "hypothesis_status": "authored-benchmark-stress-design-not-observed-user-statistics",
        "input_binding_order": [row["name"] for row in input_bindings],
        "input_bindings": input_bindings,
        "orders": {
            "fact_profiles": "persona-then-empty-then-singleton-fact-then-graph-then-normal-then-conflict-graph-then-branch",
            "persona": list(envelope.PERSONA_IDS),
            "semantic_topics": "persona-then-graph-id-ascii",
            "topic_slot": list(TOPIC_SLOT_ORDER),
        },
        "remaining_blockers": [
            "formal-source-recipes-and-missing-renderer-validator-implementations",
            "concrete-logical-overlay-materialization",
            "history-and-checkpoint-transition-membership",
            "scope-placement-allocation-and-proof",
            "render-write-chunk-observation-and-kcs-execution",
            "future-complete-persona-package-cap-proof",
        ],
        "semantic_profiles": [],
        "semantic_topics": copy.deepcopy(inputs["topics"]),
        "summary": {
            "conflict_branch_profile_count": 160,
            "empty_profile_count": 20,
            "fact_profile_count": len(inputs["fact_profiles"]),
            "normal_profile_count": 80,
            "persona_count": len(envelope.PERSONA_IDS),
            "semantic_profile_count": inventory_profile.EXPECTED_PROFILE_COUNT,
            "semantic_topic_count": len(inputs["topics"]),
            "singleton_profile_count": 640,
        },
    }
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
    for source_profile in inventory["source_profile_rows"]:
        variant_id = source_profile["variant_id"]
        row = {
            "content_template_slot_id": f"persona-v2-content-template-slot-{variant_id}-v2",
            "document_role": document_roles[source_profile["family"]],
            "family": source_profile["family"],
            "filename_template_slot_id": f"persona-v2-filename-template-slot-{variant_id}-v2",
            "formal_recipe_binding_status": source_profile["source_recipe"]["binding_status"],
            "gate_role": source_profile["gate_role"],
            "language_binding_mode": "origin-component-language",
            "semantic_profile_id": f"persona-v2-source-semantic-profile-{variant_id}-v2",
            "source_profile_id": source_profile["source_profile_id"],
            "variant_id": variant_id,
        }
        if set(row) != SEMANTIC_PROFILE_FIELDS:
            raise PersonaV2SourceSemanticMembershipPackageError(
                "source semantic-profile row schema drifted"
            )
        value["semantic_profiles"].append(row)
    if set(value) != CATALOG_TOP_LEVEL_FIELDS:
        raise PersonaV2SourceSemanticMembershipPackageError(
            "source semantic catalog top-level schema drifted"
        )
    _require_negative_authority(value, label="source semantic membership catalog")
    try:
        artifact_common.canonical_json_bytes(
            value,
            label="persona v2 source semantic membership catalog",
            max_bytes=MAX_CATALOG_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SourceSemanticMembershipPackageError(str(error)) from None
    return value


def build_source_semantic_membership_catalog():
    """Return the detached 20-persona, 900-profile W0 semantic catalog."""

    return copy.deepcopy(_canonical_catalog())


def canonical_json_bytes(value):
    if type(value) is not dict:
        raise PersonaV2SourceSemanticMembershipPackageError(
            "source semantic membership artifact must be an object"
        )
    schema = value.get("artifact_schema")
    contracts = {
        CATALOG_ARTIFACT_SCHEMA: (
            "persona v2 source semantic membership catalog",
            MAX_CATALOG_BYTES,
        ),
        ORIGIN_ARTIFACT_SCHEMA: (
            "persona v2 source semantic membership origin manifest",
            MAX_ORIGIN_MANIFEST_BYTES,
        ),
        PROFILE_ARTIFACT_SCHEMA: (
            "persona v2 source semantic membership profile manifest",
            MAX_PROFILE_MANIFEST_BYTES,
        ),
        SUITE_ARTIFACT_SCHEMA: (
            "persona v2 source semantic membership suite",
            MAX_SUITE_DESCRIPTOR_BYTES,
        ),
    }
    if schema not in contracts:
        raise PersonaV2SourceSemanticMembershipPackageError(
            f"unknown source semantic membership schema: {schema!r}"
        )
    label, cap = contracts[schema]
    try:
        return artifact_common.canonical_json_bytes(value, label=label, max_bytes=cap)
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SourceSemanticMembershipPackageError(str(error)) from None


def validate_source_semantic_membership_catalog(value):
    expected = build_source_semantic_membership_catalog()
    if canonical_json_bytes(value) != canonical_json_bytes(expected):
        raise PersonaV2SourceSemanticMembershipPackageError(
            "source semantic membership catalog differs from exact regeneration"
        )
    return True


def source_semantic_membership_catalog_sha256(value=None):
    if value is None:
        value = build_source_semantic_membership_catalog()
    validate_source_semantic_membership_catalog(value)
    return _sha256(canonical_json_bytes(value))


def _quota_counts(persona_id, origin, labels, weights):
    if (
        type(labels) is not list
        or type(weights) is not list
        or not labels
        or len(labels) != len(weights)
        or len(labels) != len(set(labels))
    ):
        raise PersonaV2SourceSemanticMembershipPackageError(
            "quota labels and weights must be aligned and unique"
        )
    ordered = sorted(zip(labels, weights), key=lambda item: _ascii_key(item[0]))
    labels = [item[0] for item in ordered]
    weights = [item[1] for item in ordered]
    pilot_total = envelope.profile_file_count(persona_id, "pilot")
    full_total = envelope.profile_file_count(persona_id, "full")
    pilot = envelope.largest_remainder(pilot_total, weights)
    full = envelope.largest_remainder(full_total, weights)
    selected = pilot if origin == "pilot" else tuple(
        full_count - pilot_count
        for full_count, pilot_count in zip(full, pilot)
    )
    if any(value < 0 for value in selected):
        raise PersonaV2SourceSemanticMembershipPackageError(
            "full-minus-pilot quota became negative"
        )
    return {label: count for label, count in zip(labels, selected)}


def _component_assignments(components, target_counts, fixed_by_intent):
    labels = sorted(target_counts, key=_ascii_key)
    domain_source_count = sum(target_counts.values())
    if sum(len(component) for component in components) != domain_source_count:
        raise PersonaV2SourceSemanticMembershipPackageError(
            "component partition and quota denominator disagree"
        )
    assigned_counts = {label: 0 for label in labels}
    component_labels = {}
    fixed = []
    free = []
    for component in components:
        declared = {
            fixed_by_intent[intent_key]
            for intent_key in component
            if intent_key in fixed_by_intent
        }
        if len(declared) > 1:
            raise PersonaV2SourceSemanticMembershipPackageError(
                "one component received incompatible fixed labels"
            )
        (fixed if declared else free).append((component, next(iter(declared), None)))
    order_key = lambda item: (-len(item[0]), _ascii_key(item[0][0]))
    for component, label in sorted(fixed, key=order_key):
        if label not in target_counts:
            raise PersonaV2SourceSemanticMembershipPackageError(
                "fixed component references an unknown quota label"
            )
        size = len(component)
        if assigned_counts[label] + size > target_counts[label]:
            raise PersonaV2SourceSemanticMembershipPackageError(
                "fixed component exceeds its Hamilton target"
            )
        assigned_counts[label] += size
        component_labels[component[0]] = label
    for component, _unused in sorted(free, key=order_key):
        size = len(component)
        assigned_total = sum(assigned_counts.values())
        candidates = [
            label
            for label in labels
            if target_counts[label] - assigned_counts[label] >= size
        ]
        if not candidates:
            raise PersonaV2SourceSemanticMembershipPackageError(
                "component allocator exhausted all exact quota candidates"
            )
        label = sorted(
            candidates,
            key=lambda candidate: (
                -(
                    target_counts[candidate] * (assigned_total + size)
                    - assigned_counts[candidate] * domain_source_count
                ),
                _ascii_key(candidate),
            ),
        )[0]
        assigned_counts[label] += size
        component_labels[component[0]] = label
    if assigned_counts != target_counts:
        raise PersonaV2SourceSemanticMembershipPackageError(
            "component allocator did not close the exact Hamilton target"
        )
    result = {}
    for component in components:
        label = component_labels[component[0]]
        for intent_key in component:
            result[intent_key] = label
    return result, assigned_counts


def _source_local_identity(source_row):
    context_id = source_row["content_context_id"]
    return {
        "logical_branch_key": f"{context_id}-branch-v2",
        "logical_document_key": f"{context_id}-document-v2",
        "logical_revision_key": f"{context_id}-revision-v2",
        "payload_equivalence_key": source_row["deterministic_payload_seed"],
        "semantic_section_key": f"{context_id}-section-v2",
    }


def _build_origin_plan(persona_id, origin):
    _require_persona_id(persona_id)
    _require_origin(origin)
    catalog = _canonical_catalog()
    source_manifest = source_package.build_source_intent_origin_manifest(
        persona_id, origin
    )
    reservation = reservation_layout.build_overlay_reservation_origin(
        persona_id, origin
    )
    source_rows = []
    for descriptor in source_manifest["shard_descriptors"]:
        source_rows.extend(
            source_package.iter_source_intent_rows(
                persona_id, origin, descriptor["shard_ordinal"]
            )
        )
    source_by_key = {row["intent_key"]: row for row in source_rows}
    if len(source_by_key) != len(source_rows) or len(source_rows) != source_manifest["summary"]["source_intent_count"]:
        raise PersonaV2SourceSemanticMembershipPackageError(
            "source origin rows are missing, duplicated, or reordered"
        )

    parent = {intent_key: intent_key for intent_key in source_by_key}
    component_size = {intent_key: 1 for intent_key in source_by_key}

    def find(intent_key):
        if intent_key not in parent:
            raise PersonaV2SourceSemanticMembershipPackageError(
                "reservation references an unknown source intent"
            )
        root = intent_key
        while parent[root] != root:
            root = parent[root]
        while parent[intent_key] != intent_key:
            next_key = parent[intent_key]
            parent[intent_key] = root
            intent_key = next_key
        return root

    def union(left, right):
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return
        if _ascii_key(left_root) > _ascii_key(right_root):
            left_root, right_root = right_root, left_root
        parent[right_root] = left_root
        component_size[left_root] += component_size.pop(right_root)

    overlay_identities = {}
    relation_roles = {intent_key: "independent" for intent_key in source_by_key}
    container_roles = {intent_key: set() for intent_key in source_by_key}

    def bind_identity(intent_key, identity):
        if intent_key not in source_by_key:
            raise PersonaV2SourceSemanticMembershipPackageError(
                "semantic identity references an unknown source intent"
            )
        existing = overlay_identities.get(intent_key)
        if existing is not None and existing != identity:
            raise PersonaV2SourceSemanticMembershipPackageError(
                "overlapping reservations disagree on semantic identity"
            )
        overlay_identities[intent_key] = copy.deepcopy(identity)

    fact_profiles = [
        row for row in catalog["fact_profiles"] if row["persona_id"] == persona_id
    ]
    profiles_by_id = {row["fact_profile_id"]: row for row in fact_profiles}
    singleton_profiles = [
        row for row in fact_profiles if row["profile_kind"] == "w0-singleton"
    ]
    normal_by_graph = {
        row["graph_id"]: row
        for row in fact_profiles
        if row["profile_kind"] == "graph-normal-w0"
    }
    conflict_by_graph_branch = {
        (row["graph_id"], row["branch_role"]): row
        for row in fact_profiles
        if row["profile_kind"] == "conflict-branch"
    }
    empty_profile = profiles_by_id[empty_fact_profile_id(persona_id)]
    topics = [
        row for row in catalog["semantic_topics"] if row["persona_id"] == persona_id
    ]
    topic_by_graph = {row["graph_id"]: row for row in topics}
    topic_by_id = {row["topic_id"]: row for row in topics}
    if (
        len(singleton_profiles) != 32
        or len(normal_by_graph) != 4
        or len(conflict_by_graph_branch) != 8
        or len(topic_by_graph) != 4
    ):
        raise PersonaV2SourceSemanticMembershipPackageError(
            "persona semantic catalog coverage drifted"
        )

    fixed_topics = {}
    fact_profile_overrides = {}
    conflict_rows = []
    relation_row_count = 0
    attachment_row_count = 0
    for row in reservation["reservation_rows"]:
        if row["row_kind"] == "content-relation-reservation":
            relation_row_count += 1
            anchor = row["anchor_intent_key"]
            derivative = row["derivative_intent_key"]
            union(anchor, derivative)
            bind_identity(anchor, row["anchor_identity"])
            bind_identity(derivative, row["derivative_identity"])
            relation_prefix = {
                "exact-duplicate": "exact",
                "near-revision": "near",
                "conflict-copy": "conflict",
            }[row["relation_kind"]]
            relation_roles[anchor] = f"{relation_prefix}-anchor"
            relation_roles[derivative] = f"{relation_prefix}-derivative"
            if row["relation_kind"] == "conflict-copy":
                binding = row["conflict_fact_binding"]
                graph_id = binding["graph_id"]
                topic = topic_by_graph.get(graph_id)
                branch_a = conflict_by_graph_branch.get((graph_id, "a"))
                branch_b = conflict_by_graph_branch.get((graph_id, "b"))
                if (
                    topic is None
                    or branch_a is None
                    or branch_b is None
                    or branch_a["present_fact_ids"]
                    != binding["branch_a_present_fact_ids"]
                    or branch_b["present_fact_ids"]
                    != binding["branch_b_present_fact_ids"]
                    or branch_a["conflict_set_id"] != binding["conflict_set_id"]
                    or branch_b["conflict_set_id"] != binding["conflict_set_id"]
                    or branch_a["conflict_template_key"] != binding["template_key"]
                    or branch_b["conflict_template_key"] != binding["template_key"]
                ):
                    raise PersonaV2SourceSemanticMembershipPackageError(
                        "conflict reservation and branch fact profiles disagree"
                    )
                fixed_topics[anchor] = topic["topic_id"]
                fixed_topics[derivative] = topic["topic_id"]
                fact_profile_overrides[anchor] = branch_a["fact_profile_id"]
                fact_profile_overrides[derivative] = branch_b["fact_profile_id"]
                compact = {
                    "anchor_fact_profile_id": branch_a["fact_profile_id"],
                    "anchor_intent_key": anchor,
                    "cluster_key": row["cluster_key"],
                    "derivative_fact_profile_id": branch_b["fact_profile_id"],
                    "derivative_intent_key": derivative,
                    "row_kind": "fact-conflict-pair-override",
                }
                if set(compact) != CONFLICT_ROW_FIELDS:
                    raise PersonaV2SourceSemanticMembershipPackageError(
                        "compact conflict row schema drifted"
                    )
                conflict_rows.append(compact)
        elif row["row_kind"] == "attachment-membership-reservation":
            attachment_row_count += 1
            host = row["host_intent_key"]
            member = row["standalone_member_intent_key"]
            union(host, member)
            bind_identity(host, row["host_identity"])
            bind_identity(member, row["standalone_member_identity"])
            if row["decoded_payload_equivalence_key"] != row["standalone_member_identity"]["payload_equivalence_key"]:
                raise PersonaV2SourceSemanticMembershipPackageError(
                    "attachment decoded payload identity drifted"
                )
            container_roles[host].add("attachment-host")
            container_roles[member].add("attachment-member")
        else:
            raise PersonaV2SourceSemanticMembershipPackageError(
                "unknown reservation row kind"
            )

    anchor_rows = []
    semantic_anchor_keys = set()
    for anchor in reservation["semantic_anchor_slots"]:
        intent_key = anchor["intent_key"]
        slot_ordinal = anchor["semantic_anchor_slot_ordinal"]
        profile = singleton_profiles[(slot_ordinal - 1) % len(singleton_profiles)]
        topic = topic_by_graph[profile["graph_id"]]
        if intent_key in fixed_topics or find(intent_key) != intent_key or component_size[find(intent_key)] != 1:
            raise PersonaV2SourceSemanticMembershipPackageError(
                "semantic anchor must remain a disjoint singleton component"
            )
        semantic_anchor_keys.add(intent_key)
        fixed_topics[intent_key] = topic["topic_id"]
        fact_profile_overrides[intent_key] = profile["fact_profile_id"]
        compact = {
            "fact_profile_id": profile["fact_profile_id"],
            "intent_key": intent_key,
            "row_kind": "fact-semantic-anchor-override",
            "semantic_anchor_slot_ordinal": slot_ordinal,
        }
        if set(compact) != ANCHOR_ROW_FIELDS:
            raise PersonaV2SourceSemanticMembershipPackageError(
                "compact semantic-anchor row schema drifted"
            )
        anchor_rows.append(compact)

    grouped = {}
    for intent_key in sorted(source_by_key, key=_ascii_key):
        grouped.setdefault(find(intent_key), []).append(intent_key)
    components = [tuple(sorted(values, key=_ascii_key)) for values in grouped.values()]
    components.sort(key=lambda values: _ascii_key(values[0]))
    if max(map(len, components)) > 7:
        raise PersonaV2SourceSemanticMembershipPackageError(
            "reservation component exceeds the exact seven-source bound"
        )

    realism = _catalog_inputs()["realism_by_persona"][persona_id]
    topic_labels = [row["topic_id"] for row in topics]
    topic_targets = _quota_counts(
        persona_id, origin, topic_labels, [1] * len(topic_labels)
    )
    language_labels = [row["language"] for row in realism["language_weights_bp"]]
    language_weights = [row["weight_bp"] for row in realism["language_weights_bp"]]
    language_targets = _quota_counts(
        persona_id, origin, language_labels, language_weights
    )
    topic_assignments, assigned_topics = _component_assignments(
        components, topic_targets, fixed_topics
    )
    language_assignments, assigned_languages = _component_assignments(
        components, language_targets, {}
    )

    semantic_profiles = {
        row["source_profile_id"]: row for row in catalog["semantic_profiles"]
    }
    fact_profile_assignments = {}
    for intent_key, source_row in source_by_key.items():
        override = fact_profile_overrides.get(intent_key)
        if override is not None:
            fact_profile_assignments[intent_key] = override
            continue
        source_semantic_profile = semantic_profiles.get(source_row["source_profile_id"])
        if source_semantic_profile is None:
            raise PersonaV2SourceSemanticMembershipPackageError(
                "source profile does not resolve to a semantic profile"
            )
        if source_semantic_profile["gate_role"] == "raw_only":
            fact_profile_assignments[intent_key] = empty_profile["fact_profile_id"]
        elif source_semantic_profile["gate_role"] in {
            "contract_contributor",
            "incidental_searchable",
        }:
            topic = topic_by_id[topic_assignments[intent_key]]
            fact_profile_assignments[intent_key] = normal_by_graph[topic["graph_id"]][
                "fact_profile_id"
            ]
        else:
            raise PersonaV2SourceSemanticMembershipPackageError(
                "source semantic profile has an unknown gate role"
            )

    exact_profile_counts = {}
    exact_fact_reference_count = 0
    for fact_profile_id_value in fact_profile_assignments.values():
        exact_profile_counts[fact_profile_id_value] = exact_profile_counts.get(
            fact_profile_id_value, 0
        ) + 1
        exact_fact_reference_count += len(
            profiles_by_id[fact_profile_id_value]["present_fact_ids"]
        )
    if (
        len(anchor_rows) != reservation["summary"]["semantic_anchor_slot_count"]
        or len(conflict_rows) != reservation["target_marginals"]["conflict_copy_cluster_count"]
        or relation_row_count != reservation["summary"]["content_relation_row_count"]
        or attachment_row_count != reservation["summary"]["attachment_membership_row_count"]
    ):
        raise PersonaV2SourceSemanticMembershipPackageError(
            "origin reservation projection cardinality drifted"
        )
    return {
        "anchor_rows": anchor_rows,
        "assigned_languages": assigned_languages,
        "assigned_topics": assigned_topics,
        "components": components,
        "conflict_rows": conflict_rows,
        "container_roles": container_roles,
        "exact_fact_reference_count": exact_fact_reference_count,
        "exact_profile_counts": exact_profile_counts,
        "fact_profile_assignments": fact_profile_assignments,
        "fact_profiles_by_id": profiles_by_id,
        "language_assignments": language_assignments,
        "language_targets": language_targets,
        "origin": origin,
        "overlay_identities": overlay_identities,
        "persona_id": persona_id,
        "relation_roles": relation_roles,
        "reservation": reservation,
        "semantic_anchor_keys": semantic_anchor_keys,
        "semantic_profiles": semantic_profiles,
        "source_by_key": source_by_key,
        "source_manifest": source_manifest,
        "source_rows": source_rows,
        "topic_assignments": topic_assignments,
        "topic_targets": topic_targets,
    }


@functools.lru_cache(maxsize=1)
def _origin_plan(persona_id, origin):
    return _build_origin_plan(persona_id, origin)


def _expanded_content_context_row(source_row, plan):
    intent_key = source_row["intent_key"]
    identity = plan["overlay_identities"].get(intent_key)
    if identity is None:
        identity = _source_local_identity(source_row)
    semantic_profile = plan["semantic_profiles"][source_row["source_profile_id"]]
    row = {
        "container_role_ids": sorted(plan["container_roles"][intent_key], key=_ascii_key),
        "content_context_id": source_row["content_context_id"],
        "content_relation_role": plan["relation_roles"][intent_key],
        "deterministic_payload_seed": source_row["deterministic_payload_seed"],
        "intent_key": intent_key,
        "language": plan["language_assignments"][intent_key],
        "logical_period_id": "W0",
        "membership_status": "current",
        "origin": plan["origin"],
        "payload_equivalence_key": identity["payload_equivalence_key"],
        "persona_id": plan["persona_id"],
        "semantic_anchor_capacity": intent_key in plan["semantic_anchor_keys"],
        "semantic_profile_id": semantic_profile["semantic_profile_id"],
        "semantic_version": (
            "v2"
            if plan["relation_roles"][intent_key] == "near-derivative"
            else "v1"
        ),
        "topic_id": plan["topic_assignments"][intent_key],
    }
    if set(row) != EXPANDED_CONTEXT_ROW_FIELDS:
        raise PersonaV2SourceSemanticMembershipPackageError(
            "expanded content-context row schema drifted"
        )
    return row


def _expanded_fact_membership_row(source_row, plan):
    intent_key = source_row["intent_key"]
    identity = plan["overlay_identities"].get(intent_key)
    if identity is None:
        identity = _source_local_identity(source_row)
    fact_profile_id_value = plan["fact_profile_assignments"][intent_key]
    profile = plan["fact_profiles_by_id"][fact_profile_id_value]
    present_fact_ids = list(profile["present_fact_ids"])
    empty = not present_fact_ids
    row = {
        "fact_profile_id": fact_profile_id_value,
        "intent_key": intent_key,
        "logical_branch_key": identity["logical_branch_key"],
        "logical_document_key": identity["logical_document_key"],
        "logical_revision_key": identity["logical_revision_key"],
        "origin": plan["origin"],
        "persona_id": plan["persona_id"],
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
    if set(row) != EXPANDED_MEMBERSHIP_ROW_FIELDS:
        raise PersonaV2SourceSemanticMembershipPackageError(
            "expanded fact-membership row schema drifted"
        )
    return row


def _source_shard_rows(plan, source_shard_ordinal):
    descriptors = plan["source_manifest"]["shard_descriptors"]
    if type(source_shard_ordinal) is not int or not 1 <= source_shard_ordinal <= len(descriptors):
        raise PersonaV2SourceSemanticMembershipPackageError(
            "source shard ordinal is out of range"
        )
    descriptor = descriptors[source_shard_ordinal - 1]
    first = descriptor["first_origin_ordinal"] - 1
    last = descriptor["last_origin_ordinal"]
    rows = plan["source_rows"][first:last]
    if len(rows) != descriptor["row_count"]:
        raise PersonaV2SourceSemanticMembershipPackageError(
            "source shard slice cardinality drifted"
        )
    return descriptor, rows


def iter_expanded_content_context_rows(persona_id, origin, source_shard_ordinal):
    """Yield one source shard's exact content contexts with origin-bounded state."""

    plan = _origin_plan(persona_id, origin)
    _descriptor, rows = _source_shard_rows(plan, source_shard_ordinal)
    for source_row in rows:
        yield _expanded_content_context_row(source_row, plan)


def iter_expanded_fact_membership_rows(persona_id, origin, source_shard_ordinal):
    """Yield one source shard's exact source-owned W0 fact memberships."""

    plan = _origin_plan(persona_id, origin)
    _descriptor, rows = _source_shard_rows(plan, source_shard_ordinal)
    for source_row in rows:
        yield _expanded_fact_membership_row(source_row, plan)


def _expanded_body(rows, *, label, row_cap):
    parts = []
    total = 0
    maximum = 0
    row_count = 0
    for row in rows:
        row_count += 1
        if row_count > MAX_EXPANDED_ROWS_PER_SHARD:
            raise PersonaV2SourceSemanticMembershipPackageError(
                f"{label} exceeds the expanded shard row cap"
            )
        raw = _jsonl_row_bytes(row, label=label, cap=row_cap)
        total += len(raw)
        maximum = max(maximum, len(raw))
        if total > MAX_EXPANDED_SHARD_BODY_BYTES:
            raise PersonaV2SourceSemanticMembershipPackageError(
                f"{label} exceeds the expanded shard body cap"
            )
        parts.append(raw)
    if not parts:
        raise PersonaV2SourceSemanticMembershipPackageError(
            f"{label} cannot be empty"
        )
    return b"".join(parts), maximum


def expanded_content_context_shard_body_bytes(persona_id, origin, source_shard_ordinal):
    body, _maximum = _expanded_body(
        iter_expanded_content_context_rows(persona_id, origin, source_shard_ordinal),
        label="persona v2 expanded content-context row",
        row_cap=MAX_EXPANDED_CONTEXT_ROW_BYTES_INCLUDING_LF,
    )
    return body


def expanded_fact_membership_shard_body_bytes(persona_id, origin, source_shard_ordinal):
    body, _maximum = _expanded_body(
        iter_expanded_fact_membership_rows(persona_id, origin, source_shard_ordinal),
        label="persona v2 expanded fact-membership row",
        row_cap=MAX_EXPANDED_MEMBERSHIP_ROW_BYTES_INCLUDING_LF,
    )
    return body


def _range_receipt_row(plan, source_descriptor):
    shard_ordinal = source_descriptor["shard_ordinal"]
    context_body, context_maximum = _expanded_body(
        (
            _expanded_content_context_row(source_row, plan)
            for source_row in _source_shard_rows(plan, shard_ordinal)[1]
        ),
        label="persona v2 expanded content-context row",
        row_cap=MAX_EXPANDED_CONTEXT_ROW_BYTES_INCLUDING_LF,
    )
    membership_body, membership_maximum = _expanded_body(
        (
            _expanded_fact_membership_row(source_row, plan)
            for source_row in _source_shard_rows(plan, shard_ordinal)[1]
        ),
        label="persona v2 expanded fact-membership row",
        row_cap=MAX_EXPANDED_MEMBERSHIP_ROW_BYTES_INCLUDING_LF,
    )
    row = {
        "expanded_content_context_body_bytes": len(context_body),
        "expanded_content_context_max_row_bytes_including_lf": context_maximum,
        "expanded_content_context_sha256": _sha256(context_body),
        "expanded_fact_membership_body_bytes": len(membership_body),
        "expanded_fact_membership_max_row_bytes_including_lf": membership_maximum,
        "expanded_fact_membership_sha256": _sha256(membership_body),
        "first_intent_key": source_descriptor["first_intent_key"],
        "last_intent_key": source_descriptor["last_intent_key"],
        "row_count": source_descriptor["row_count"],
        "row_kind": "source-shard-total-projection",
        "source_body_sha256": source_descriptor["body_sha256"],
        "source_shard_id": source_descriptor["shard_id"],
    }
    if set(row) != RANGE_ROW_FIELDS:
        raise PersonaV2SourceSemanticMembershipPackageError(
            "compact source-shard range row schema drifted"
        )
    return row


def iter_source_semantic_membership_origin_rows(persona_id, origin):
    """Yield compact range receipts followed by anchor and conflict overrides."""

    plan = _origin_plan(persona_id, origin)
    for descriptor in plan["source_manifest"]["shard_descriptors"]:
        yield _range_receipt_row(plan, descriptor)
    yield from plan["anchor_rows"]
    yield from plan["conflict_rows"]


def source_semantic_membership_origin_body_bytes(persona_id, origin):
    """Return one canonical compact JSONL owner body for an origin."""

    parts = []
    total = 0
    for row in iter_source_semantic_membership_origin_rows(persona_id, origin):
        raw = _jsonl_row_bytes(
            row,
            label="persona v2 compact source semantic membership row",
            cap=MAX_COMPACT_ROW_BYTES_INCLUDING_LF,
        )
        total += len(raw)
        if total > MAX_ORIGIN_BODY_BYTES:
            raise PersonaV2SourceSemanticMembershipPackageError(
                "compact source semantic origin body exceeds four MiB"
            )
        parts.append(raw)
        if len(parts) > MAX_COMPACT_ROWS_PER_ORIGIN:
            raise PersonaV2SourceSemanticMembershipPackageError(
                "compact source semantic origin body exceeds its row cap"
            )
    if not parts:
        raise PersonaV2SourceSemanticMembershipPackageError(
            "compact source semantic origin body cannot be empty"
        )
    return b"".join(parts)


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


def _bound_manifest(name, role, value, *, canonical, digest, coordinate_fields=()):
    raw = canonical(value)
    actual = digest(value)
    if actual != _sha256(raw):
        raise PersonaV2SourceSemanticMembershipPackageError(
            f"{name} manifest digest drifted"
        )
    result = {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "dependency_role": role,
        "name": name,
        "sha256": actual,
    }
    for field in coordinate_fields:
        result[field] = value[field]
    return result


@functools.lru_cache(maxsize=40)
def _canonical_origin_manifest(persona_id, origin):
    plan = _origin_plan(persona_id, origin)
    compact_rows = list(iter_source_semantic_membership_origin_rows(persona_id, origin))
    if len(compact_rows) > MAX_COMPACT_ROWS_PER_ORIGIN:
        raise PersonaV2SourceSemanticMembershipPackageError(
            "compact source semantic origin body exceeds its row cap"
        )
    compact_body = b"".join(
        _jsonl_row_bytes(
            row,
            label="persona v2 compact source semantic membership row",
            cap=MAX_COMPACT_ROW_BYTES_INCLUDING_LF,
        )
        for row in compact_rows
    )
    if len(compact_body) > MAX_ORIGIN_BODY_BYTES:
        raise PersonaV2SourceSemanticMembershipPackageError(
            "compact source semantic origin body exceeds four MiB"
        )
    maximum_row_bytes = max(len(line) + 1 for line in compact_body.splitlines())
    body_descriptor = {
        "body_bytes": len(compact_body),
        "body_sha256": _sha256(compact_body),
        "file_name": f"{persona_id}-source-semantic-membership-{origin}.jsonl",
        "maximum_row_bytes_including_lf": maximum_row_bytes,
        "row_count": len(compact_rows),
    }
    if set(body_descriptor) != ORIGIN_BODY_DESCRIPTOR_FIELDS:
        raise PersonaV2SourceSemanticMembershipPackageError(
            "compact origin body descriptor schema drifted"
        )
    catalog = _canonical_catalog()
    source_manifest = plan["source_manifest"]
    reservation = plan["reservation"]
    input_bindings = [
        _bound_manifest(
            "persona-v2-source-semantic-membership-catalog",
            "semantic-profile-topic-and-fact-profile-owner",
            catalog,
            canonical=canonical_json_bytes,
            digest=source_semantic_membership_catalog_sha256,
        ),
        _bound_manifest(
            "persona-v2-source-inventory-origin-manifest",
            "immutable-source-row-owner",
            source_manifest,
            canonical=source_package.canonical_json_bytes,
            digest=lambda value: source_package.source_intent_origin_manifest_sha256(
                persona_id, origin, value
            ),
            coordinate_fields=("persona_id", "origin"),
        ),
        _bound_manifest(
            "persona-v2-overlay-reservation-origin",
            "matching-relation-container-anchor-and-conflict-reservation",
            reservation,
            canonical=reservation_layout.canonical_json_bytes,
            digest=lambda value: reservation_layout.overlay_reservation_origin_sha256(
                persona_id, origin, value
            ),
            coordinate_fields=("persona_id", "origin"),
        ),
        _artifact_binding(
            "persona-v2-fact-graph",
            "direct-persona-typed-fact-owner",
            _catalog_inputs()["graph_values_by_persona"][persona_id],
            canonical=fact_graph.canonical_json_bytes,
            digest=lambda value: fact_graph.fact_graph_sha256(persona_id, value),
            coordinate_fields=("persona_id",),
        ),
    ]
    range_rows = [row for row in compact_rows if row["row_kind"] == "source-shard-total-projection"]
    anchor_rows = [row for row in compact_rows if row["row_kind"] == "fact-semantic-anchor-override"]
    conflict_rows = [row for row in compact_rows if row["row_kind"] == "fact-conflict-pair-override"]
    profile_counts = [
        {"fact_profile_id": profile_id, "source_count": count}
        for profile_id, count in sorted(
            plan["exact_profile_counts"].items(), key=lambda item: _ascii_key(item[0])
        )
    ]
    value = {
        "artifact_kind": ORIGIN_ARTIFACT_KIND,
        "artifact_schema": ORIGIN_ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": _negative_authority(),
        "body_descriptor": body_descriptor,
        "canonical_limits": {
            "max_compact_body_bytes": MAX_ORIGIN_BODY_BYTES,
            "max_compact_row_bytes_including_lf": MAX_COMPACT_ROW_BYTES_INCLUDING_LF,
            "max_compact_rows": MAX_COMPACT_ROWS_PER_ORIGIN,
            "max_expanded_context_row_bytes_including_lf": MAX_EXPANDED_CONTEXT_ROW_BYTES_INCLUDING_LF,
            "max_expanded_fact_membership_row_bytes_including_lf": MAX_EXPANDED_MEMBERSHIP_ROW_BYTES_INCLUDING_LF,
            "max_expanded_shard_body_bytes": MAX_EXPANDED_SHARD_BODY_BYTES,
            "max_expanded_rows_per_shard": MAX_EXPANDED_ROWS_PER_SHARD,
            "max_manifest_bytes": MAX_ORIGIN_MANIFEST_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_origin_content_context_ids_resolved": True,
            "all_origin_present_fact_set_keys_resolved": True,
            "compact_override_and_range_body_complete": True,
            "expanded_context_and_membership_receipts_complete": True,
            "formal_complete_persona_package_cap_proved": False,
            "matching_reservation_exactly_projected": True,
            "source_inventory_rows_modified": False,
        },
        "completion_scope": (
            "one-origin-source-owned-w0-semantic-context-and-fact-membership-"
            "with-streaming-receipts-no-render-no-solver-no-history-no-execution-no-g0"
        ),
        "dependency_direction_contract": {
            "matching_source_and_reservation_origins_are_strictly_upstream": True,
            "origin_manifest_owns_fact_profile_assignment": True,
            "source_inventory_origin_may_bind_this_manifest": False,
            "streamed_expansions_may_redefine_catalog_fact_sets": False,
        },
        "fact_profile_assignment_counts": profile_counts,
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "hypothesis_status": "authored-benchmark-stress-design-not-observed-user-statistics",
        "input_binding_order": [row["name"] for row in input_bindings],
        "input_bindings": input_bindings,
        "language_quota_counts": [
            {"language": label, "source_count": count}
            for label, count in sorted(plan["assigned_languages"].items(), key=lambda item: _ascii_key(item[0]))
        ],
        "origin": origin,
        "persona_id": persona_id,
        "remaining_blockers": [
            "formal-source-recipes-and-renderer-validator-implementations",
            "concrete-overlay-materialization",
            "history-checkpoint-membership",
            "scope-placement-allocation-and-proof",
            "render-write-chunk-observation-and-kcs-execution",
            "future-complete-persona-package-cap-proof",
        ],
        "summary": {
            "compact_anchor_row_count": len(anchor_rows),
            "compact_conflict_pair_row_count": len(conflict_rows),
            "compact_range_receipt_row_count": len(range_rows),
            "component_count": len(plan["components"]),
            "expanded_content_context_body_bytes": sum(
                row["expanded_content_context_body_bytes"] for row in range_rows
            ),
            "expanded_fact_membership_body_bytes": sum(
                row["expanded_fact_membership_body_bytes"] for row in range_rows
            ),
            "maximum_component_source_count": max(map(len, plan["components"])),
            "maximum_expanded_content_context_row_bytes_including_lf": max(
                row["expanded_content_context_max_row_bytes_including_lf"] for row in range_rows
            ),
            "maximum_expanded_content_context_shard_body_bytes": max(
                row["expanded_content_context_body_bytes"] for row in range_rows
            ),
            "maximum_expanded_fact_membership_row_bytes_including_lf": max(
                row["expanded_fact_membership_max_row_bytes_including_lf"] for row in range_rows
            ),
            "maximum_expanded_fact_membership_shard_body_bytes": max(
                row["expanded_fact_membership_body_bytes"] for row in range_rows
            ),
            "present_fact_reference_count": plan["exact_fact_reference_count"],
            "semantic_version_source_counts": {
                "v1": len(plan["source_rows"])
                - sum(
                    role == "near-derivative"
                    for role in plan["relation_roles"].values()
                ),
                "v2": sum(
                    role == "near-derivative"
                    for role in plan["relation_roles"].values()
                ),
            },
            "source_count": len(plan["source_rows"]),
            "source_shard_count": len(range_rows),
        },
        "topic_quota_counts": [
            {"source_count": count, "topic_id": label}
            for label, count in sorted(plan["assigned_topics"].items(), key=lambda item: _ascii_key(item[0]))
        ],
    }
    if set(value) != ORIGIN_TOP_LEVEL_FIELDS:
        raise PersonaV2SourceSemanticMembershipPackageError(
            "source semantic origin manifest top-level schema drifted"
        )
    _require_negative_authority(value, label="source semantic origin manifest")
    try:
        artifact_common.canonical_json_bytes(
            value,
            label="persona v2 source semantic membership origin manifest",
            max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SourceSemanticMembershipPackageError(str(error)) from None
    return value


def build_source_semantic_membership_origin_manifest(persona_id, origin):
    return copy.deepcopy(_canonical_origin_manifest(persona_id, origin))


def validate_source_semantic_membership_origin_manifest(persona_id, origin, value):
    expected = build_source_semantic_membership_origin_manifest(persona_id, origin)
    if canonical_json_bytes(value) != canonical_json_bytes(expected):
        raise PersonaV2SourceSemanticMembershipPackageError(
            "source semantic origin manifest differs from exact regeneration"
        )
    return True


def source_semantic_membership_origin_manifest_sha256(persona_id, origin, value=None):
    if value is None:
        value = build_source_semantic_membership_origin_manifest(persona_id, origin)
    validate_source_semantic_membership_origin_manifest(persona_id, origin, value)
    return _sha256(canonical_json_bytes(value))


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


def _profile_origins(profile):
    _require_profile(profile)
    return ("pilot",) if profile == "pilot" else ORIGIN_ORDER


def _sum_labeled_rows(manifests, field, label_field):
    result = {}
    for manifest in manifests:
        for row in manifest[field]:
            label = row[label_field]
            result[label] = result.get(label, 0) + row["source_count"]
    return result


@functools.lru_cache(maxsize=40)
def _canonical_profile_manifest(persona_id, profile):
    _require_persona_id(persona_id)
    origins = [
        _canonical_origin_manifest(persona_id, origin)
        for origin in _profile_origins(profile)
    ]
    origin_bindings = [
        _bound_manifest(
            "persona-v2-source-semantic-membership-origin-manifest",
            "immutable-source-semantic-origin-owner",
            manifest,
            canonical=canonical_json_bytes,
            digest=lambda value, origin=manifest["origin"]: source_semantic_membership_origin_manifest_sha256(
                persona_id, origin, value
            ),
            coordinate_fields=("persona_id", "origin"),
        )
        for manifest in origins
    ]
    catalog = _canonical_catalog()
    catalog_binding = _bound_manifest(
        "persona-v2-source-semantic-membership-catalog",
        "semantic-profile-topic-and-fact-profile-owner",
        catalog,
        canonical=canonical_json_bytes,
        digest=source_semantic_membership_catalog_sha256,
    )
    profile_counts = _sum_labeled_rows(
        origins, "fact_profile_assignment_counts", "fact_profile_id"
    )
    language_counts = _sum_labeled_rows(
        origins, "language_quota_counts", "language"
    )
    topic_counts = _sum_labeled_rows(origins, "topic_quota_counts", "topic_id")
    source_count = sum(row["summary"]["source_count"] for row in origins)
    pilot_origin_binding = origin_bindings[0]
    if (
        pilot_origin_binding["origin"] != "pilot"
        or (profile == "full" and [row["origin"] for row in origin_bindings] != list(ORIGIN_ORDER))
    ):
        raise PersonaV2SourceSemanticMembershipPackageError(
            "profile origin composition or pilot reuse order drifted"
        )
    value = {
        "artifact_kind": PROFILE_ARTIFACT_KIND,
        "artifact_schema": PROFILE_ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": _negative_authority(),
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
            "one-persona-pilot-or-full-w0-source-semantic-membership-composition-"
            "with-exact-pilot-reuse-no-render-no-solver-no-history-no-execution-no-g0"
        ),
        "dependency_direction_contract": {
            "full_profile_origin_order_is_pilot_then-full-residual": True,
            "full_profile_must_reuse_exact_pilot_origin_manifest": True,
            "origin_manifests_are_strictly_upstream": True,
            "profile_may_bind_future_execution_artifact": False,
        },
        "fact_profile_assignment_counts": [
            {"fact_profile_id": label, "source_count": count}
            for label, count in sorted(profile_counts.items(), key=lambda item: _ascii_key(item[0]))
        ],
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "hypothesis_status": "authored-benchmark-stress-design-not-observed-user-statistics",
        "language_quota_counts": [
            {"language": label, "source_count": count}
            for label, count in sorted(language_counts.items(), key=lambda item: _ascii_key(item[0]))
        ],
        "origin_manifest_bindings": origin_bindings,
        "origin_order": [row["origin"] for row in origins],
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
            "compact_body_bytes": sum(row["body_descriptor"]["body_bytes"] for row in origins),
            "compact_row_count": sum(row["body_descriptor"]["row_count"] for row in origins),
            "expanded_content_context_body_bytes": sum(
                row["summary"]["expanded_content_context_body_bytes"] for row in origins
            ),
            "expanded_fact_membership_body_bytes": sum(
                row["summary"]["expanded_fact_membership_body_bytes"] for row in origins
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
            "source_shard_count": sum(row["summary"]["source_shard_count"] for row in origins),
        },
        "topic_quota_counts": [
            {"source_count": count, "topic_id": label}
            for label, count in sorted(topic_counts.items(), key=lambda item: _ascii_key(item[0]))
        ],
    }
    expected_source_count = envelope.profile_file_count(persona_id, profile)
    if source_count != expected_source_count or set(value) != PROFILE_TOP_LEVEL_FIELDS:
        raise PersonaV2SourceSemanticMembershipPackageError(
            "source semantic profile manifest schema or source total drifted"
        )
    _require_negative_authority(value, label="source semantic profile manifest")
    try:
        artifact_common.canonical_json_bytes(
            value,
            label="persona v2 source semantic membership profile manifest",
            max_bytes=MAX_PROFILE_MANIFEST_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SourceSemanticMembershipPackageError(str(error)) from None
    return value


def build_source_semantic_membership_profile_manifest(persona_id, profile):
    return copy.deepcopy(_canonical_profile_manifest(persona_id, profile))


def validate_source_semantic_membership_profile_manifest(persona_id, profile, value):
    expected = build_source_semantic_membership_profile_manifest(persona_id, profile)
    if canonical_json_bytes(value) != canonical_json_bytes(expected):
        raise PersonaV2SourceSemanticMembershipPackageError(
            "source semantic profile manifest differs from exact regeneration"
        )
    return True


def source_semantic_membership_profile_manifest_sha256(persona_id, profile, value=None):
    if value is None:
        value = build_source_semantic_membership_profile_manifest(persona_id, profile)
    validate_source_semantic_membership_profile_manifest(persona_id, profile, value)
    return _sha256(canonical_json_bytes(value))


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


def _build_canonical_suite_descriptor():
    catalog = _canonical_catalog()
    source_suite = source_package.build_source_intent_suite_descriptor()
    reservation_suite = reservation_layout.build_overlay_reservation_suite()
    source_package.validate_source_intent_suite_descriptor(source_suite)
    reservation_layout.validate_overlay_reservation_suite(reservation_suite)
    origins = [
        _canonical_origin_manifest(persona_id, origin)
        for persona_id in envelope.PERSONA_IDS
        for origin in ORIGIN_ORDER
    ]
    profiles = [
        _canonical_profile_manifest(persona_id, profile)
        for persona_id in envelope.PERSONA_IDS
        for profile in PROFILE_ORDER
    ]
    profile_by_coordinate = {
        (row["persona_id"], row["profile"]): row for row in profiles
    }
    for persona_id in envelope.PERSONA_IDS:
        pilot_profile = profile_by_coordinate[(persona_id, "pilot")]
        full_profile = profile_by_coordinate[(persona_id, "full")]
        if (
            len(pilot_profile["origin_manifest_bindings"]) != 1
            or pilot_profile["origin_manifest_bindings"][0]
            != full_profile["origin_manifest_bindings"][0]
        ):
            raise PersonaV2SourceSemanticMembershipPackageError(
                "full profile does not reuse the exact pilot origin binding"
            )
    origin_bindings = [
        _bound_manifest(
            "persona-v2-source-semantic-membership-origin-manifest",
            "source-semantic-origin-owner",
            manifest,
            canonical=canonical_json_bytes,
            digest=lambda value, persona_id=manifest["persona_id"], origin=manifest["origin"]: source_semantic_membership_origin_manifest_sha256(
                persona_id, origin, value
            ),
            coordinate_fields=("persona_id", "origin"),
        )
        for manifest in origins
    ]
    profile_bindings = [
        _bound_manifest(
            "persona-v2-source-semantic-membership-profile-manifest",
            "source-semantic-profile-composition",
            manifest,
            canonical=canonical_json_bytes,
            digest=lambda value, persona_id=manifest["persona_id"], profile=manifest["profile"]: source_semantic_membership_profile_manifest_sha256(
                persona_id, profile, value
            ),
            coordinate_fields=("persona_id", "profile"),
        )
        for manifest in profiles
    ]
    catalog_binding = _bound_manifest(
        "persona-v2-source-semantic-membership-catalog",
        "semantic-profile-topic-and-fact-profile-owner",
        catalog,
        canonical=canonical_json_bytes,
        digest=source_semantic_membership_catalog_sha256,
    )
    input_bindings = [
        _artifact_binding(
            "persona-v2-source-inventory-suite",
            "global-immutable-source-inventory",
            source_suite,
            canonical=source_package.canonical_json_bytes,
            digest=source_package.source_intent_suite_descriptor_sha256,
        ),
        _artifact_binding(
            "persona-v2-overlay-reservation-suite",
            "global-overlay-reservation-index",
            reservation_suite,
            canonical=reservation_layout.overlay_reservation_suite_bytes,
            digest=reservation_layout.overlay_reservation_suite_sha256,
        ),
    ]
    profile_kind_by_id = {
        row["fact_profile_id"]: row["profile_kind"]
        for row in catalog["fact_profiles"]
    }
    kind_counts = {kind: 0 for kind in ("empty", "graph-normal-w0", "w0-singleton", "conflict-branch")}
    for manifest in origins:
        for row in manifest["fact_profile_assignment_counts"]:
            kind_counts[profile_kind_by_id[row["fact_profile_id"]]] += row["source_count"]

    source_ledgers = {
        row["persona_id"]: row
        for row in source_suite["persona_current_component_byte_ledgers"]
    }
    reservation_bytes = {persona_id: 0 for persona_id in envelope.PERSONA_IDS}
    for binding in reservation_suite["origin_bindings"]:
        reservation_bytes[binding["persona_id"]] += binding["canonical_bytes"]
    origin_by_persona = {
        persona_id: [row for row in origins if row["persona_id"] == persona_id]
        for persona_id in envelope.PERSONA_IDS
    }
    profile_by_persona = {
        persona_id: [row for row in profiles if row["persona_id"] == persona_id]
        for persona_id in envelope.PERSONA_IDS
    }
    catalog_bytes = len(canonical_json_bytes(catalog))
    ledgers = []
    for persona_id in envelope.PERSONA_IDS:
        persona_origins = origin_by_persona[persona_id]
        persona_profiles = profile_by_persona[persona_id]
        compact_body_bytes = sum(
            row["body_descriptor"]["body_bytes"] for row in persona_origins
        )
        semantic_origin_manifest_bytes = sum(
            len(canonical_json_bytes(row)) for row in persona_origins
        )
        semantic_profile_manifest_bytes = sum(
            len(canonical_json_bytes(row)) for row in persona_profiles
        )
        existing_source_component_bytes = source_ledgers[persona_id][
            "current_component_bytes"
        ]
        current = (
            existing_source_component_bytes
            + reservation_bytes[persona_id]
            + catalog_bytes
            + compact_body_bytes
            + semantic_origin_manifest_bytes
            + semantic_profile_manifest_bytes
        )
        if current > MAX_PERSONA_PACKAGE_BYTES:
            raise PersonaV2SourceSemanticMembershipPackageError(
                f"current semantic membership component exceeds 16 MiB for {persona_id}"
            )
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
        "authority": _negative_authority(),
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
            "with-compact-owner-bodies-and-streaming-receipts-no-render-no-solver-"
            "no-history-no-execution-no-g0"
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
            "compact_origin_rows": "source-shard-total-projection-then-fact-semantic-anchor-override-then-fact-conflict-pair-override",
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
            "compact_anchor_row_count": sum(row["summary"]["compact_anchor_row_count"] for row in origins),
            "compact_body_bytes": sum(row["body_descriptor"]["body_bytes"] for row in origins),
            "compact_conflict_pair_row_count": sum(row["summary"]["compact_conflict_pair_row_count"] for row in origins),
            "compact_range_receipt_row_count": sum(row["summary"]["compact_range_receipt_row_count"] for row in origins),
            "compact_row_count": sum(row["body_descriptor"]["row_count"] for row in origins),
            "expanded_content_context_body_bytes": sum(row["summary"]["expanded_content_context_body_bytes"] for row in origins),
            "expanded_fact_membership_body_bytes": sum(row["summary"]["expanded_fact_membership_body_bytes"] for row in origins),
            "fact_profile_kind_source_counts": kind_counts,
            "maximum_compact_row_bytes_including_lf": max(row["body_descriptor"]["maximum_row_bytes_including_lf"] for row in origins),
            "maximum_component_source_count": max(row["summary"]["maximum_component_source_count"] for row in origins),
            "maximum_expanded_content_context_row_bytes_including_lf": max(row["summary"]["maximum_expanded_content_context_row_bytes_including_lf"] for row in origins),
            "maximum_expanded_content_context_shard_body_bytes": max(row["summary"]["maximum_expanded_content_context_shard_body_bytes"] for row in origins),
            "maximum_expanded_fact_membership_row_bytes_including_lf": max(row["summary"]["maximum_expanded_fact_membership_row_bytes_including_lf"] for row in origins),
            "maximum_expanded_fact_membership_shard_body_bytes": max(row["summary"]["maximum_expanded_fact_membership_shard_body_bytes"] for row in origins),
            "origin_manifest_count": len(origins),
            "present_fact_reference_count": sum(row["summary"]["present_fact_reference_count"] for row in origins),
            "profile_manifest_count": len(profiles),
            "semantic_version_source_counts": semantic_version_counts,
            "source_count": sum(row["summary"]["source_count"] for row in origins),
            "source_shard_count": sum(row["summary"]["source_shard_count"] for row in origins),
        },
    }
    expected_summary = {
        "compact_anchor_row_count": EXPECTED_SEMANTIC_ANCHOR_COUNT,
        "compact_conflict_pair_row_count": EXPECTED_CONFLICT_CLUSTER_COUNT,
        "compact_row_count": (
            EXPECTED_SOURCE_SHARD_COUNT
            + EXPECTED_SEMANTIC_ANCHOR_COUNT
            + EXPECTED_CONFLICT_CLUSTER_COUNT
        ),
        "compact_range_receipt_row_count": EXPECTED_SOURCE_SHARD_COUNT,
        "origin_manifest_count": EXPECTED_ORIGIN_COUNT,
        "profile_manifest_count": EXPECTED_PROFILE_COUNT,
        "source_count": EXPECTED_SOURCE_COUNT,
        "source_shard_count": EXPECTED_SOURCE_SHARD_COUNT,
    }
    if (
        any(value["summary"][key] != expected for key, expected in expected_summary.items())
        or kind_counts
        != {
            "conflict-branch": EXPECTED_CONFLICT_ENDPOINT_COUNT,
            "empty": 73_350,
            "graph-normal-w0": 124_430,
            "w0-singleton": EXPECTED_SEMANTIC_ANCHOR_COUNT,
        }
        or semantic_version_counts != {"v1": 189_770, "v2": 13_230}
        or value["summary"]["present_fact_reference_count"] != 1_019_380
        or value["summary"]["maximum_expanded_content_context_shard_body_bytes"]
        > MAX_EXPANDED_SHARD_BODY_BYTES
        or value["summary"]["maximum_expanded_fact_membership_shard_body_bytes"]
        > MAX_EXPANDED_SHARD_BODY_BYTES
        or set(value) != SUITE_TOP_LEVEL_FIELDS
    ):
        raise PersonaV2SourceSemanticMembershipPackageError(
            "source semantic suite exact coverage drifted"
        )
    _require_negative_authority(value, label="source semantic membership suite")
    try:
        artifact_common.canonical_json_bytes(
            value,
            label="persona v2 source semantic membership suite",
            max_bytes=MAX_SUITE_DESCRIPTOR_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SourceSemanticMembershipPackageError(str(error)) from None
    return value


def _release_generation_caches():
    """Drop verbose source/reservation derivations after suite projection."""

    for module, names in (
        (
            reservation_layout,
            ("_canonical_origin", "_intent_slot_tuples_by_variant"),
        ),
        (
            source_package,
            (
                "_canonical_shard_descriptor",
                "_canonical_origin_manifest",
                "_canonical_profile_manifest",
                "_canonical_suite_descriptor",
                "_shared_inputs",
            ),
        ),
    ):
        for name in names:
            candidate = getattr(module, name, None)
            clear = getattr(candidate, "cache_clear", None)
            if callable(clear):
                clear()
    _origin_plan.cache_clear()


@functools.lru_cache(maxsize=1)
def _canonical_suite_descriptor():
    try:
        return _build_canonical_suite_descriptor()
    finally:
        _release_generation_caches()


def build_source_semantic_membership_suite_descriptor():
    return copy.deepcopy(_canonical_suite_descriptor())


def validate_source_semantic_membership_suite_descriptor(value):
    expected = build_source_semantic_membership_suite_descriptor()
    if canonical_json_bytes(value) != canonical_json_bytes(expected):
        raise PersonaV2SourceSemanticMembershipPackageError(
            "source semantic membership suite differs from exact regeneration"
        )
    return True


def source_semantic_membership_suite_descriptor_sha256(value=None):
    if value is None:
        value = build_source_semantic_membership_suite_descriptor()
    validate_source_semantic_membership_suite_descriptor(value)
    return _sha256(canonical_json_bytes(value))


def require_complete_source_semantic_membership_package():
    raise PersonaV2SourceSemanticMembershipPackageError(
        "all 203,000 W0 content contexts and source-owned fact memberships are "
        "deterministically bound, but formal recipes, missing renderer/validator "
        "implementations, concrete overlay materialization, history, allocation, "
        "render/write/chunk observation, complete package-cap proof, execution, "
        "and G0 authority remain absent"
    )


__all__ = [
    "ANCHOR_ROW_FIELDS",
    "AUTHORITY_FIELDS",
    "CATALOG_ARTIFACT_KIND",
    "CATALOG_ARTIFACT_SCHEMA",
    "CATALOG_TOP_LEVEL_FIELDS",
    "CONFLICT_ROW_FIELDS",
    "EXPANDED_CONTEXT_ROW_FIELDS",
    "EXPANDED_MEMBERSHIP_ROW_FIELDS",
    "FACT_PROFILE_FIELDS",
    "MAX_CATALOG_BYTES",
    "MAX_COMPACT_ROW_BYTES_INCLUDING_LF",
    "MAX_COMPACT_ROWS_PER_ORIGIN",
    "MAX_EXPANDED_CONTEXT_ROW_BYTES_INCLUDING_LF",
    "MAX_EXPANDED_MEMBERSHIP_ROW_BYTES_INCLUDING_LF",
    "MAX_EXPANDED_SHARD_BODY_BYTES",
    "MAX_EXPANDED_ROWS_PER_SHARD",
    "MAX_ORIGIN_BODY_BYTES",
    "MAX_ORIGIN_MANIFEST_BYTES",
    "MAX_PROFILE_MANIFEST_BYTES",
    "MAX_SUITE_DESCRIPTOR_BYTES",
    "ORIGIN_ARTIFACT_KIND",
    "ORIGIN_ARTIFACT_SCHEMA",
    "ORIGIN_BODY_DESCRIPTOR_FIELDS",
    "ORIGIN_TOP_LEVEL_FIELDS",
    "PROFILE_ARTIFACT_KIND",
    "PROFILE_ARTIFACT_SCHEMA",
    "PROFILE_TOP_LEVEL_FIELDS",
    "PersonaV2SourceSemanticMembershipPackageError",
    "RANGE_ROW_FIELDS",
    "SEMANTIC_PROFILE_FIELDS",
    "SUITE_ARTIFACT_KIND",
    "SUITE_ARTIFACT_SCHEMA",
    "SUITE_TOP_LEVEL_FIELDS",
    "TOPIC_FIELDS",
    "build_source_semantic_membership_catalog",
    "build_source_semantic_membership_origin_manifest",
    "build_source_semantic_membership_profile_manifest",
    "build_source_semantic_membership_suite_descriptor",
    "canonical_json_bytes",
    "conflict_fact_profile_id",
    "empty_fact_profile_id",
    "expanded_content_context_shard_body_bytes",
    "expanded_fact_membership_shard_body_bytes",
    "iter_expanded_content_context_rows",
    "iter_expanded_fact_membership_rows",
    "iter_source_semantic_membership_origin_rows",
    "normal_fact_profile_id",
    "require_complete_source_semantic_membership_package",
    "semantic_topic_id",
    "singleton_fact_profile_id",
    "source_semantic_membership_catalog_sha256",
    "source_semantic_membership_origin_body_bytes",
    "source_semantic_membership_origin_manifest_sha256",
    "source_semantic_membership_profile_manifest_sha256",
    "source_semantic_membership_suite_descriptor_sha256",
    "validate_source_semantic_membership_catalog",
    "validate_source_semantic_membership_origin_manifest",
    "validate_source_semantic_membership_profile_manifest",
    "validate_source_semantic_membership_suite_descriptor",
]
