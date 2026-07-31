"""Exact, non-authorizing pre-source overlay reservations for persona-PC v2.

The concrete overlay-membership manifest is downstream of materialized source
intent and fact-membership manifests.  Creating that manifest from the current
count-only source layout would falsely claim referential and branch-fact
validity.  This module closes the earlier reservation boundary instead:

* exact persona/origin relation and attachment slots;
* existing source-intent keys reserved for every endpoint, host, and member;
* exact attachment-host fan-out histograms;
* exact relation-kind by placement-class contingency tables;
* corpus-owned logical-document/revision/branch/section key reservations; and
* persona-local reuse of the four authored conflict-fact templates.

It contains no source row body, source-intent manifest, concrete membership
manifest, solved scope, final source/materialization identity, rendered byte,
KIO observation, or execution authority.  Source rows may bind this upstream
reservation.  A later concrete membership must bind both this reservation and
the independently materialized source/fact manifests.
"""

from __future__ import annotations

import copy
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


ARTIFACT_SCHEMA = "kio.persona.pc-overlay-reservation-origin/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-overlay-reservation-origin"
SUITE_ARTIFACT_SCHEMA = "kio.persona.pc-overlay-reservation-suite/v2"
SUITE_ARTIFACT_KIND = "persona-pc-v2-overlay-reservation-suite"

MAX_ORIGIN_ARTIFACT_BYTES = 4 * 2**20
MAX_SUITE_ARTIFACT_BYTES = 256 * 1024
MAX_RESERVATION_ROW_BYTES = 2_048
MAX_ROWS_PER_ORIGIN = 4_096

ORIGIN_TO_TARGET_PROFILE = {
    "pilot": "pilot",
    "full-residual": "full-minus-pilot",
}
ORIGIN_ORDER = tuple(ORIGIN_TO_TARGET_PROFILE)
RELATION_ORDER = tuple(overlay_contract.CONTENT_RELATION_ORDER)
PLACEMENT_ORDER = tuple(overlay_contract.PLACEMENT_CLASS_ORDER)
MEMBERS_PER_HOST_ORDER = (1, 2, 3, 4, 5)
ATTACHMENT_HOST_STRESS_WEIGHTS = (10, 4, 3, 2, 1)

# These are corpus-side capacity slots only.  They do not import or contain
# evaluation query IDs.  A later evaluation mapping must prove totality against
# actual query requirements without changing this corpus identity namespace.
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

_INTENT_KEY_RE = re.compile(
    r"^(p(?:0[1-9]|1[0-9]|20))-intent-"
    r"(pilot|full-residual)-syn-([0-9]{4,5})$"
)
_LOWER_ASCII_KEY_RE = re.compile(r"^[a-z][a-z0-9-]{0,119}$")


class PersonaV2OverlayReservationError(ValueError):
    """Raised when an overlay reservation violates the exact contract."""


def _require_persona_id(persona_id):
    if type(persona_id) is not str or persona_id not in envelope.PERSONA_IDS:
        raise PersonaV2OverlayReservationError(
            f"unknown persona ID: {persona_id!r}"
        )


def _require_origin(origin):
    if type(origin) is not str or origin not in ORIGIN_TO_TARGET_PROFILE:
        raise PersonaV2OverlayReservationError(
            f"unknown overlay reservation origin: {origin!r}"
        )


def _require_negative_authority(value, *, label):
    authority = value.get("authority") if type(value) is dict else None
    if set(authority or {}) != AUTHORITY_FIELDS or any(
        type(flag) is not bool or flag is not False
        for flag in (authority or {}).values()
    ):
        raise PersonaV2OverlayReservationError(
            f"{label} authority must contain the exact all-false schema"
        )


def _artifact_binding(
    name,
    dependency_role,
    value,
    *,
    validate,
    canonical,
):
    validate(value)
    raw = canonical(value)
    actual_digest = hashlib.sha256(raw).hexdigest()
    return {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "dependency_role": dependency_role,
        "fixture_id": value["fixture_id"],
        "fixture_schema_version": value["fixture_schema_version"],
        "name": name,
        "sha256": actual_digest,
    }


def _fact_graph_binding(persona_id, value):
    raw = fact_graph.canonical_json_bytes(value)
    return {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "dependency_role": "persona-local-conflict-fact-templates",
        "fixture_id": value["fixture_id"],
        "fixture_schema_version": value["fixture_schema_version"],
        "name": "typed-fact-graph",
        "persona_id": persona_id,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


@functools.lru_cache(maxsize=1)
def _shared_inputs():
    overlay_value = overlay_contract.build_overlay_contract()
    layout_value = source_layout.build_source_inventory_layout()
    variant_value = variant_catalog.build_variant_catalog()
    graph_values = {
        value["persona_id"]: value for value in fact_graph.build_fact_graph_suite()
    }
    if tuple(graph_values) != envelope.PERSONA_IDS:
        raise PersonaV2OverlayReservationError(
            "fact graph suite persona order drifted"
        )
    bindings = [
        _artifact_binding(
            "overlay-contract",
            "overlay-semantics-and-target-marginals",
            overlay_value,
            validate=overlay_contract.validate_overlay_contract,
            canonical=overlay_contract.canonical_json_bytes,
        ),
        _artifact_binding(
            "source-inventory-layout",
            "reserved-source-intent-keyspace-and-variant-ranges",
            layout_value,
            validate=source_layout.validate_source_inventory_layout,
            canonical=source_layout.canonical_json_bytes,
        ),
        _artifact_binding(
            "variant-catalog",
            "gate-role-and-variant-identity",
            variant_value,
            validate=variant_catalog.validate_variant_catalog,
            canonical=variant_catalog.canonical_json_bytes,
        ),
    ]
    graph_bindings = {
        persona_id: _fact_graph_binding(persona_id, graph_values[persona_id])
        for persona_id in envelope.PERSONA_IDS
    }
    return {
        "base_bindings": bindings,
        "fact_graph_bindings": graph_bindings,
        "fact_graphs": graph_values,
        "layout": layout_value,
        "overlay": overlay_value,
        "variants": variant_value,
    }


@functools.lru_cache(maxsize=20)
def _persona_layout(persona_id):
    return next(
        row
        for row in _shared_inputs()["layout"]["personas"]
        if row["persona_id"] == persona_id
    )


@functools.lru_cache(maxsize=20)
def _persona_targets(persona_id):
    return next(
        row
        for row in _shared_inputs()["overlay"]["persona_target_marginals"]
        if row["persona_id"] == persona_id
    )


@functools.lru_cache(maxsize=1)
def _variant_roles():
    return {
        row["variant_id"]: row["gate_role"]
        for row in _shared_inputs()["variants"]["variant_rows"]
    }


@functools.lru_cache(maxsize=40)
def _intent_slot_tuples_by_variant(persona_id, origin):
    reservations = _persona_layout(persona_id)["variant_reservations"][origin]
    result = {}
    observed = set()
    for reservation in reservations:
        variant_id = reservation["variant_id"]
        if variant_id in result:
            raise PersonaV2OverlayReservationError(
                f"duplicate variant reservation: {persona_id}/{origin}/{variant_id}"
            )
        slots = []
        for ordinal in range(
            reservation["first_origin_ordinal"],
            reservation["last_origin_ordinal"] + 1,
        ):
            key = source_layout.intent_key(persona_id, origin, ordinal)
            if key in observed:
                raise PersonaV2OverlayReservationError(
                    f"duplicate source-intent reservation: {key}"
                )
            observed.add(key)
            slots.append(key)
        if len(slots) != reservation["row_count"]:
            raise PersonaV2OverlayReservationError(
                "variant reservation row count drifted"
            )
        result[variant_id] = tuple(slots)
    expected = (
        _persona_layout(persona_id)["pilot_source_count"]
        if origin == "pilot"
        else _persona_layout(persona_id)["full_residual_source_count"]
    )
    if len(observed) != expected:
        raise PersonaV2OverlayReservationError(
            f"source-intent key coverage drifted: {persona_id}/{origin}"
        )
    return tuple(result.items())


def _intent_slots_by_variant(persona_id, origin):
    return {
        variant_id: list(intent_keys)
        for variant_id, intent_keys in _intent_slot_tuples_by_variant(
            persona_id, origin
        )
    }


def _take_round_robin(pools, count, eligible_variant_ids, *, label):
    if type(count) is not int or count < 0:
        raise PersonaV2OverlayReservationError(f"{label} count is invalid")
    variants = sorted(set(eligible_variant_ids), key=lambda value: value.encode("ascii"))
    result = []
    while len(result) < count:
        before = len(result)
        for variant_id in variants:
            values = pools.get(variant_id)
            if values:
                result.append(values.pop(0))
            if len(result) == count:
                break
        if len(result) == before:
            raise PersonaV2OverlayReservationError(
                f"insufficient source slots for {label}"
            )
    return result


def _midpoint_sample(sorted_values, count, *, label):
    if type(count) is not int or count < 0 or count > len(sorted_values):
        raise PersonaV2OverlayReservationError(
            f"invalid midpoint sample count for {label}"
        )
    if count == 0:
        return []
    indices = [
        ((2 * index + 1) * len(sorted_values)) // (2 * count)
        for index in range(count)
    ]
    if len(indices) != len(set(indices)):
        raise PersonaV2OverlayReservationError(
            f"midpoint sample duplicated a value for {label}"
        )
    return [sorted_values[index] for index in indices]


@functools.lru_cache(maxsize=20)
def _attachment_host_count(persona_id):
    targets = _persona_targets(persona_id)["targets"]
    pilot_members = targets["pilot"]["attachment_membership_count"]
    pilot_slots = _intent_slots_by_variant(persona_id, "pilot")
    residual_slots = _intent_slots_by_variant(persona_id, "full-residual")
    pilot_eml = len(pilot_slots.get("eml", []))
    residual_eml = len(residual_slots.get("eml", []))
    full_eml = pilot_eml + residual_eml
    lower = (pilot_members + 4) // 5
    upper = min(
        pilot_members,
        pilot_eml,
        residual_eml // 9,
        full_eml // 10,
    )
    host_count = min((pilot_members + 1) // 2, upper)
    if host_count < lower:
        raise PersonaV2OverlayReservationError(
            f"attachment host capacity is infeasible for {persona_id}"
        )
    return {
        "full": 10 * host_count,
        "full-residual": 9 * host_count,
        "pilot": host_count,
    }


def _best_host_histogram(member_count, host_count):
    if (
        type(member_count) is not int
        or type(host_count) is not int
        or host_count < 0
        or not host_count <= member_count <= 5 * host_count
    ):
        raise PersonaV2OverlayReservationError(
            "attachment host histogram dimensions are infeasible"
        )
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
                    (
                        20 * observed
                        - host_count * target_weight
                    )
                    ** 2
                    for observed, target_weight in zip(
                        histogram, ATTACHMENT_HOST_STRESS_WEIGHTS
                    )
                )
                maximum_error = max(
                    abs(20 * observed - host_count * target_weight)
                    for observed, target_weight in zip(
                        histogram, ATTACHMENT_HOST_STRESS_WEIGHTS
                    )
                )
                key = (
                    squared_error,
                    maximum_error,
                    tuple(-value for value in histogram),
                )
                if best is None or key < best[0]:
                    best = (key, histogram)
    if best is None:
        raise PersonaV2OverlayReservationError(
            "no exact attachment host histogram exists"
        )
    return best[1]


def _host_histogram(persona_id, origin):
    target_profile = ORIGIN_TO_TARGET_PROFILE[origin]
    member_count = _persona_targets(persona_id)["targets"][target_profile][
        "attachment_membership_count"
    ]
    pilot_members = _persona_targets(persona_id)["targets"]["pilot"][
        "attachment_membership_count"
    ]
    pilot_hosts = _attachment_host_count(persona_id)["pilot"]
    pilot_histogram = _best_host_histogram(pilot_members, pilot_hosts)
    multiplier = 1 if origin == "pilot" else 9
    histogram = tuple(multiplier * value for value in pilot_histogram)
    if sum(histogram) != _attachment_host_count(persona_id)[origin]:
        raise PersonaV2OverlayReservationError("attachment host count drifted")
    if sum(
        members * count
        for members, count in zip(MEMBERS_PER_HOST_ORDER, histogram)
    ) != member_count:
        raise PersonaV2OverlayReservationError("attachment member count drifted")
    return {
        str(members): count
        for members, count in zip(MEMBERS_PER_HOST_ORDER, histogram)
    }


def _spread_cardinalities(histogram):
    target = {
        members: histogram[str(members)] for members in MEMBERS_PER_HOST_ORDER
    }
    total = sum(target.values())
    assigned = {members: 0 for members in MEMBERS_PER_HOST_ORDER}
    result = []
    for position in range(total):
        remaining = [
            members
            for members in MEMBERS_PER_HOST_ORDER
            if assigned[members] < target[members]
        ]
        chosen = min(
            remaining,
            key=lambda members: (
                -(
                    target[members] * (position + 1)
                    - assigned[members] * total
                ),
                members,
            ),
        )
        assigned[chosen] += 1
        result.append(chosen)
    if assigned != target:
        raise PersonaV2OverlayReservationError(
            "attachment cardinality spread lost mass"
        )
    return result


def _balanced_contingency(row_counts, column_counts):
    """Round the proportional 3x4 matrix with exact integer margins."""

    if (
        type(row_counts) is not list
        or type(column_counts) is not list
        or len(row_counts) != len(RELATION_ORDER)
        or len(column_counts) != len(PLACEMENT_ORDER)
        or any(type(value) is not int or value < 0 for value in row_counts)
        or any(type(value) is not int or value < 0 for value in column_counts)
        or sum(row_counts) != sum(column_counts)
        or sum(row_counts) <= 0
    ):
        raise PersonaV2OverlayReservationError(
            "relation/placement contingency margins are invalid"
        )
    total = sum(row_counts)
    base = [
        [row_total * column_total // total for column_total in column_counts]
        for row_total in row_counts
    ]
    row_deficits = [
        row_counts[index] - sum(base[index])
        for index in range(len(row_counts))
    ]
    column_deficits = [
        column_counts[column] - sum(row[column] for row in base)
        for column in range(len(column_counts))
    ]
    if sum(row_deficits) != sum(column_deficits):
        raise PersonaV2OverlayReservationError(
            "contingency rounding deficits lost mass"
        )
    remainders = [
        [row_total * column_total % total for column_total in column_counts]
        for row_total in row_counts
    ]
    candidates = []

    def visit(row_index, remaining_columns, additions):
        if row_index == len(row_counts):
            if any(remaining_columns):
                return
            flattened = tuple(
                additions[row][column]
                for row in range(len(row_counts))
                for column in range(len(column_counts))
            )
            score = sum(
                remainders[row][column] * additions[row][column]
                for row in range(len(row_counts))
                for column in range(len(column_counts))
            )
            candidates.append((-score, tuple(-value for value in flattened), additions))
            return
        deficit = row_deficits[row_index]
        for columns in itertools.combinations(range(len(column_counts)), deficit):
            if any(remaining_columns[column] <= 0 for column in columns):
                continue
            next_remaining = list(remaining_columns)
            row_additions = [0] * len(column_counts)
            for column in columns:
                next_remaining[column] -= 1
                row_additions[column] = 1
            visit(
                row_index + 1,
                next_remaining,
                additions + [row_additions],
            )

    visit(0, column_deficits, [])
    if not candidates:
        raise PersonaV2OverlayReservationError(
            "no exact relation/placement rounding exists"
        )
    additions = min(candidates)[2]
    matrix = [
        [base[row][column] + additions[row][column] for column in range(4)]
        for row in range(3)
    ]
    if [sum(row) for row in matrix] != row_counts or [
        sum(row[column] for row in matrix) for column in range(4)
    ] != column_counts:
        raise PersonaV2OverlayReservationError(
            "rounded relation/placement matrix differs from exact margins"
        )
    return matrix


def _relation_placement_matrix(persona_id, origin):
    target = _persona_targets(persona_id)["targets"][
        ORIGIN_TO_TARGET_PROFILE[origin]
    ]
    row_counts = [
        target[f"{relation.replace('-', '_')}_cluster_count"]
        for relation in RELATION_ORDER
    ]
    column_counts = [
        target["placement_demand_by_scope_class"][placement]
        for placement in PLACEMENT_ORDER
    ]
    matrix = _balanced_contingency(row_counts, column_counts)
    return {
        relation: {
            placement: matrix[row_index][column_index]
            for column_index, placement in enumerate(PLACEMENT_ORDER)
        }
        for row_index, relation in enumerate(RELATION_ORDER)
    }


def _placement_sequence(counts):
    total = sum(counts.values())
    assigned = {placement: 0 for placement in PLACEMENT_ORDER}
    result = []
    for position in range(total):
        remaining = [
            placement
            for placement in PLACEMENT_ORDER
            if assigned[placement] < counts[placement]
        ]
        chosen = min(
            remaining,
            key=lambda placement: (
                -(
                    counts[placement] * (position + 1)
                    - assigned[placement] * total
                ),
                PLACEMENT_ORDER.index(placement),
            ),
        )
        assigned[chosen] += 1
        result.append(chosen)
    if assigned != counts:
        raise PersonaV2OverlayReservationError(
            "placement sequence differs from its exact marginal"
        )
    return result


def _parse_intent_key(intent_key, *, persona_id, origin):
    match = _INTENT_KEY_RE.fullmatch(intent_key)
    if match is None or match.group(1) != persona_id or match.group(2) != origin:
        raise PersonaV2OverlayReservationError(
            f"intent key is outside the reservation domain: {intent_key!r}"
        )
    ordinal = int(match.group(3))
    if source_layout.intent_key(persona_id, origin, ordinal) != intent_key:
        raise PersonaV2OverlayReservationError(
            f"intent key is non-canonical: {intent_key!r}"
        )
    return ordinal


def _ordinal_width(origin):
    return 4 if origin == "pilot" else 5


def _semantic_keys(persona_id, origin, anchor_intent_key):
    ordinal = _parse_intent_key(
        anchor_intent_key, persona_id=persona_id, origin=origin
    )
    width = _ordinal_width(origin)
    stem = f"{persona_id}-{{kind}}-{origin}-syn-{ordinal:0{width}d}"
    result = {
        "document": stem.format(kind="logical-document"),
        "section": stem.format(kind="logical-section") + "-s0001",
    }
    for branch in (1, 2):
        branch_key = stem.format(kind="logical-branch") + f"-b{branch:02d}"
        result[f"branch_{branch}"] = branch_key
        for revision in (1, 2):
            result[f"revision_{branch}_{revision}"] = (
                stem.format(kind="logical-revision")
                + f"-b{branch:02d}-r{revision:04d}"
            )
    if any(_LOWER_ASCII_KEY_RE.fullmatch(value) is None for value in result.values()):
        raise PersonaV2OverlayReservationError(
            "logical identity key violates the bounded ASCII grammar"
        )
    return result


def _cluster_key(persona_id, origin, relation_kind, ordinal):
    width = _ordinal_width(origin)
    value = (
        f"{persona_id}-overlay-{origin}-{relation_kind}-syn-"
        f"{ordinal:0{width}d}"
    )
    if _LOWER_ASCII_KEY_RE.fullmatch(value) is None:
        raise PersonaV2OverlayReservationError("cluster key grammar drifted")
    return value


def _attachment_key(persona_id, origin, ordinal):
    width = _ordinal_width(origin)
    value = f"{persona_id}-attachment-{origin}-syn-{ordinal:0{width}d}"
    if _LOWER_ASCII_KEY_RE.fullmatch(value) is None:
        raise PersonaV2OverlayReservationError("attachment key grammar drifted")
    return value


def _payload_key(persona_id, origin, anchor_intent_key, suffix):
    ordinal = _parse_intent_key(
        anchor_intent_key, persona_id=persona_id, origin=origin
    )
    width = _ordinal_width(origin)
    value = (
        f"{persona_id}-payload-{origin}-syn-{ordinal:0{width}d}-{suffix}"
    )
    if _LOWER_ASCII_KEY_RE.fullmatch(value) is None:
        raise PersonaV2OverlayReservationError("payload key grammar drifted")
    return value


def _proportional_quotas(total, capacities, *, label):
    if (
        type(total) is not int
        or total < 0
        or type(capacities) is not dict
        or not capacities
        or any(type(key) is not str for key in capacities)
        or any(type(value) is not int or value < 0 for value in capacities.values())
        or total > sum(capacities.values())
    ):
        raise PersonaV2OverlayReservationError(
            f"invalid proportional quota dimensions for {label}"
        )
    capacity_total = sum(capacities.values())
    if total == 0:
        return {key: 0 for key in capacities}
    if capacity_total == 0:
        raise PersonaV2OverlayReservationError(f"zero capacity for {label}")
    result = {
        key: total * capacity // capacity_total
        for key, capacity in capacities.items()
    }
    remainder = total - sum(result.values())
    order = sorted(
        capacities,
        key=lambda key: (
            -(total * capacities[key] % capacity_total),
            key.encode("ascii"),
        ),
    )
    for key in order[:remainder]:
        result[key] += 1
    if sum(result.values()) != total or any(
        result[key] > capacities[key] for key in result
    ):
        raise PersonaV2OverlayReservationError(
            f"proportional quotas exceed capacity for {label}"
        )
    return result


def _spread_labels(quotas, *, label):
    total = sum(quotas.values())
    assigned = {key: 0 for key in quotas}
    result = []
    for position in range(total):
        eligible = [key for key in quotas if assigned[key] < quotas[key]]
        if not eligible:
            raise PersonaV2OverlayReservationError(
                f"label spread exhausted early for {label}"
            )
        chosen = min(
            eligible,
            key=lambda key: (
                -(quotas[key] * (position + 1) - assigned[key] * total),
                key.encode("ascii"),
            ),
        )
        assigned[chosen] += 1
        result.append(chosen)
    if assigned != quotas:
        raise PersonaV2OverlayReservationError(
            f"label spread differs from exact quotas for {label}"
        )
    return result


def _remove_selected(pool, selected, *, label):
    selected_set = set(selected)
    if len(selected_set) != len(selected) or not selected_set.issubset(pool):
        raise PersonaV2OverlayReservationError(
            f"selected source slots are invalid for {label}"
        )
    pool[:] = [value for value in pool if value not in selected_set]


def _allocate_same_variant_pairs(pools, count, eligible_variant_ids, *, label):
    variants = sorted(set(eligible_variant_ids), key=lambda value: value.encode("ascii"))
    capacities = {
        variant_id: len(pools.get(variant_id, [])) // 2
        for variant_id in variants
    }
    capacities = {key: value for key, value in capacities.items() if value > 0}
    quotas = _proportional_quotas(count, capacities, label=label)
    pairs_by_variant = {}
    for variant_id, quota in quotas.items():
        chosen = _midpoint_sample(
            pools[variant_id], 2 * quota, label=f"{label}/{variant_id}"
        )
        _remove_selected(
            pools[variant_id], chosen, label=f"{label}/{variant_id}"
        )
        pairs_by_variant[variant_id] = [
            (chosen[index], chosen[index + 1])
            for index in range(0, len(chosen), 2)
        ]
    result = []
    for variant_id in _spread_labels(quotas, label=label):
        first, second = pairs_by_variant[variant_id].pop(0)
        result.append(
            {
                "anchor_intent_key": first,
                "derivative_intent_key": second,
                "variant_id": variant_id,
            }
        )
    if len(result) != count or any(pairs_by_variant.values()):
        raise PersonaV2OverlayReservationError(
            f"same-variant pair allocation drifted for {label}"
        )
    return result


def _allocate_singletons(pools, count, eligible_variant_ids, *, label):
    variants = sorted(set(eligible_variant_ids), key=lambda value: value.encode("ascii"))
    capacities = {
        variant_id: len(pools.get(variant_id, [])) for variant_id in variants
    }
    capacities = {key: value for key, value in capacities.items() if value > 0}
    quotas = _proportional_quotas(count, capacities, label=label)
    values_by_variant = {}
    for variant_id, quota in quotas.items():
        chosen = _midpoint_sample(
            pools[variant_id], quota, label=f"{label}/{variant_id}"
        )
        _remove_selected(
            pools[variant_id], chosen, label=f"{label}/{variant_id}"
        )
        values_by_variant[variant_id] = chosen
    result = []
    for variant_id in _spread_labels(quotas, label=label):
        result.append(
            {
                "intent_key": values_by_variant[variant_id].pop(0),
                "variant_id": variant_id,
            }
        )
    if len(result) != count or any(values_by_variant.values()):
        raise PersonaV2OverlayReservationError(
            f"singleton allocation drifted for {label}"
        )
    return result


def _identity(
    *,
    logical_document_key,
    logical_branch_key,
    logical_revision_key,
    semantic_section_key,
    payload_equivalence_key,
):
    return {
        "logical_branch_key": logical_branch_key,
        "logical_document_key": logical_document_key,
        "logical_revision_key": logical_revision_key,
        "payload_equivalence_key": payload_equivalence_key,
        "semantic_section_key": semantic_section_key,
    }


def _content_identities(persona_id, origin, relation_kind, anchor_intent_key):
    keys = _semantic_keys(persona_id, origin, anchor_intent_key)
    if relation_kind == "exact-duplicate":
        payload = _payload_key(
            persona_id, origin, anchor_intent_key, "exact-shared"
        )
        return (
            _identity(
                logical_document_key=keys["document"],
                logical_branch_key=keys["branch_1"],
                logical_revision_key=keys["revision_1_1"],
                semantic_section_key=keys["section"],
                payload_equivalence_key=payload,
            ),
            _identity(
                logical_document_key=keys["document"],
                logical_branch_key=keys["branch_1"],
                logical_revision_key=keys["revision_1_1"],
                semantic_section_key=keys["section"],
                payload_equivalence_key=payload,
            ),
            "same-raw-and-decoded-payload-v2",
        )
    if relation_kind == "near-revision":
        return (
            _identity(
                logical_document_key=keys["document"],
                logical_branch_key=keys["branch_1"],
                logical_revision_key=keys["revision_1_1"],
                semantic_section_key=keys["section"],
                payload_equivalence_key=_payload_key(
                    persona_id, origin, anchor_intent_key, "near-r0001"
                ),
            ),
            _identity(
                logical_document_key=keys["document"],
                logical_branch_key=keys["branch_1"],
                logical_revision_key=keys["revision_1_2"],
                semantic_section_key=keys["section"],
                payload_equivalence_key=_payload_key(
                    persona_id, origin, anchor_intent_key, "near-r0002"
                ),
            ),
            "same-document-visible-later-revision-v2",
        )
    if relation_kind == "conflict-copy":
        return (
            _identity(
                logical_document_key=keys["document"],
                logical_branch_key=keys["branch_1"],
                logical_revision_key=keys["revision_1_1"],
                semantic_section_key=keys["section"],
                payload_equivalence_key=_payload_key(
                    persona_id, origin, anchor_intent_key, "conflict-b01"
                ),
            ),
            _identity(
                logical_document_key=keys["document"],
                logical_branch_key=keys["branch_2"],
                logical_revision_key=keys["revision_2_1"],
                semantic_section_key=keys["section"],
                payload_equivalence_key=_payload_key(
                    persona_id, origin, anchor_intent_key, "conflict-b02"
                ),
            ),
            "same-document-neutral-distinct-branches-v2",
        )
    raise PersonaV2OverlayReservationError(
        f"unknown content relation for identity: {relation_kind!r}"
    )


def _w0_current_fact_ids(graph):
    result = []
    for fact in graph["facts"]:
        states = [
            row["state"]
            for row in fact["visibility_by_checkpoint"]
            if row["checkpoint"] == "W0"
        ]
        if len(states) != 1:
            raise PersonaV2OverlayReservationError(
                "fact graph has a non-total W0 visibility state"
            )
        if states[0] == "current":
            result.append(fact["fact_id"])
    return sorted(result, key=lambda value: value.encode("ascii"))


def _conflict_templates(persona_id):
    graph_value = _shared_inputs()["fact_graphs"][persona_id]
    templates = []
    for ordinal, graph in enumerate(
        sorted(graph_value["graphs"], key=lambda value: value["graph_id"].encode("ascii")),
        start=1,
    ):
        if len(graph["conflict_sets"]) != 1:
            raise PersonaV2OverlayReservationError(
                "each authored graph must expose exactly one conflict template"
            )
        conflict_set = graph["conflict_sets"][0]
        pair = sorted(
            conflict_set["member_fact_ids"], key=lambda value: value.encode("ascii")
        )
        current = _w0_current_fact_ids(graph)
        common = [fact_id for fact_id in current if fact_id not in pair]
        facts = {fact["fact_id"]: fact for fact in graph["facts"]}
        if (
            len(pair) != 2
            or not set(pair).issubset(current)
            or len(current) != 8
            or len(common) != 6
            or facts[pair[0]]["subject_entity_id"]
            != facts[pair[1]]["subject_entity_id"]
            or facts[pair[0]]["predicate_id"] != facts[pair[1]]["predicate_id"]
            or facts[pair[0]]["typed_value"] == facts[pair[1]]["typed_value"]
        ):
            raise PersonaV2OverlayReservationError(
                f"invalid conflict fact template for {persona_id}/{graph['graph_id']}"
            )
        templates.append(
            {
                "branch_a_present_fact_ids": sorted(
                    common + [pair[0]], key=lambda value: value.encode("ascii")
                ),
                "branch_a_selected_fact_id": pair[0],
                "branch_b_present_fact_ids": sorted(
                    common + [pair[1]], key=lambda value: value.encode("ascii")
                ),
                "branch_b_selected_fact_id": pair[1],
                "common_w0_current_fact_ids": common,
                "conflict_set_id": conflict_set["conflict_set_id"],
                "graph_id": graph["graph_id"],
                "template_key": (
                    f"{persona_id}-conflict-fact-template-syn-{ordinal:02d}"
                ),
                "template_ordinal": ordinal,
                "unordered_member_fact_ids": pair,
            }
        )
    if len(templates) != 4:
        raise PersonaV2OverlayReservationError(
            f"expected four conflict fact templates for {persona_id}"
        )
    return templates


def _conflict_binding(persona_id, origin, conflict_ordinal, template_rows):
    pilot_count = _persona_targets(persona_id)["targets"]["pilot"][
        "conflict_copy_cluster_count"
    ]
    global_ordinal = (
        conflict_ordinal
        if origin == "pilot"
        else pilot_count + conflict_ordinal
    )
    template = template_rows[(global_ordinal - 1) % len(template_rows)]
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


def _identity_for_singleton(persona_id, origin, intent_key, *, payload_suffix):
    keys = _semantic_keys(persona_id, origin, intent_key)
    return _identity(
        logical_document_key=keys["document"],
        logical_branch_key=keys["branch_1"],
        logical_revision_key=keys["revision_1_1"],
        semantic_section_key=keys["section"],
        payload_equivalence_key=_payload_key(
            persona_id, origin, intent_key, payload_suffix
        ),
    )


def _relation_rows(persona_id, origin, pools, searchable_non_eml_variants):
    target = _persona_targets(persona_id)["targets"][
        ORIGIN_TO_TARGET_PROFILE[origin]
    ]
    relation_total = target["content_relation_cluster_count"]
    allocated_pairs = _allocate_same_variant_pairs(
        pools,
        relation_total,
        searchable_non_eml_variants,
        label=f"{persona_id}/{origin}/content-relation",
    )
    roles = _variant_roles()
    joint = _relation_placement_matrix(persona_id, origin)
    templates = _conflict_templates(persona_id)
    rows = []
    pair_index = 0
    conflict_ordinal = 0
    for relation_kind in RELATION_ORDER:
        relation_count = target[
            f"{relation_kind.replace('-', '_')}_cluster_count"
        ]
        placements = _placement_sequence(joint[relation_kind])
        for ordinal in range(1, relation_count + 1):
            pair = allocated_pairs[pair_index]
            pair_index += 1
            anchor_identity, derivative_identity, recipe = _content_identities(
                persona_id,
                origin,
                relation_kind,
                pair["anchor_intent_key"],
            )
            cluster_key = _cluster_key(
                persona_id, origin, relation_kind, ordinal
            )
            row = {
                "anchor_identity": anchor_identity,
                "anchor_intent_key": pair["anchor_intent_key"],
                "cluster_context_seed": f"{cluster_key}-context-v2",
                "cluster_key": cluster_key,
                "content_recipe_profile_id": recipe,
                "derivative_identity": derivative_identity,
                "derivative_intent_key": pair["derivative_intent_key"],
                "endpoint_gate_role": roles[pair["variant_id"]],
                "endpoint_variant_id": pair["variant_id"],
                "placement_class_requirement": placements[ordinal - 1],
                "relation_kind": relation_kind,
                "row_kind": "content-relation-reservation",
            }
            if row["endpoint_gate_role"] not in {
                "contract_contributor",
                "incidental_searchable",
            }:
                raise PersonaV2OverlayReservationError(
                    "content relation endpoint is not searchable"
                )
            if relation_kind == "conflict-copy":
                conflict_ordinal += 1
                row["conflict_fact_binding"] = _conflict_binding(
                    persona_id, origin, conflict_ordinal, templates
                )
            rows.append(row)
    if pair_index != len(allocated_pairs):
        raise PersonaV2OverlayReservationError(
            "content relation pair allocation has trailing values"
        )
    return rows, joint, templates


def _attachment_rows(
    persona_id,
    origin,
    pools,
    hosts,
    relation_rows,
    searchable_non_eml_variants,
    intent_to_variant,
):
    target = _persona_targets(persona_id)["targets"][
        ORIGIN_TO_TARGET_PROFILE[origin]
    ]
    member_count = target["attachment_membership_count"]
    overlap_count = target["attachment_exact_duplicate_overlap_count"]
    histogram = _host_histogram(persona_id, origin)
    cardinalities = _spread_cardinalities(histogram)
    if len(cardinalities) != len(hosts):
        raise PersonaV2OverlayReservationError(
            "attachment host cardinality count drifted"
        )
    exact_rows = [
        row for row in relation_rows if row["relation_kind"] == "exact-duplicate"
    ]
    selected_exact_rows = _midpoint_sample(
        exact_rows, overlap_count, label=f"{persona_id}/{origin}/exact-overlap"
    )
    selected_hosts = _midpoint_sample(
        hosts, overlap_count, label=f"{persona_id}/{origin}/overlap-hosts"
    )
    overlap_by_host = dict(zip(selected_hosts, selected_exact_rows))
    fresh_members = _allocate_singletons(
        pools,
        member_count - overlap_count,
        searchable_non_eml_variants,
        label=f"{persona_id}/{origin}/attachment-members",
    )
    fresh_index = 0
    rows = []
    roles = _variant_roles()
    for host_index, (host_intent_key, host_member_count) in enumerate(
        zip(hosts, cardinalities), start=1
    ):
        host_identity = _identity_for_singleton(
            persona_id, origin, host_intent_key, payload_suffix="host-container"
        )
        for member_ordinal in range(1, host_member_count + 1):
            overlap_row = (
                overlap_by_host.get(host_intent_key)
                if member_ordinal == 1
                else None
            )
            if overlap_row is not None:
                member_intent_key = overlap_row["derivative_intent_key"]
                member_variant_id = overlap_row["endpoint_variant_id"]
                member_identity = copy.deepcopy(overlap_row["derivative_identity"])
                relation_membership = overlap_row["cluster_key"]
            else:
                member = fresh_members[fresh_index]
                fresh_index += 1
                member_intent_key = member["intent_key"]
                member_variant_id = member["variant_id"]
                member_identity = _identity_for_singleton(
                    persona_id,
                    origin,
                    member_intent_key,
                    payload_suffix="attachment-member",
                )
                relation_membership = "none"
            attachment_ordinal = len(rows) + 1
            attachment_key = _attachment_key(
                persona_id, origin, attachment_ordinal
            )
            rows.append(
                {
                    "attachment_context_seed": f"{attachment_key}-context-v2",
                    "attachment_key": attachment_key,
                    "content_relation_membership": relation_membership,
                    "decoded_payload_equivalence_key": member_identity[
                        "payload_equivalence_key"
                    ],
                    "embedded_member_identity_source": (
                        "standalone-member-identity-exact"
                    ),
                    "host_gate_role": roles[intent_to_variant[host_intent_key]],
                    "host_identity": host_identity,
                    "host_intent_key": host_intent_key,
                    "host_member_count": host_member_count,
                    "host_ordinal": host_index,
                    "host_variant_id": intent_to_variant[host_intent_key],
                    "member_ordinal": member_ordinal,
                    "row_kind": "attachment-membership-reservation",
                    "standalone_member_gate_role": roles[member_variant_id],
                    "standalone_member_identity": member_identity,
                    "standalone_member_intent_key": member_intent_key,
                    "standalone_member_variant_id": member_variant_id,
                }
            )
    if fresh_index != len(fresh_members) or len(rows) != member_count:
        raise PersonaV2OverlayReservationError(
            "attachment member allocation differs from exact target"
        )
    return rows, histogram


def _variant_usage_marginals(
    original_pools,
    intent_to_variant,
    semantic_anchor_keys,
    relation_rows,
    attachment_rows,
):
    roles = _variant_roles()
    anchors = set(semantic_anchor_keys)
    endpoints = {
        key
        for row in relation_rows
        for key in (row["anchor_intent_key"], row["derivative_intent_key"])
    }
    hosts = {row["host_intent_key"] for row in attachment_rows}
    members = {row["standalone_member_intent_key"] for row in attachment_rows}
    overlap = endpoints & members
    all_reserved = anchors | endpoints | hosts | members
    rows = []
    for variant_id in sorted(original_pools, key=lambda value: value.encode("ascii")):
        source_keys = set(original_pools[variant_id])
        row = {
            "attachment_exact_overlap_intent_count": len(source_keys & overlap),
            "attachment_host_intent_count": len(source_keys & hosts),
            "attachment_member_reference_count": len(source_keys & members),
            "content_relation_endpoint_count": len(source_keys & endpoints),
            "gate_role": roles[variant_id],
            "semantic_anchor_slot_count": len(source_keys & anchors),
            "source_intent_count": len(source_keys),
            "unique_reserved_source_intent_count": len(source_keys & all_reserved),
            "unreserved_source_intent_count": len(source_keys - all_reserved),
            "variant_id": variant_id,
        }
        if row["source_intent_count"]:
            rows.append(row)
    return rows


def _validate_origin_built_value(value):
    _require_negative_authority(value, label="overlay reservation origin")
    if value.get("fixture_id") != envelope.FIXTURE_ID:
        raise PersonaV2OverlayReservationError("reservation fixture identity drifted")
    if value.get("fixture_schema_version") != envelope.FIXTURE_SCHEMA_VERSION:
        raise PersonaV2OverlayReservationError(
            "reservation fixture schema version drifted"
        )
    rows = value["reservation_rows"]
    if len(rows) > MAX_ROWS_PER_ORIGIN:
        raise PersonaV2OverlayReservationError("reservation origin exceeds row cap")
    maximum_row_bytes = 0
    for row in rows:
        try:
            raw = artifact_common.canonical_json_bytes(
                row,
                label="persona v2 overlay reservation row",
                max_bytes=MAX_RESERVATION_ROW_BYTES - 1,
            )
        except artifact_common.PersonaV2ArtifactError as error:
            raise PersonaV2OverlayReservationError(str(error)) from None
        maximum_row_bytes = max(maximum_row_bytes, len(raw) + 1)
    if maximum_row_bytes != value["summary"]["maximum_row_bytes_including_lf"]:
        raise PersonaV2OverlayReservationError(
            "reservation maximum row byte summary drifted"
        )


@functools.lru_cache(maxsize=40)
def _canonical_origin(persona_id, origin):
    _require_persona_id(persona_id)
    _require_origin(origin)
    original_pools = _intent_slots_by_variant(persona_id, origin)
    pools = copy.deepcopy(original_pools)
    intent_to_variant = {
        intent_key: variant_id
        for variant_id, intent_keys in original_pools.items()
        for intent_key in intent_keys
    }
    roles = _variant_roles()
    contributor_variants = [
        variant_id
        for variant_id in pools
        if roles[variant_id] == "contract_contributor"
    ]
    searchable_non_eml_variants = [
        variant_id
        for variant_id in pools
        if variant_id != "eml"
        and roles[variant_id]
        in {"contract_contributor", "incidental_searchable"}
    ]
    semantic_anchor_keys = []
    if origin == "pilot":
        semantic_anchor_keys = _take_round_robin(
            pools,
            PILOT_SEMANTIC_ANCHOR_SLOT_COUNT,
            contributor_variants,
            label=f"{persona_id}/pilot/semantic-anchor-slots",
        )
    host_count = _attachment_host_count(persona_id)[origin]
    eml_candidates = list(pools.get("eml", []))
    hosts = _midpoint_sample(
        eml_candidates, host_count, label=f"{persona_id}/{origin}/eml-hosts"
    )
    _remove_selected(pools["eml"], hosts, label=f"{persona_id}/{origin}/eml-hosts")

    relation_rows, joint_matrix, conflict_templates = _relation_rows(
        persona_id, origin, pools, searchable_non_eml_variants
    )
    attachment_rows, host_histogram = _attachment_rows(
        persona_id,
        origin,
        pools,
        hosts,
        relation_rows,
        searchable_non_eml_variants,
        intent_to_variant,
    )
    host_histogram = {
        "0": len(original_pools.get("eml", [])) - len(hosts),
        **host_histogram,
    }
    reservation_rows = relation_rows + attachment_rows
    target = copy.deepcopy(
        _persona_targets(persona_id)["targets"][ORIGIN_TO_TARGET_PROFILE[origin]]
    )
    endpoint_keys = {
        key
        for row in relation_rows
        for key in (row["anchor_intent_key"], row["derivative_intent_key"])
    }
    host_keys = {row["host_intent_key"] for row in attachment_rows}
    member_keys = {row["standalone_member_intent_key"] for row in attachment_rows}
    overlap_keys = endpoint_keys & member_keys
    anchor_set = set(semantic_anchor_keys)
    if (
        len(endpoint_keys) != 2 * target["content_relation_cluster_count"]
        or len(host_keys) != host_count
        or len(member_keys) != target["attachment_membership_count"]
        or len(overlap_keys) != target["attachment_exact_duplicate_overlap_count"]
        or anchor_set & (endpoint_keys | host_keys | member_keys)
        or host_keys & (endpoint_keys | member_keys)
    ):
        raise PersonaV2OverlayReservationError(
            f"source slot disjointness or overlap target drifted: {persona_id}/{origin}"
        )
    maximum_row_bytes = max(
        len(
            artifact_common.canonical_json_bytes(
                row,
                label="persona v2 overlay reservation row",
                max_bytes=MAX_RESERVATION_ROW_BYTES - 1,
            )
        )
        + 1
        for row in reservation_rows
    )
    source_count = sum(len(values) for values in original_pools.values())
    overlay_referenced = endpoint_keys | host_keys | member_keys
    value = {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {field: False for field in sorted(AUTHORITY_FIELDS)},
        "canonical_limits": {
            "max_body_bytes": MAX_ORIGIN_ARTIFACT_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_reservation_row_bytes_including_lf": MAX_RESERVATION_ROW_BYTES,
            "max_rows": MAX_ROWS_PER_ORIGIN,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "null_float_or_negative_integer_allowed": False,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
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
        },
        "completion_scope": (
            "exact-pre-source-overlay-reservation-only-no-source-row-body-no-concrete-"
            "membership-no-scope-solution-no-rendered-bytes-no-execution-no-g0"
        ),
        "conflict_fact_templates": conflict_templates,
        "dependency_direction_contract": {
            "concrete_membership_must_bind_reservation_and_source_fact_manifests": True,
            "evaluation_query_or_oracle_identity_imported": False,
            "source_intent_manifest_must_bind_reservation": True,
            "reservation_may_bind_concrete_source_or_fact_manifest": False,
            "solved_scope_or_final_identity_allowed": False,
        },
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "hypothesis_status": (
            "authored-benchmark-stress-reservation-not-observed-user-statistics"
        ),
        "input_bindings": list(_shared_inputs()["base_bindings"])
        + [copy.deepcopy(_shared_inputs()["fact_graph_bindings"][persona_id])],
        "origin": origin,
        "persona_id": persona_id,
        "relation_placement_joint_marginals": joint_matrix,
        "remaining_blockers": [
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
        ],
        "reservation_contract": {
            "attachment_exact_overlap_member_side": "derivative",
            "attachment_member_cardinality_order": list(MEMBERS_PER_HOST_ORDER),
            "conflict_fact_pair_reuse_allowed": True,
            "conflict_branch_a_maps_to_anchor_endpoint": True,
            "conflict_branch_b_maps_to_derivative_endpoint": True,
            "content_relation_endpoint_variants_must_match": True,
            "content_relation_endpoint_variants_must_not_be_eml": True,
            "cross_cluster_intent_or_logical_identity_reuse_allowed": False,
            "eml_fanout_zero_bin_counts_unselected_eml_intents": True,
            "fact_template_reuse_is_not-independent-semantic-conflict-count": True,
            "full_conflict_order_continues_from_pilot_into_residual": True,
            "host_variant_id": "eml",
            "placement_class_is_requirement_not_scope_assignment": True,
            "semantic_anchor_slots_are_corpus_capacity_not_query_mapping": True,
        },
        "reservation_rows": reservation_rows,
        "semantic_anchor_slots": [
            {
                "gate_role": roles[intent_to_variant[intent_key]],
                "intent_key": intent_key,
                "semantic_anchor_slot_ordinal": ordinal,
                "variant_id": intent_to_variant[intent_key],
            }
            for ordinal, intent_key in enumerate(semantic_anchor_keys, start=1)
        ],
        "summary": {
            "attachment_exact_overlap_intent_count": len(overlap_keys),
            "eml_attachment_fanout_histogram": host_histogram,
            "attachment_host_intent_count": len(host_keys),
            "attachment_membership_row_count": len(attachment_rows),
            "content_relation_row_count": len(relation_rows),
            "maximum_row_bytes_including_lf": maximum_row_bytes,
            "overlay_referenced_unique_source_intent_count": len(overlay_referenced),
            "reservation_row_count": len(reservation_rows),
            "semantic_anchor_slot_count": len(semantic_anchor_keys),
            "source_origin_intent_count": source_count,
            "unreserved_source_intent_count": (
                source_count - len(overlay_referenced | anchor_set)
            ),
        },
        "target_marginals": target,
        "target_profile": ORIGIN_TO_TARGET_PROFILE[origin],
        "variant_usage_marginals": _variant_usage_marginals(
            original_pools,
            intent_to_variant,
            semantic_anchor_keys,
            relation_rows,
            attachment_rows,
        ),
    }
    _validate_origin_built_value(value)
    try:
        artifact_common.canonical_json_bytes(
            value,
            label="persona v2 overlay reservation origin",
            max_bytes=MAX_ORIGIN_ARTIFACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2OverlayReservationError(str(error)) from None
    return value


def build_overlay_reservation_origin(persona_id, origin):
    """Return one detached persona/origin pre-source reservation artifact."""

    return copy.deepcopy(_canonical_origin(persona_id, origin))


def build_overlay_reservation_origin_suite():
    """Return all forty detached origin artifacts in canonical suite order."""

    return [
        build_overlay_reservation_origin(persona_id, origin)
        for persona_id in envelope.PERSONA_IDS
        for origin in ORIGIN_ORDER
    ]


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 overlay reservation origin",
            max_bytes=MAX_ORIGIN_ARTIFACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2OverlayReservationError(str(error)) from None


def validate_overlay_reservation_origin(persona_id, origin, value):
    _require_persona_id(persona_id)
    _require_origin(origin)
    try:
        artifact_common.validate_exact_regeneration(
            value,
            builder=lambda: build_overlay_reservation_origin(persona_id, origin),
            label="persona v2 overlay reservation origin",
            max_bytes=MAX_ORIGIN_ARTIFACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2OverlayReservationError(str(error)) from None
    _validate_origin_built_value(value)
    return True


def overlay_reservation_origin_sha256(persona_id, origin, value=None):
    _require_persona_id(persona_id)
    _require_origin(origin)
    try:
        return artifact_common.canonical_sha256(
            value,
            builder=lambda: build_overlay_reservation_origin(persona_id, origin),
            label="persona v2 overlay reservation origin",
            max_bytes=MAX_ORIGIN_ARTIFACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2OverlayReservationError(str(error)) from None


def _add_nested_counts(target, source):
    for key, value in source.items():
        if type(value) is dict:
            child = target.setdefault(key, {})
            _add_nested_counts(child, value)
        else:
            target[key] = target.get(key, 0) + value


@functools.lru_cache(maxsize=1)
def _canonical_suite():
    descriptors = []
    relation_placement = {
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
    origin_totals = {
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
    total_origin_bytes = 0
    maximum_origin_bytes = 0
    maximum_row_bytes = 0
    for persona_id in envelope.PERSONA_IDS:
        for origin in ORIGIN_ORDER:
            artifact = _canonical_origin(persona_id, origin)
            raw = canonical_json_bytes(artifact)
            digest = hashlib.sha256(raw).hexdigest()
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
                    "origin": origin,
                    "persona_id": persona_id,
                    "reservation_row_count": summary["reservation_row_count"],
                    "sha256": digest,
                    "target_profile": artifact["target_profile"],
                }
            )
            total_origin_bytes += len(raw)
            maximum_origin_bytes = max(maximum_origin_bytes, len(raw))
            maximum_row_bytes = max(
                maximum_row_bytes, summary["maximum_row_bytes_including_lf"]
            )
            for key in origin_totals[origin]:
                origin_totals[origin][key] += summary[key]
            _add_nested_counts(
                relation_placement[origin],
                artifact["relation_placement_joint_marginals"],
            )
            histogram = summary["eml_attachment_fanout_histogram"]
            for cardinality in MEMBERS_PER_HOST_ORDER:
                host_histograms[origin][str(cardinality)] += histogram[
                    str(cardinality)
                ]
            host_histograms[origin]["0"] += histogram["0"]
    full_totals = copy.deepcopy(origin_totals["pilot"])
    _add_nested_counts(full_totals, origin_totals["full-residual"])
    full_relation_placement = copy.deepcopy(relation_placement["pilot"])
    _add_nested_counts(
        full_relation_placement, relation_placement["full-residual"]
    )
    full_host_histogram = copy.deepcopy(host_histograms["pilot"])
    _add_nested_counts(full_host_histogram, host_histograms["full-residual"])
    value = {
        "artifact_kind": SUITE_ARTIFACT_KIND,
        "artifact_schema": SUITE_ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {field: False for field in sorted(AUTHORITY_FIELDS)},
        "canonical_limits": {
            "max_body_bytes": MAX_SUITE_ARTIFACT_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_scope": (
            "compact-binding-of-forty-pre-source-reservations-only-no-source-or-"
            "membership-manifest-no-solver-no-rendered-bytes-no-execution-no-g0"
        ),
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "full_composition_contract": {
            "full_equals_pilot_plus_full_residual_coordinatewise": True,
            "pilot_origin_artifact_bytes_reused_unchanged": True,
        },
        "g0_contract_frozen": False,
        "input_bindings": list(_shared_inputs()["base_bindings"]),
        "orders": {
            "origin": list(ORIGIN_ORDER),
            "persona": list(envelope.PERSONA_IDS),
            "relation": list(RELATION_ORDER),
            "placement": list(PLACEMENT_ORDER),
        },
        "origin_bindings": descriptors,
        "remaining_blockers": [
            "source-intent-row-bodies-and-manifests-not-present",
            "fact-membership-and-concrete-overlay-membership-not-present",
            "format-rendition-and-evaluation-target-mapping-not-present",
            "scope-solution-rendering-history-and-observation-not-present",
            "independent-reservation-review-receipt-not-bound",
        ],
        "suite_summary": {
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
                "full": full_relation_placement,
                "full-minus-pilot": relation_placement["full-residual"],
                "pilot": relation_placement["pilot"],
            },
        },
    }
    _require_negative_authority(value, label="overlay reservation suite")
    try:
        artifact_common.canonical_json_bytes(
            value,
            label="persona v2 overlay reservation suite",
            max_bytes=MAX_SUITE_ARTIFACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2OverlayReservationError(str(error)) from None
    return value


def build_overlay_reservation_suite():
    """Return the compact descriptor that binds all forty origin artifacts."""

    return copy.deepcopy(_canonical_suite())


def overlay_reservation_suite_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 overlay reservation suite",
            max_bytes=MAX_SUITE_ARTIFACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2OverlayReservationError(str(error)) from None


def validate_overlay_reservation_suite(value):
    try:
        artifact_common.validate_exact_regeneration(
            value,
            builder=build_overlay_reservation_suite,
            label="persona v2 overlay reservation suite",
            max_bytes=MAX_SUITE_ARTIFACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2OverlayReservationError(str(error)) from None
    _require_negative_authority(value, label="overlay reservation suite")
    return True


def overlay_reservation_suite_sha256(value=None):
    try:
        return artifact_common.canonical_sha256(
            value,
            builder=build_overlay_reservation_suite,
            label="persona v2 overlay reservation suite",
            max_bytes=MAX_SUITE_ARTIFACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2OverlayReservationError(str(error)) from None


def require_concrete_overlay_membership():
    raise PersonaV2OverlayReservationError(
        "the forty persona/origin source-slot reservations are exact, but 203,000 "
        "source row bodies/manifests, complete fact membership, concrete overlay "
        "membership, scope solution, rendering, and execution authority remain absent"
    )
