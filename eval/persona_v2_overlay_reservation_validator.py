"""Builder-independent semantic validation for overlay reservations.

This module deliberately does not import ``persona_v2_overlay_reservation_layout``.
It reconstructs the admissible source-key domain, exact overlay targets, and
persona-local conflict templates from the public upstream artifacts.  The
validator therefore checks reservation semantics without treating regeneration
by the producer as independent evidence.
"""

from __future__ import annotations

import functools
import hashlib
import itertools
import re

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_fact_graph as fact_graph
    from . import persona_v2_overlay_contract as overlay_contract
    from . import persona_v2_source_inventory_layout as source_layout
    from . import persona_v2_variant_catalog as variant_catalog
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_fact_graph as fact_graph
    import persona_v2_overlay_contract as overlay_contract
    import persona_v2_source_inventory_layout as source_layout
    import persona_v2_variant_catalog as variant_catalog


ORIGIN_ARTIFACT_SCHEMA = "kio.persona.pc-overlay-reservation-origin/v2"
ORIGIN_ARTIFACT_KIND = "persona-pc-v2-overlay-reservation-origin"
SUITE_ARTIFACT_SCHEMA = "kio.persona.pc-overlay-reservation-suite/v2"
SUITE_ARTIFACT_KIND = "persona-pc-v2-overlay-reservation-suite"
ARTIFACT_SCHEMA_VERSION = 2

MAX_ORIGIN_ARTIFACT_BYTES = 4 * 2**20
MAX_SUITE_ARTIFACT_BYTES = 256 * 1024
MAX_RESERVATION_ROW_BYTES = 2_048
MAX_ROWS_PER_ORIGIN = 4_096

ORIGIN_ORDER = ("pilot", "full-residual")
ORIGIN_TO_TARGET_PROFILE = {
    "pilot": "pilot",
    "full-residual": "full-minus-pilot",
}
RELATION_ORDER = tuple(overlay_contract.CONTENT_RELATION_ORDER)
PLACEMENT_ORDER = tuple(overlay_contract.PLACEMENT_CLASS_ORDER)
MEMBERS_PER_HOST_ORDER = (1, 2, 3, 4, 5)
ATTACHMENT_HOST_STRESS_WEIGHTS = (10, 4, 3, 2, 1)
PILOT_SEMANTIC_ANCHOR_SLOT_COUNT = 105

AUTHORITY_FIELDS = frozenset(
    {
        "actual_chunks_attested",
        "authorizes_concrete_overlay_membership",
        "authorizes_g0_freeze",
        "authorizes_history_mutation",
        "authorizes_kio_execution",
        "authorizes_physical_write",
        "authorizes_renderer_execution",
        "authorizes_solver_execution",
        "authorizes_source_inventory",
        "authorizes_source_plan",
        "concrete_fact_membership_bound",
        "concrete_source_intent_manifest_bound",
        "filesystem_writer_available",
        "formal_capacity_gate_satisfied",
        "history_executor_available",
        "kio_execution_available",
        "query_instances_rendered",
        "renderer_available",
        "scope_assignment_present",
        "source_rows_materialized",
        "validator_available",
    }
)

IDENTITY_FIELDS = frozenset(
    {
        "logical_branch_key",
        "logical_document_key",
        "logical_revision_key",
        "payload_equivalence_key",
        "semantic_section_key",
    }
)
RELATION_ROW_FIELDS = frozenset(
    {
        "anchor_identity",
        "anchor_intent_key",
        "cluster_context_seed",
        "cluster_key",
        "content_recipe_profile_id",
        "derivative_identity",
        "derivative_intent_key",
        "endpoint_gate_role",
        "endpoint_variant_id",
        "placement_class_requirement",
        "relation_kind",
        "row_kind",
    }
)
CONFLICT_BINDING_FIELDS = frozenset(
    {
        "branch_a_present_fact_ids",
        "branch_a_selected_fact_id",
        "branch_b_present_fact_ids",
        "branch_b_selected_fact_id",
        "conflict_set_id",
        "fact_template_reuse_ordinal",
        "graph_id",
        "template_key",
        "unordered_member_fact_ids",
    }
)
ATTACHMENT_ROW_FIELDS = frozenset(
    {
        "attachment_context_seed",
        "attachment_key",
        "content_relation_membership",
        "decoded_payload_equivalence_key",
        "embedded_member_identity_source",
        "host_gate_role",
        "host_identity",
        "host_intent_key",
        "host_member_count",
        "host_ordinal",
        "host_variant_id",
        "member_ordinal",
        "row_kind",
        "standalone_member_gate_role",
        "standalone_member_identity",
        "standalone_member_intent_key",
        "standalone_member_variant_id",
    }
)

ORIGIN_TOP_LEVEL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "canonical_limits",
        "completion_claims",
        "completion_scope",
        "conflict_fact_templates",
        "dependency_direction_contract",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
        "hypothesis_status",
        "input_bindings",
        "origin",
        "persona_id",
        "relation_placement_joint_marginals",
        "remaining_blockers",
        "reservation_contract",
        "reservation_rows",
        "semantic_anchor_slots",
        "summary",
        "target_marginals",
        "target_profile",
        "variant_usage_marginals",
    }
)
SUITE_TOP_LEVEL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "canonical_limits",
        "completion_scope",
        "fixture_id",
        "fixture_schema_version",
        "full_composition_contract",
        "g0_contract_frozen",
        "input_bindings",
        "orders",
        "origin_bindings",
        "remaining_blockers",
        "suite_summary",
    }
)

_INTENT_KEY_RE = re.compile(
    r"^(p(?:0[1-9]|1[0-9]|20))-intent-"
    r"(pilot|full-residual)-syn-([0-9]{4,5})$"
)
_LOWER_ASCII_KEY_RE = re.compile(r"^[a-z][a-z0-9-]{0,119}$")
_FORBIDDEN_KEY_TOKEN_RE = re.compile(
    r"(?:^|_)(?:query|oracle|rendered|solution|solved|final)(?:_|$)"
)
_ALLOWED_NEGATIVE_GUARD_FIELDS = frozenset(
    {
        "evaluation_query_or_oracle_identity_imported",
        "query_instances_rendered",
        "semantic_anchor_slots_are_corpus_capacity_not_query_mapping",
        "solved_scope_or_final_identity_allowed",
    }
)
_EXPLICIT_FORBIDDEN_FIELDS = frozenset(
    {
        "allocation_solution_sha256",
        "canonical_allocation_solution_sha256",
        "final_materialization_id",
        "final_source_id",
        "final_source_plan_sha256",
        "history_event_key",
        "materialization_id",
        "physical_path",
        "query_id",
        "query_instance_id",
        "raw_bytes",
        "rendered_body",
        "rendered_bytes",
        "rendered_sha256",
        "scope_id",
        "scope_key",
        "source_row",
        "target_intent_key",
    }
)

# A receipt is keyed by the complete canonical body, not by object identity.
# It only avoids repeating the row-level proof when a suite validates the exact
# same immutable bytes that a caller has already validated individually.
_VALIDATED_ORIGIN_DIGESTS = set()


class PersonaV2OverlayReservationValidationError(ValueError):
    """Raised when a reservation fails independent semantic validation."""


def _fail(message):
    raise PersonaV2OverlayReservationValidationError(message)


def _require_exact_fields(value, expected, *, label):
    if type(value) is not dict or set(value) != set(expected):
        _fail(f"{label} must contain the exact field set")


def _require_all_false_authority(value, *, label):
    if type(value) is not dict or set(value) != AUTHORITY_FIELDS:
        _fail(f"{label} authority field set drifted")
    if any(type(flag) is not bool or flag is not False for flag in value.values()):
        _fail(f"{label} authority must be all-false booleans")


def _reject_forbidden_fields(value, *, path="$"):
    if type(value) is dict:
        for key, child in value.items():
            if type(key) is not str:
                _fail(f"{path} contains a non-string field name")
            if key in _EXPLICIT_FORBIDDEN_FIELDS:
                _fail(f"{path}.{key} is forbidden in a pre-source reservation")
            if (
                key not in _ALLOWED_NEGATIVE_GUARD_FIELDS
                and _FORBIDDEN_KEY_TOKEN_RE.search(key)
            ):
                _fail(f"{path}.{key} imports a solved/final/query/rendered field")
            _reject_forbidden_fields(child, path=f"{path}.{key}")
    elif type(value) is list:
        for index, child in enumerate(value):
            _reject_forbidden_fields(child, path=f"{path}[{index}]")


def _canonical_bytes(value, *, label, max_bytes):
    try:
        return artifact_common.canonical_json_bytes(
            value, label=label, max_bytes=max_bytes
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _public_binding(name, role, value, *, validate, canonical, digest=None):
    validate(value)
    raw = canonical(value)
    actual = hashlib.sha256(raw).hexdigest()
    if digest is not None and digest(value) != actual:
        _fail(f"{name} public digest differs from canonical bytes")
    return {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "dependency_role": role,
        "fixture_id": value["fixture_id"],
        "fixture_schema_version": value["fixture_schema_version"],
        "name": name,
        "sha256": actual,
    }


@functools.lru_cache(maxsize=1)
def _upstream_inputs():
    overlay_value = overlay_contract.build_overlay_contract()
    source_value = source_layout.build_source_inventory_layout()
    variant_value = variant_catalog.build_variant_catalog()
    roles = {
        row["variant_id"]: row["gate_role"]
        for row in variant_value["variant_rows"]
    }
    targets = {
        row["persona_id"]: row
        for row in overlay_value["persona_target_marginals"]
    }
    layouts = {row["persona_id"]: row for row in source_value["personas"]}
    if tuple(targets) != envelope.PERSONA_IDS or tuple(layouts) != envelope.PERSONA_IDS:
        _fail("upstream persona ordering or coverage drifted")
    bindings = [
        _public_binding(
            "overlay-contract",
            "overlay-semantics-and-target-marginals",
            overlay_value,
            validate=overlay_contract.validate_overlay_contract,
            canonical=overlay_contract.canonical_json_bytes,
            digest=overlay_contract.overlay_contract_sha256,
        ),
        _public_binding(
            "source-inventory-layout",
            "reserved-source-intent-keyspace-and-variant-ranges",
            source_value,
            validate=source_layout.validate_source_inventory_layout,
            canonical=source_layout.canonical_json_bytes,
            digest=source_layout.source_inventory_layout_sha256,
        ),
        _public_binding(
            "variant-catalog",
            "gate-role-and-variant-identity",
            variant_value,
            validate=variant_catalog.validate_variant_catalog,
            canonical=variant_catalog.canonical_json_bytes,
            digest=variant_catalog.variant_catalog_sha256,
        ),
    ]
    return {
        "base_bindings": bindings,
        "layouts": layouts,
        "roles": roles,
        "targets": targets,
    }


@functools.lru_cache(maxsize=40)
def _source_domain(persona_id, origin):
    if persona_id not in envelope.PERSONA_IDS or origin not in ORIGIN_ORDER:
        _fail(f"unknown persona/origin: {persona_id!r}/{origin!r}")
    layout = _upstream_inputs()["layouts"][persona_id]
    result = {}
    for reservation in layout["variant_reservations"][origin]:
        variant_id = reservation["variant_id"]
        for ordinal in range(
            reservation["first_origin_ordinal"],
            reservation["last_origin_ordinal"] + 1,
        ):
            key = source_layout.intent_key(persona_id, origin, ordinal)
            if key in result:
                _fail(f"upstream source key is duplicated: {key}")
            result[key] = variant_id
        if (
            reservation["last_origin_ordinal"]
            - reservation["first_origin_ordinal"]
            + 1
            != reservation["row_count"]
        ):
            _fail("upstream variant reservation row count drifted")
    expected = (
        layout["pilot_source_count"]
        if origin == "pilot"
        else layout["full_residual_source_count"]
    )
    if len(result) != expected:
        _fail(f"upstream source domain is incomplete for {persona_id}/{origin}")
    return result


def _resolve_intent(intent_key, *, persona_id, origin, source_domain):
    if type(intent_key) is not str or _INTENT_KEY_RE.fullmatch(intent_key) is None:
        _fail(f"invalid source intent key: {intent_key!r}")
    match = _INTENT_KEY_RE.fullmatch(intent_key)
    if match.group(1) != persona_id or match.group(2) != origin:
        _fail(f"cross-persona/origin source intent reference: {intent_key}")
    if intent_key not in source_domain:
        _fail(f"source intent is outside the upstream reservation: {intent_key}")
    return source_domain[intent_key]


def _intent_ordinal(intent_key):
    return int(_INTENT_KEY_RE.fullmatch(intent_key).group(3))


def _ordinal_width(origin):
    return 4 if origin == "pilot" else 5


def _identity(
    document, branch, revision, section, payload
):
    return {
        "logical_branch_key": branch,
        "logical_document_key": document,
        "logical_revision_key": revision,
        "payload_equivalence_key": payload,
        "semantic_section_key": section,
    }


def _identity_stem(persona_id, origin, intent_key):
    ordinal = _intent_ordinal(intent_key)
    width = _ordinal_width(origin)
    base = f"{persona_id}-{{kind}}-{origin}-syn-{ordinal:0{width}d}"
    return {
        "document": base.format(kind="logical-document"),
        "section": base.format(kind="logical-section") + "-s0001",
        "branch_1": base.format(kind="logical-branch") + "-b01",
        "branch_2": base.format(kind="logical-branch") + "-b02",
        "revision_1_1": base.format(kind="logical-revision") + "-b01-r0001",
        "revision_1_2": base.format(kind="logical-revision") + "-b01-r0002",
        "revision_2_1": base.format(kind="logical-revision") + "-b02-r0001",
        "payload_base": f"{persona_id}-payload-{origin}-syn-{ordinal:0{width}d}",
    }


def _expected_content_identities(persona_id, origin, relation, anchor_key):
    keys = _identity_stem(persona_id, origin, anchor_key)
    if relation == "exact-duplicate":
        payload = keys["payload_base"] + "-exact-shared"
        value = _identity(
            keys["document"],
            keys["branch_1"],
            keys["revision_1_1"],
            keys["section"],
            payload,
        )
        return value, dict(value), "same-raw-and-decoded-payload-v2"
    if relation == "near-revision":
        return (
            _identity(
                keys["document"],
                keys["branch_1"],
                keys["revision_1_1"],
                keys["section"],
                keys["payload_base"] + "-near-r0001",
            ),
            _identity(
                keys["document"],
                keys["branch_1"],
                keys["revision_1_2"],
                keys["section"],
                keys["payload_base"] + "-near-r0002",
            ),
            "same-document-visible-later-revision-v2",
        )
    if relation == "conflict-copy":
        return (
            _identity(
                keys["document"],
                keys["branch_1"],
                keys["revision_1_1"],
                keys["section"],
                keys["payload_base"] + "-conflict-b01",
            ),
            _identity(
                keys["document"],
                keys["branch_2"],
                keys["revision_2_1"],
                keys["section"],
                keys["payload_base"] + "-conflict-b02",
            ),
            "same-document-neutral-distinct-branches-v2",
        )
    _fail(f"unknown relation kind: {relation!r}")


def _expected_singleton_identity(persona_id, origin, intent_key, suffix):
    keys = _identity_stem(persona_id, origin, intent_key)
    return _identity(
        keys["document"],
        keys["branch_1"],
        keys["revision_1_1"],
        keys["section"],
        keys["payload_base"] + f"-{suffix}",
    )


def _require_identity(value, expected, *, label):
    _require_exact_fields(value, IDENTITY_FIELDS, label=label)
    if value != expected:
        _fail(f"{label} violates the logical identity recipe")
    if any(
        type(field) is not str or _LOWER_ASCII_KEY_RE.fullmatch(field) is None
        for field in value.values()
    ):
        _fail(f"{label} contains a non-canonical logical key")


@functools.lru_cache(maxsize=20)
def _expected_conflict_inputs(persona_id):
    graph_value = fact_graph.build_fact_graph(persona_id)
    templates = []
    for ordinal, graph in enumerate(
        sorted(graph_value["graphs"], key=lambda row: row["graph_id"].encode("ascii")),
        start=1,
    ):
        if len(graph["conflict_sets"]) != 1:
            _fail("each authored fact graph must have one conflict set")
        conflict_set = graph["conflict_sets"][0]
        pair = sorted(conflict_set["member_fact_ids"], key=lambda item: item.encode("ascii"))
        facts = {row["fact_id"]: row for row in graph["facts"]}
        current = []
        for fact_id, fact in facts.items():
            states = [
                row["state"]
                for row in fact["visibility_by_checkpoint"]
                if row["checkpoint"] == "W0"
            ]
            if len(states) != 1:
                _fail("fact graph has a non-total W0 state")
            if states[0] == "current":
                current.append(fact_id)
        current.sort(key=lambda item: item.encode("ascii"))
        common = [fact_id for fact_id in current if fact_id not in pair]
        if (
            len(pair) != 2
            or len(current) != 8
            or len(common) != 6
            or not set(pair).issubset(current)
            or facts[pair[0]]["subject_entity_id"]
            != facts[pair[1]]["subject_entity_id"]
            or facts[pair[0]]["predicate_id"] != facts[pair[1]]["predicate_id"]
            or facts[pair[0]]["typed_value"] == facts[pair[1]]["typed_value"]
        ):
            _fail(f"invalid W0 conflict template for {persona_id}/{graph['graph_id']}")
        templates.append(
            {
                "branch_a_present_fact_ids": sorted(
                    common + [pair[0]], key=lambda item: item.encode("ascii")
                ),
                "branch_a_selected_fact_id": pair[0],
                "branch_b_present_fact_ids": sorted(
                    common + [pair[1]], key=lambda item: item.encode("ascii")
                ),
                "branch_b_selected_fact_id": pair[1],
                "common_w0_current_fact_ids": common,
                "conflict_set_id": conflict_set["conflict_set_id"],
                "graph_id": graph["graph_id"],
                "template_key": f"{persona_id}-conflict-fact-template-syn-{ordinal:02d}",
                "template_ordinal": ordinal,
                "unordered_member_fact_ids": pair,
            }
        )
    if len(templates) != 4:
        _fail(f"{persona_id} must expose exactly four conflict templates")
    return graph_value, templates


@functools.lru_cache(maxsize=20)
def _expected_fact_graph_binding(persona_id):
    graph_value, _ = _expected_conflict_inputs(persona_id)
    raw = fact_graph.canonical_json_bytes(graph_value)
    actual = hashlib.sha256(raw).hexdigest()
    return {
        "artifact_kind": graph_value["artifact_kind"],
        "artifact_schema": graph_value["artifact_schema"],
        "artifact_schema_version": graph_value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "dependency_role": "persona-local-conflict-fact-templates",
        "fixture_id": graph_value["fixture_id"],
        "fixture_schema_version": graph_value["fixture_schema_version"],
        "name": "typed-fact-graph",
        "persona_id": persona_id,
        "sha256": actual,
    }


def _expected_target(persona_id, origin):
    return _upstream_inputs()["targets"][persona_id]["targets"][
        ORIGIN_TO_TARGET_PROFILE[origin]
    ]


def _balanced_joint_matrix(row_counts, column_counts):
    """Independently solve the exact proportional 3x4 rounding problem."""

    if (
        len(row_counts) != len(RELATION_ORDER)
        or len(column_counts) != len(PLACEMENT_ORDER)
        or sum(row_counts) != sum(column_counts)
        or sum(row_counts) <= 0
    ):
        _fail("relation/placement margins are infeasible")
    total = sum(row_counts)
    floors = [
        [row_total * column_total // total for column_total in column_counts]
        for row_total in row_counts
    ]
    row_need = [
        row_counts[row_index] - sum(floors[row_index])
        for row_index in range(len(row_counts))
    ]
    column_need = [
        column_counts[column_index]
        - sum(row[column_index] for row in floors)
        for column_index in range(len(column_counts))
    ]
    remainders = [
        [row_total * column_total % total for column_total in column_counts]
        for row_total in row_counts
    ]
    candidates = []
    row_choices = [
        list(itertools.combinations(range(len(column_counts)), need))
        for need in row_need
    ]
    for combination in itertools.product(*row_choices):
        additions = [
            [int(column_index in columns) for column_index in range(4)]
            for columns in combination
        ]
        if [
            sum(row[column_index] for row in additions)
            for column_index in range(4)
        ] != column_need:
            continue
        score = sum(
            remainders[row][column] * additions[row][column]
            for row in range(3)
            for column in range(4)
        )
        flattened = tuple(
            additions[row][column]
            for row in range(3)
            for column in range(4)
        )
        candidates.append((-score, tuple(-item for item in flattened), additions))
    if not candidates:
        _fail("no exact relation/placement contingency rounding exists")
    additions = min(candidates)[2]
    matrix = [
        [floors[row][column] + additions[row][column] for column in range(4)]
        for row in range(3)
    ]
    return {
        relation: {
            placement: matrix[row_index][column_index]
            for column_index, placement in enumerate(PLACEMENT_ORDER)
        }
        for row_index, relation in enumerate(RELATION_ORDER)
    }


def _expected_joint_matrix(persona_id, origin):
    target = _expected_target(persona_id, origin)
    row_counts = [
        target[f"{relation.replace('-', '_')}_cluster_count"]
        for relation in RELATION_ORDER
    ]
    column_counts = [
        target["placement_demand_by_scope_class"][placement]
        for placement in PLACEMENT_ORDER
    ]
    return _balanced_joint_matrix(row_counts, column_counts)


def _best_host_histogram(member_count, host_count):
    if not 0 <= host_count <= member_count <= 5 * host_count:
        _fail("attachment host dimensions are infeasible")
    best = None
    for h1 in range(host_count + 1):
        for h2 in range(host_count - h1 + 1):
            for h3 in range(host_count - h1 - h2 + 1):
                remaining_hosts = host_count - h1 - h2 - h3
                remaining_members = member_count - h1 - 2 * h2 - 3 * h3
                h5 = remaining_members - 4 * remaining_hosts
                h4 = remaining_hosts - h5
                if h4 < 0 or h5 < 0:
                    continue
                histogram = (h1, h2, h3, h4, h5)
                squared_error = sum(
                    (20 * observed - host_count * weight) ** 2
                    for observed, weight in zip(
                        histogram, ATTACHMENT_HOST_STRESS_WEIGHTS
                    )
                )
                maximum_error = max(
                    abs(20 * observed - host_count * weight)
                    for observed, weight in zip(
                        histogram, ATTACHMENT_HOST_STRESS_WEIGHTS
                    )
                )
                key = (
                    squared_error,
                    maximum_error,
                    tuple(-observed for observed in histogram),
                )
                if best is None or key < best[0]:
                    best = (key, histogram)
    if best is None:
        _fail("no exact attachment host histogram exists")
    return best[1]


@functools.lru_cache(maxsize=20)
def _pilot_host_count(persona_id):
    pilot_members = _expected_target(persona_id, "pilot")[
        "attachment_membership_count"
    ]
    pilot_eml = sum(
        variant_id == "eml"
        for variant_id in _source_domain(persona_id, "pilot").values()
    )
    residual_eml = sum(
        variant_id == "eml"
        for variant_id in _source_domain(persona_id, "full-residual").values()
    )
    lower = (pilot_members + 4) // 5
    upper = min(
        pilot_members,
        pilot_eml,
        residual_eml // 9,
        (pilot_eml + residual_eml) // 10,
    )
    host_count = min((pilot_members + 1) // 2, upper)
    if host_count < lower:
        _fail(f"attachment host capacity is infeasible for {persona_id}")
    return host_count


def _expected_host_histogram(persona_id, origin):
    pilot_members = _expected_target(persona_id, "pilot")[
        "attachment_membership_count"
    ]
    pilot_hosts = _pilot_host_count(persona_id)
    pilot_histogram = _best_host_histogram(pilot_members, pilot_hosts)
    multiplier = 1 if origin == "pilot" else 9
    source_domain = _source_domain(persona_id, origin)
    eml_count = sum(variant_id == "eml" for variant_id in source_domain.values())
    host_count = multiplier * pilot_hosts
    result = {
        str(cardinality): multiplier * count
        for cardinality, count in zip(
            MEMBERS_PER_HOST_ORDER, pilot_histogram
        )
    }
    result["0"] = eml_count - host_count
    if result["0"] < 0:
        _fail(f"negative unselected EML count for {persona_id}/{origin}")
    if sum(result[str(value)] for value in MEMBERS_PER_HOST_ORDER) != host_count:
        _fail("attachment host histogram lost host mass")
    if sum(
        value * result[str(value)] for value in MEMBERS_PER_HOST_ORDER
    ) != _expected_target(persona_id, origin)["attachment_membership_count"]:
        _fail("attachment host histogram lost member mass")
    return result


def _expected_base_bindings():
    return _upstream_inputs()["base_bindings"]


def _expected_origin_bindings(persona_id):
    return _expected_base_bindings() + [
        _expected_fact_graph_binding(persona_id)
    ]


def _validate_origin_envelope(value):
    _require_exact_fields(
        value, ORIGIN_TOP_LEVEL_FIELDS, label="overlay reservation origin"
    )
    if (
        value["artifact_kind"] != ORIGIN_ARTIFACT_KIND
        or value["artifact_schema"] != ORIGIN_ARTIFACT_SCHEMA
        or value["artifact_schema_version"] != ARTIFACT_SCHEMA_VERSION
        or value["fixture_id"] != envelope.FIXTURE_ID
        or value["fixture_schema_version"] != envelope.FIXTURE_SCHEMA_VERSION
    ):
        _fail("overlay reservation origin identity drifted")
    persona_id = value["persona_id"]
    origin = value["origin"]
    if type(persona_id) is not str or persona_id not in envelope.PERSONA_IDS:
        _fail(f"unknown reservation persona: {persona_id!r}")
    if type(origin) is not str or origin not in ORIGIN_ORDER:
        _fail(f"unknown reservation origin: {origin!r}")
    _require_all_false_authority(value["authority"], label="origin")
    _reject_forbidden_fields(value)
    if value["canonical_limits"] != {
        "max_body_bytes": MAX_ORIGIN_ARTIFACT_BYTES,
        "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
        "max_reservation_row_bytes_including_lf": MAX_RESERVATION_ROW_BYTES,
        "max_rows": MAX_ROWS_PER_ORIGIN,
        "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
        "null_float_or_negative_integer_allowed": False,
        "self_hash_embedded": False,
        "unicode_normalization": "NFC",
    }:
        _fail("origin canonical limits drifted")
    if value["completion_claims"] != {
        "attachment_host_marginals_reserved": True,
        "concrete_fact_membership_bound": False,
        "concrete_overlay_membership_present": False,
        "concrete_source_intent_manifest_bound": False,
        "conflict_endpoint_fact_assignment_reserved": True,
        "conflict_fact_template_reuse_reserved": True,
        "logical_identity_slots_reserved": True,
        "payload_relation_slots_reserved": True,
        "relation_placement_joint_marginals_reserved": True,
        "scope_assignment_present": False,
        "source_profile_assignment_complete": False,
        "source_slot_reservations_present": True,
    }:
        _fail("origin completion claims overstate or understate the reservation")
    if value["dependency_direction_contract"] != {
        "concrete_membership_must_bind_reservation_and_source_fact_manifests": True,
        "evaluation_query_or_oracle_identity_imported": False,
        "source_intent_manifest_must_bind_reservation": True,
        "reservation_may_bind_concrete_source_or_fact_manifest": False,
        "solved_scope_or_final_identity_allowed": False,
    }:
        _fail("origin dependency direction contract drifted")
    if value["reservation_contract"] != {
        "attachment_exact_overlap_member_side": "derivative",
        "attachment_member_cardinality_order": list(MEMBERS_PER_HOST_ORDER),
        "conflict_branch_a_maps_to_anchor_endpoint": True,
        "conflict_branch_b_maps_to_derivative_endpoint": True,
        "conflict_fact_pair_reuse_allowed": True,
        "content_relation_endpoint_variants_must_match": True,
        "content_relation_endpoint_variants_must_not_be_eml": True,
        "cross_cluster_intent_or_logical_identity_reuse_allowed": False,
        "eml_fanout_zero_bin_counts_unselected_eml_intents": True,
        "fact_template_reuse_is_not-independent-semantic-conflict-count": True,
        "full_conflict_order_continues_from_pilot_into_residual": True,
        "host_variant_id": "eml",
        "placement_class_is_requirement_not_scope_assignment": True,
        "semantic_anchor_slots_are_corpus_capacity_not_query_mapping": True,
    }:
        _fail("origin reservation contract drifted")
    if value["g0_contract_frozen"] is not False:
        _fail("reservation must not freeze G0")
    if value["input_bindings"] != _expected_origin_bindings(persona_id):
        _fail("origin dependency hashes or roles drifted")
    profile = ORIGIN_TO_TARGET_PROFILE[origin]
    if value["target_profile"] != profile:
        _fail("origin target profile mapping drifted")
    if value["target_marginals"] != _expected_target(persona_id, origin):
        _fail("origin target marginals differ from the overlay contract")
    raw = _canonical_bytes(
        value,
        label="persona v2 overlay reservation origin",
        max_bytes=MAX_ORIGIN_ARTIFACT_BYTES,
    )
    return persona_id, origin, raw


def _validate_semantic_anchor_slots(value, persona_id, origin, source_domain):
    slots = value["semantic_anchor_slots"]
    if type(slots) is not list:
        _fail("semantic anchor slots must be a list")
    expected_count = PILOT_SEMANTIC_ANCHOR_SLOT_COUNT if origin == "pilot" else 0
    if len(slots) != expected_count:
        _fail(
            f"{persona_id}/{origin} must reserve exactly {expected_count} semantic anchors"
        )
    roles = _upstream_inputs()["roles"]
    observed = set()
    for expected_ordinal, row in enumerate(slots, start=1):
        _require_exact_fields(
            row,
            {
                "gate_role",
                "intent_key",
                "semantic_anchor_slot_ordinal",
                "variant_id",
            },
            label="semantic anchor slot",
        )
        if row["semantic_anchor_slot_ordinal"] != expected_ordinal:
            _fail("semantic anchor slot ordinals must be contiguous from one")
        intent_key = row["intent_key"]
        variant_id = _resolve_intent(
            intent_key,
            persona_id=persona_id,
            origin=origin,
            source_domain=source_domain,
        )
        if intent_key in observed:
            _fail(f"duplicate semantic anchor source slot: {intent_key}")
        observed.add(intent_key)
        if (
            row["variant_id"] != variant_id
            or row["gate_role"] != roles[variant_id]
            or roles[variant_id] != "contract_contributor"
        ):
            _fail("semantic anchors must resolve to contract-contributor variants")
    return observed


def _validate_conflict_templates(value, persona_id):
    _, expected = _expected_conflict_inputs(persona_id)
    if value["conflict_fact_templates"] != expected:
        _fail("conflict fact template catalog differs from the typed fact graph")
    for template in expected:
        branch_a = set(template["branch_a_present_fact_ids"])
        branch_b = set(template["branch_b_present_fact_ids"])
        pair = set(template["unordered_member_fact_ids"])
        common = set(template["common_w0_current_fact_ids"])
        if (
            len(branch_a) != 7
            or len(branch_b) != 7
            or branch_a & branch_b != common
            or len(common) != 6
            or branch_a | branch_b != common | pair
            or branch_a ^ branch_b != pair
            or template["branch_a_selected_fact_id"] not in branch_a - branch_b
            or template["branch_b_selected_fact_id"] not in branch_b - branch_a
        ):
            _fail("conflict template branch fact-set algebra is invalid")
    return expected


def _expected_conflict_binding(template, global_ordinal):
    return {
        "branch_a_present_fact_ids": list(template["branch_a_present_fact_ids"]),
        "branch_a_selected_fact_id": template["branch_a_selected_fact_id"],
        "branch_b_present_fact_ids": list(template["branch_b_present_fact_ids"]),
        "branch_b_selected_fact_id": template["branch_b_selected_fact_id"],
        "conflict_set_id": template["conflict_set_id"],
        "fact_template_reuse_ordinal": (global_ordinal - 1) // 4 + 1,
        "graph_id": template["graph_id"],
        "template_key": template["template_key"],
        "unordered_member_fact_ids": list(template["unordered_member_fact_ids"]),
    }


def _validate_relation_rows(
    rows, value, persona_id, origin, source_domain, templates
):
    target = _expected_target(persona_id, origin)
    roles = _upstream_inputs()["roles"]
    expected_joint = _expected_joint_matrix(persona_id, origin)
    if value["relation_placement_joint_marginals"] != expected_joint:
        _fail("relation/placement joint marginal differs from exact rounding")
    expected_total = target["content_relation_cluster_count"]
    if len(rows) != expected_total:
        _fail("content relation row count differs from the exact target")

    endpoints = set()
    anchors = set()
    derivatives = set()
    relation_by_cluster = {}
    logical_document_owners = {}
    actual_joint = {
        relation: {placement: 0 for placement in PLACEMENT_ORDER}
        for relation in RELATION_ORDER
    }
    row_index = 0
    conflict_ordinal = 0
    for relation in RELATION_ORDER:
        relation_count = target[
            f"{relation.replace('-', '_')}_cluster_count"
        ]
        for relation_ordinal in range(1, relation_count + 1):
            row = rows[row_index]
            row_index += 1
            expected_fields = set(RELATION_ROW_FIELDS)
            if relation == "conflict-copy":
                expected_fields.add("conflict_fact_binding")
            _require_exact_fields(
                row, expected_fields, label=f"{relation} reservation row"
            )
            if (
                row["row_kind"] != "content-relation-reservation"
                or row["relation_kind"] != relation
            ):
                _fail("content relation rows must follow canonical relation order")
            width = _ordinal_width(origin)
            cluster_key = (
                f"{persona_id}-overlay-{origin}-{relation}-syn-"
                f"{relation_ordinal:0{width}d}"
            )
            if (
                row["cluster_key"] != cluster_key
                or row["cluster_context_seed"] != f"{cluster_key}-context-v2"
            ):
                _fail("content relation cluster key or context seed drifted")
            if cluster_key in relation_by_cluster:
                _fail(f"duplicate content relation cluster key: {cluster_key}")
            placement = row["placement_class_requirement"]
            if placement not in PLACEMENT_ORDER:
                _fail(f"unknown placement-class requirement: {placement!r}")
            actual_joint[relation][placement] += 1

            anchor_key = row["anchor_intent_key"]
            derivative_key = row["derivative_intent_key"]
            anchor_variant = _resolve_intent(
                anchor_key,
                persona_id=persona_id,
                origin=origin,
                source_domain=source_domain,
            )
            derivative_variant = _resolve_intent(
                derivative_key,
                persona_id=persona_id,
                origin=origin,
                source_domain=source_domain,
            )
            if anchor_key == derivative_key:
                _fail("content relation endpoints must be distinct source intents")
            if anchor_key in endpoints or derivative_key in endpoints:
                _fail("content relation endpoints must be disjoint across clusters")
            endpoints.update((anchor_key, derivative_key))
            anchors.add(anchor_key)
            derivatives.add(derivative_key)
            if (
                anchor_variant != derivative_variant
                or anchor_variant == "eml"
                or roles[anchor_variant]
                not in {"contract_contributor", "incidental_searchable"}
                or row["endpoint_variant_id"] != anchor_variant
                or row["endpoint_gate_role"] != roles[anchor_variant]
            ):
                _fail(
                    "content endpoints must resolve to one matching non-EML searchable variant"
                )

            expected_anchor, expected_derivative, expected_recipe = (
                _expected_content_identities(
                    persona_id, origin, relation, anchor_key
                )
            )
            _require_identity(
                row["anchor_identity"],
                expected_anchor,
                label=f"{cluster_key} anchor identity",
            )
            _require_identity(
                row["derivative_identity"],
                expected_derivative,
                label=f"{cluster_key} derivative identity",
            )
            if row["content_recipe_profile_id"] != expected_recipe:
                _fail(f"{cluster_key} content recipe profile drifted")
            document_key = expected_anchor["logical_document_key"]
            if document_key in logical_document_owners:
                _fail("logical document identity is reused across relation clusters")
            logical_document_owners[document_key] = cluster_key

            if relation == "conflict-copy":
                conflict_ordinal += 1
                pilot_offset = (
                    0
                    if origin == "pilot"
                    else _expected_target(persona_id, "pilot")[
                        "conflict_copy_cluster_count"
                    ]
                )
                global_ordinal = pilot_offset + conflict_ordinal
                template = templates[(global_ordinal - 1) % 4]
                binding = row["conflict_fact_binding"]
                _require_exact_fields(
                    binding,
                    CONFLICT_BINDING_FIELDS,
                    label=f"{cluster_key} conflict binding",
                )
                if binding != _expected_conflict_binding(template, global_ordinal):
                    _fail(
                        "conflict fact templates must rotate modulo four with the pilot offset"
                    )
                branch_a = set(binding["branch_a_present_fact_ids"])
                branch_b = set(binding["branch_b_present_fact_ids"])
                pair = set(binding["unordered_member_fact_ids"])
                if (
                    len(branch_a & branch_b) != 6
                    or len(branch_a | branch_b) != 8
                    or branch_a ^ branch_b != pair
                    or binding["branch_a_selected_fact_id"] not in branch_a - branch_b
                    or binding["branch_b_selected_fact_id"] not in branch_b - branch_a
                ):
                    _fail("conflict reservation branch fact-set algebra is invalid")
            relation_by_cluster[cluster_key] = row
    if row_index != len(rows) or actual_joint != expected_joint:
        _fail("content relation rows do not realize the exact joint marginal")
    if len(endpoints) != target["content_relation_endpoint_reference_count"]:
        _fail("content relation endpoint reference count drifted")
    return {
        "anchors": anchors,
        "derivatives": derivatives,
        "endpoints": endpoints,
        "logical_document_owners": logical_document_owners,
        "relation_by_cluster": relation_by_cluster,
    }


def _validate_attachment_rows(
    rows, persona_id, origin, source_domain, relation_state
):
    target = _expected_target(persona_id, origin)
    roles = _upstream_inputs()["roles"]
    endpoints = relation_state["endpoints"]
    relation_by_cluster = relation_state["relation_by_cluster"]
    logical_document_owners = relation_state["logical_document_owners"]
    if len(rows) != target["attachment_membership_count"]:
        _fail("attachment membership row count differs from the exact target")

    hosts = set()
    members = set()
    overlap_members = set()
    overlap_clusters = set()
    overlap_hosts = set()
    groups = []
    current_group = None
    width = _ordinal_width(origin)
    for attachment_ordinal, row in enumerate(rows, start=1):
        _require_exact_fields(
            row, ATTACHMENT_ROW_FIELDS, label="attachment membership row"
        )
        if row["row_kind"] != "attachment-membership-reservation":
            _fail("attachment row kind drifted")
        attachment_key = (
            f"{persona_id}-attachment-{origin}-syn-"
            f"{attachment_ordinal:0{width}d}"
        )
        if (
            row["attachment_key"] != attachment_key
            or row["attachment_context_seed"] != f"{attachment_key}-context-v2"
        ):
            _fail("attachment key or context seed drifted")
        if (
            type(row["host_ordinal"]) is not int
            or type(row["member_ordinal"]) is not int
            or type(row["host_member_count"]) is not int
            or not 1 <= row["host_member_count"] <= 5
        ):
            _fail("attachment host/member ordinals or cardinality are invalid")

        if current_group is None or row["host_ordinal"] != current_group["ordinal"]:
            expected_host_ordinal = len(groups) + 1
            if (
                row["host_ordinal"] != expected_host_ordinal
                or row["member_ordinal"] != 1
            ):
                _fail("attachment host ordinals must be contiguous from one")
            current_group = {
                "count": 0,
                "declared_count": row["host_member_count"],
                "host_identity": row["host_identity"],
                "host_intent_key": row["host_intent_key"],
                "ordinal": row["host_ordinal"],
            }
            groups.append(current_group)
            if row["host_intent_key"] in hosts:
                _fail("an attachment host cannot reappear in another host group")
            hosts.add(row["host_intent_key"])
        else:
            if (
                row["member_ordinal"] != current_group["count"] + 1
                or row["host_member_count"] != current_group["declared_count"]
                or row["host_intent_key"] != current_group["host_intent_key"]
                or row["host_identity"] != current_group["host_identity"]
            ):
                _fail("attachment members are not contiguous within their host")
        current_group["count"] += 1
        if current_group["count"] > current_group["declared_count"]:
            _fail("attachment host contains more members than declared")

        host_key = row["host_intent_key"]
        host_variant = _resolve_intent(
            host_key,
            persona_id=persona_id,
            origin=origin,
            source_domain=source_domain,
        )
        expected_host_identity = _expected_singleton_identity(
            persona_id, origin, host_key, "host-container"
        )
        _require_identity(
            row["host_identity"],
            expected_host_identity,
            label=f"{attachment_key} host identity",
        )
        if (
            host_variant != "eml"
            or row["host_variant_id"] != "eml"
            or row["host_gate_role"] != roles["eml"]
        ):
            _fail("every attachment host must resolve to the EML variant")

        member_key = row["standalone_member_intent_key"]
        member_variant = _resolve_intent(
            member_key,
            persona_id=persona_id,
            origin=origin,
            source_domain=source_domain,
        )
        if member_key in members:
            _fail("attachment standalone member intents must be unique")
        members.add(member_key)
        if (
            member_variant == "eml"
            or roles[member_variant]
            not in {"contract_contributor", "incidental_searchable"}
            or row["standalone_member_variant_id"] != member_variant
            or row["standalone_member_gate_role"] != roles[member_variant]
        ):
            _fail("attachment members must resolve to non-EML searchable variants")
        if host_key == member_key:
            _fail("an EML host cannot also be its standalone member")

        relation_key = row["content_relation_membership"]
        if relation_key == "none":
            if member_key in endpoints:
                _fail("an endpoint/member overlap must identify its exact cluster")
            expected_member_identity = _expected_singleton_identity(
                persona_id, origin, member_key, "attachment-member"
            )
            member_owner = f"attachment-member:{member_key}"
        else:
            relation_row = relation_by_cluster.get(relation_key)
            if relation_row is None or relation_row["relation_kind"] != "exact-duplicate":
                _fail("attachment overlap may reference only an exact-duplicate cluster")
            if (
                member_key != relation_row["derivative_intent_key"]
                or member_key == relation_row["anchor_intent_key"]
                or row["member_ordinal"] != 1
            ):
                _fail("exact attachment overlap must use only the derivative at ordinal one")
            if relation_key in overlap_clusters:
                _fail("an exact cluster may overlap only one attachment membership")
            if host_key in overlap_hosts:
                _fail("an attachment host may carry at most one exact overlap")
            overlap_clusters.add(relation_key)
            overlap_hosts.add(host_key)
            overlap_members.add(member_key)
            expected_member_identity = relation_row["derivative_identity"]
            member_owner = relation_key
        _require_identity(
            row["standalone_member_identity"],
            expected_member_identity,
            label=f"{attachment_key} standalone member identity",
        )
        if (
            row["decoded_payload_equivalence_key"]
            != expected_member_identity["payload_equivalence_key"]
            or row["embedded_member_identity_source"]
            != "standalone-member-identity-exact"
        ):
            _fail("embedded attachment identity must exactly copy the standalone member")

        host_document = expected_host_identity["logical_document_key"]
        previous_host_owner = logical_document_owners.setdefault(
            host_document, f"attachment-host:{host_key}"
        )
        if previous_host_owner != f"attachment-host:{host_key}":
            _fail("attachment host logical document identity is reused")
        member_document = expected_member_identity["logical_document_key"]
        previous_member_owner = logical_document_owners.setdefault(
            member_document, member_owner
        )
        if previous_member_owner != member_owner:
            _fail("attachment member logical document identity is reused illegally")

    if any(group["count"] != group["declared_count"] for group in groups):
        _fail("attachment host member counts do not match their contiguous rows")
    if hosts & members or hosts & endpoints:
        _fail("attachment hosts must be disjoint from endpoints and members")
    actual_overlap = endpoints & members
    if actual_overlap != overlap_members:
        _fail("attachment endpoint/member overlap is not exactly declared")
    if not overlap_members.issubset(relation_state["derivatives"]):
        _fail("attachment overlap must be one-sided on exact derivatives")
    if overlap_members & relation_state["anchors"]:
        _fail("attachment overlap may not use relation anchors")
    if len(overlap_members) != target["attachment_exact_duplicate_overlap_count"]:
        _fail("attachment exact-overlap count differs from the exact target")

    eml_count = sum(variant_id == "eml" for variant_id in source_domain.values())
    actual_histogram = {str(value): 0 for value in (0,) + MEMBERS_PER_HOST_ORDER}
    for group in groups:
        actual_histogram[str(group["count"])] += 1
    actual_histogram["0"] = eml_count - len(hosts)
    expected_histogram = _expected_host_histogram(persona_id, origin)
    if actual_histogram != expected_histogram:
        _fail("attachment host fan-out histogram differs from the exact stress target")
    return {
        "actual_host_histogram": actual_histogram,
        "hosts": hosts,
        "members": members,
        "overlap_members": overlap_members,
    }


def _expected_variant_usage(
    source_domain, roles, semantic_anchors, relation_state, attachment_state
):
    endpoints = relation_state["endpoints"]
    hosts = attachment_state["hosts"]
    members = attachment_state["members"]
    overlap = attachment_state["overlap_members"]
    all_reserved = semantic_anchors | endpoints | hosts | members
    source_by_variant = {}
    for intent_key, variant_id in source_domain.items():
        source_by_variant.setdefault(variant_id, set()).add(intent_key)
    result = []
    for variant_id in sorted(source_by_variant, key=lambda item: item.encode("ascii")):
        keys = source_by_variant[variant_id]
        result.append(
            {
                "attachment_exact_overlap_intent_count": len(keys & overlap),
                "attachment_host_intent_count": len(keys & hosts),
                "attachment_member_reference_count": len(keys & members),
                "content_relation_endpoint_count": len(keys & endpoints),
                "gate_role": roles[variant_id],
                "semantic_anchor_slot_count": len(keys & semantic_anchors),
                "source_intent_count": len(keys),
                "unique_reserved_source_intent_count": len(keys & all_reserved),
                "unreserved_source_intent_count": len(keys - all_reserved),
                "variant_id": variant_id,
            }
        )
    return result


def _validate_summary_and_variant_usage(
    value,
    raw_rows,
    semantic_anchors,
    relation_state,
    attachment_state,
    source_domain,
):
    maximum_row_bytes = max(len(raw) + 1 for raw in raw_rows)
    endpoints = relation_state["endpoints"]
    hosts = attachment_state["hosts"]
    members = attachment_state["members"]
    overlap = attachment_state["overlap_members"]
    overlay_referenced = endpoints | hosts | members
    all_reserved = overlay_referenced | semantic_anchors
    expected_summary = {
        "attachment_exact_overlap_intent_count": len(overlap),
        "eml_attachment_fanout_histogram": attachment_state["actual_host_histogram"],
        "attachment_host_intent_count": len(hosts),
        "attachment_membership_row_count": len(members),
        "content_relation_row_count": len(value["reservation_rows"]) - len(members),
        "maximum_row_bytes_including_lf": maximum_row_bytes,
        "overlay_referenced_unique_source_intent_count": len(overlay_referenced),
        "reservation_row_count": len(value["reservation_rows"]),
        "semantic_anchor_slot_count": len(semantic_anchors),
        "source_origin_intent_count": len(source_domain),
        "unreserved_source_intent_count": len(source_domain) - len(all_reserved),
    }
    if value["summary"] != expected_summary:
        _fail("origin summary does not recompute from reservation rows")
    expected_variant_usage = _expected_variant_usage(
        source_domain,
        _upstream_inputs()["roles"],
        semantic_anchors,
        relation_state,
        attachment_state,
    )
    if value["variant_usage_marginals"] != expected_variant_usage:
        _fail("variant usage marginals do not recompute from source references")


def validate_overlay_reservation_origin(value):
    """Validate one origin artifact without importing or rerunning its builder."""

    persona_id, origin, canonical_body = _validate_origin_envelope(value)
    validation_digest = hashlib.sha256(canonical_body).hexdigest()
    if validation_digest in _VALIDATED_ORIGIN_DIGESTS:
        return True
    if value["completion_scope"] != (
        "exact-pre-source-overlay-reservation-only-no-source-row-body-no-concrete-"
        "membership-no-scope-solution-no-rendered-bytes-no-execution-no-g0"
    ):
        _fail("origin completion scope drifted")
    if value["hypothesis_status"] != (
        "authored-benchmark-stress-reservation-not-observed-user-statistics"
    ):
        _fail("origin hypothesis status drifted")
    if value["remaining_blockers"] != [
        "203000-source-intent-row-bodies-and-manifests-not-present",
        "complete-source-profile-and-content-recipe-assignment-not-present",
        "full-source-owned-fact-membership-manifests-and-sidecars-not-present",
        "concrete-overlay-membership-shards-and-manifests-not-present",
        "format-rendition-relation-not-reserved",
        "query-and-history-target-namespace-mapping-not-present",
        "scope-placement-and-joint-solver-solution-not-present",
        "renderer-validator-and-byte-chunk-attestation-not-present",
        "bounded-framed-external-loader-not-implemented",
        "independent-reservation-review-receipt-not-bound",
    ]:
        _fail("origin blocker ledger drifted")

    rows = value["reservation_rows"]
    target = _expected_target(persona_id, origin)
    if type(rows) is not list:
        _fail("reservation rows must be a list")
    if len(rows) != target["membership_row_count"]:
        _fail("reservation row count differs from the exact membership target")
    if len(rows) > MAX_ROWS_PER_ORIGIN:
        _fail("reservation origin exceeds the row cap")
    raw_rows = []
    for row in rows:
        raw = _canonical_bytes(
            row,
            label="persona v2 overlay reservation row",
            max_bytes=MAX_RESERVATION_ROW_BYTES - 1,
        )
        if len(raw) + 1 > MAX_RESERVATION_ROW_BYTES:
            _fail("reservation row exceeds the JSONL byte cap")
        raw_rows.append(raw)

    source_domain = _source_domain(persona_id, origin)
    semantic_anchors = _validate_semantic_anchor_slots(
        value, persona_id, origin, source_domain
    )
    templates = _validate_conflict_templates(value, persona_id)
    relation_count = target["content_relation_cluster_count"]
    relation_rows = rows[:relation_count]
    attachment_rows = rows[relation_count:]
    relation_state = _validate_relation_rows(
        relation_rows,
        value,
        persona_id,
        origin,
        source_domain,
        templates,
    )
    attachment_state = _validate_attachment_rows(
        attachment_rows,
        persona_id,
        origin,
        source_domain,
        relation_state,
    )
    overlay_references = (
        relation_state["endpoints"]
        | attachment_state["hosts"]
        | attachment_state["members"]
    )
    if semantic_anchors & overlay_references:
        _fail("semantic anchor capacity slots must not be used by overlays")
    _validate_summary_and_variant_usage(
        value,
        raw_rows,
        semantic_anchors,
        relation_state,
        attachment_state,
        source_domain,
    )
    _VALIDATED_ORIGIN_DIGESTS.add(validation_digest)
    return True


def _empty_nested_counts():
    return {
        origin: {
            "attachment_exact_overlap_intent_count": 0,
            "attachment_host_intent_count": 0,
            "attachment_membership_row_count": 0,
            "content_relation_row_count": 0,
            "overlay_referenced_unique_source_intent_count": 0,
            "reservation_row_count": 0,
            "semantic_anchor_slot_count": 0,
            "source_origin_intent_count": 0,
            "unreserved_source_intent_count": 0,
        }
        for origin in ORIGIN_ORDER
    }


def _sum_flat(left, right):
    return {key: left[key] + right[key] for key in left}


def _sum_joint(left, right):
    return {
        relation: {
            placement: left[relation][placement] + right[relation][placement]
            for placement in PLACEMENT_ORDER
        }
        for relation in RELATION_ORDER
    }


def _validate_suite_envelope(value):
    _require_exact_fields(
        value, SUITE_TOP_LEVEL_FIELDS, label="overlay reservation suite"
    )
    if (
        value["artifact_kind"] != SUITE_ARTIFACT_KIND
        or value["artifact_schema"] != SUITE_ARTIFACT_SCHEMA
        or value["artifact_schema_version"] != ARTIFACT_SCHEMA_VERSION
        or value["fixture_id"] != envelope.FIXTURE_ID
        or value["fixture_schema_version"] != envelope.FIXTURE_SCHEMA_VERSION
    ):
        _fail("overlay reservation suite identity drifted")
    _require_all_false_authority(value["authority"], label="suite")
    _reject_forbidden_fields(value)
    if value["canonical_limits"] != {
        "max_body_bytes": MAX_SUITE_ARTIFACT_BYTES,
        "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
        "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
        "self_hash_embedded": False,
        "unicode_normalization": "NFC",
    }:
        _fail("suite canonical limits drifted")
    if value["full_composition_contract"] != {
        "full_equals_pilot_plus_full_residual_coordinatewise": True,
        "pilot_origin_artifact_bytes_reused_unchanged": True,
    }:
        _fail("suite full-composition contract drifted")
    if value["orders"] != {
        "origin": list(ORIGIN_ORDER),
        "persona": list(envelope.PERSONA_IDS),
        "relation": list(RELATION_ORDER),
        "placement": list(PLACEMENT_ORDER),
    }:
        _fail("suite canonical orders drifted")
    if value["input_bindings"] != _expected_base_bindings():
        _fail("suite dependency hashes or roles drifted")
    if value["g0_contract_frozen"] is not False:
        _fail("reservation suite must not freeze G0")
    if value["completion_scope"] != (
        "compact-binding-of-forty-pre-source-reservations-only-no-source-or-"
        "membership-manifest-no-solver-no-rendered-bytes-no-execution-no-g0"
    ):
        _fail("suite completion scope drifted")
    if value["remaining_blockers"] != [
        "source-intent-row-bodies-and-manifests-not-present",
        "fact-membership-and-concrete-overlay-membership-not-present",
        "format-rendition-and-evaluation-target-mapping-not-present",
        "scope-solution-rendering-history-and-observation-not-present",
        "independent-reservation-review-receipt-not-bound",
    ]:
        _fail("suite blocker ledger drifted")
    _canonical_bytes(
        value,
        label="persona v2 overlay reservation suite",
        max_bytes=MAX_SUITE_ARTIFACT_BYTES,
    )


def validate_overlay_reservation_suite(value, origin_artifacts):
    """Validate the compact suite binding against forty validated origins."""

    _validate_suite_envelope(value)
    if type(origin_artifacts) is not list:
        _fail("origin_artifacts must be a list in canonical suite order")
    expected_order = [
        (persona_id, origin)
        for persona_id in envelope.PERSONA_IDS
        for origin in ORIGIN_ORDER
    ]
    if len(origin_artifacts) != len(expected_order):
        _fail("suite must bind exactly forty persona/origin artifacts")

    descriptors = []
    origin_totals = _empty_nested_counts()
    relation_joint = {
        origin: {
            relation: {placement: 0 for placement in PLACEMENT_ORDER}
            for relation in RELATION_ORDER
        }
        for origin in ORIGIN_ORDER
    }
    host_histograms = {
        origin: {str(value): 0 for value in (0,) + MEMBERS_PER_HOST_ORDER}
        for origin in ORIGIN_ORDER
    }
    total_origin_bytes = 0
    maximum_origin_bytes = 0
    maximum_row_bytes = 0
    for artifact, (expected_persona, expected_origin) in zip(
        origin_artifacts, expected_order
    ):
        if type(artifact) is not dict:
            _fail("suite origin artifact must be an object")
        if (
            artifact.get("persona_id") != expected_persona
            or artifact.get("origin") != expected_origin
        ):
            _fail("suite origin artifacts are not in canonical persona/origin order")
        validate_overlay_reservation_origin(artifact)
        raw = _canonical_bytes(
            artifact,
            label="persona v2 overlay reservation origin",
            max_bytes=MAX_ORIGIN_ARTIFACT_BYTES,
        )
        summary = artifact["summary"]
        descriptors.append(
            {
                "artifact_kind": artifact["artifact_kind"],
                "artifact_schema": artifact["artifact_schema"],
                "artifact_schema_version": artifact["artifact_schema_version"],
                "canonical_bytes": len(raw),
                "maximum_row_bytes_including_lf": summary[
                    "maximum_row_bytes_including_lf"
                ],
                "origin": expected_origin,
                "persona_id": expected_persona,
                "reservation_row_count": summary["reservation_row_count"],
                "sha256": hashlib.sha256(raw).hexdigest(),
                "target_profile": artifact["target_profile"],
            }
        )
        total_origin_bytes += len(raw)
        maximum_origin_bytes = max(maximum_origin_bytes, len(raw))
        maximum_row_bytes = max(
            maximum_row_bytes, summary["maximum_row_bytes_including_lf"]
        )
        for key in origin_totals[expected_origin]:
            origin_totals[expected_origin][key] += summary[key]
        relation_joint[expected_origin] = _sum_joint(
            relation_joint[expected_origin],
            artifact["relation_placement_joint_marginals"],
        )
        for cardinality in (0,) + MEMBERS_PER_HOST_ORDER:
            host_histograms[expected_origin][str(cardinality)] += summary[
                "eml_attachment_fanout_histogram"
            ][str(cardinality)]

    if value["origin_bindings"] != descriptors:
        _fail("suite origin bindings differ from canonical bytes and hashes")
    full_totals = _sum_flat(
        origin_totals["pilot"], origin_totals["full-residual"]
    )
    full_joint = _sum_joint(
        relation_joint["pilot"], relation_joint["full-residual"]
    )
    full_host_histogram = _sum_flat(
        host_histograms["pilot"], host_histograms["full-residual"]
    )
    expected_summary = {
        "eml_attachment_fanout_histograms": {
            "full": full_host_histogram,
            "full-minus-pilot": host_histograms["full-residual"],
            "pilot": host_histograms["pilot"],
        },
        "maximum_origin_canonical_bytes": maximum_origin_bytes,
        "maximum_row_bytes_including_lf": maximum_row_bytes,
        "origin_artifact_count": len(descriptors),
        "origin_canonical_bytes_total": total_origin_bytes,
        "origin_totals": {
            "full": full_totals,
            "full-minus-pilot": origin_totals["full-residual"],
            "pilot": origin_totals["pilot"],
        },
        "relation_placement_joint_marginals": {
            "full": full_joint,
            "full-minus-pilot": relation_joint["full-residual"],
            "pilot": relation_joint["pilot"],
        },
    }
    if value["suite_summary"] != expected_summary:
        _fail("suite summary does not recompute from the forty origins")
    return True
