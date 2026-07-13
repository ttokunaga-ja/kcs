"""Deterministic format-variant-to-scope allocation for persona fixtures.

The specification fixes two independent marginals: physical file counts by
format family and physical file capacities by direct-file scope.  This module
joins those marginals without changing either one.  Contract-contributor
variants are routed through a required slot for every scope, so the allocation
also proves that each scope can carry its declared contributor chunk target.

Routing hints are preferences rather than extra quotas.  A deterministic
minimum-cost flow maximizes the total path affinity while preserving all hard
constraints.  The returned structure contains only JSON-compatible values and
is intended to be persisted by the fixture generator as its W0 plan.
"""

from heapq import heappop, heappush

try:  # Support package imports and direct ``eval/*.py`` script execution.
    from . import persona_fixture_spec as spec
except ImportError:  # pragma: no cover - exercised by direct generator startup
    import persona_fixture_spec as spec


ALLOCATION_SCHEMA_VERSION = 1


class AllocationError(ValueError):
    """Raised when the specification's marginals cannot be jointly allocated."""


class _Edge:
    __slots__ = ("to", "reverse", "capacity", "cost", "initial_capacity")

    def __init__(self, to, reverse, capacity, cost):
        self.to = to
        self.reverse = reverse
        self.capacity = capacity
        self.cost = cost
        self.initial_capacity = capacity


def _add_edge(graph, source, destination, capacity, cost):
    forward = _Edge(destination, len(graph[destination]), capacity, cost)
    reverse = _Edge(source, len(graph[source]), 0, -cost)
    graph[source].append(forward)
    graph[destination].append(reverse)
    return forward


def _component_matches_hint(component, hint):
    if component == hint:
        return True
    # Scope names deliberately use compounds such as ``archive-scans`` and
    # ``ticket-exports``.  A one-word hint matches one complete hyphen token;
    # it never matches an arbitrary substring (for example, data != metadata).
    return "-" not in hint and hint in component.split("-")


def matched_route_hints(family, relative_path):
    """Return routing hints matched by a portable scope path, in spec order."""
    if family not in spec.FORMAT_KEYS:
        raise AllocationError(f"unknown format family: {family}")
    components = spec.validate_relative_scope(relative_path)
    return tuple(
        hint
        for hint in spec.FORMAT_ROUTE_HINTS.get(family, ())
        if any(_component_matches_hint(component, hint) for component in components)
    )


def route_affinity(family, relative_path):
    """Score one family/scope pair using only frozen routing hints.

    A matched token dominates exactness and depth, an exact component beats a
    hyphen-token match, and a deeper match is the final deterministic routing
    preference.  Families without declared hints receive zero affinity.
    """
    if family not in spec.FORMAT_KEYS:
        raise AllocationError(f"unknown format family: {family}")
    components = spec.validate_relative_scope(relative_path)
    score = 0
    for hint in spec.FORMAT_ROUTE_HINTS.get(family, ()):
        positions = tuple(
            index
            for index, component in enumerate(components)
            if _component_matches_hint(component, hint)
        )
        if not positions:
            continue
        exact = any(components[index] == hint for index in positions)
        score += 1_000 + (100 if exact else 0) + max(positions)
    return score


def _resolve_persona(persona_or_id):
    if isinstance(persona_or_id, str):
        try:
            return spec.get_persona(persona_or_id)
        except KeyError as error:
            raise AllocationError(f"unknown persona: {persona_or_id}") from error
    if not isinstance(persona_or_id, dict) or "id" not in persona_or_id:
        raise AllocationError("persona must be a persona id or specification row")
    try:
        canonical = spec.get_persona(persona_or_id["id"])
    except KeyError as error:
        raise AllocationError(f"unknown persona: {persona_or_id['id']}") from error
    if persona_or_id != canonical:
        raise AllocationError(f"persona row differs from canonical spec: {persona_or_id['id']}")
    return canonical


def _variant_rows(persona, profile_name):
    variants = spec.format_variant_counts(persona, profile_name)
    rows = []
    for family in spec.FORMAT_KEYS:
        for entry in variants[family]:
            rows.append({
                "family": family,
                "variant": entry["variant"],
                "gate_role": entry["gate_role"],
                "expected_disposition": entry["expected_disposition"],
                "count": entry["count"],
            })
    return tuple(rows)


def _bounded_proportional_counts(total, weights, lower_bounds, upper_bounds):
    """Apportion ``total`` near the weighted ideal within inclusive bounds."""
    if not isinstance(total, int) or total < 0:
        raise AllocationError("bounded allocation total must be a non-negative integer")
    if not weights or not (
        len(weights) == len(lower_bounds) == len(upper_bounds)
    ):
        raise AllocationError("bounded allocation vectors must be non-empty and equal length")
    if any(not isinstance(value, int) or value < 0 for value in weights):
        raise AllocationError("bounded allocation weights must be non-negative integers")
    if any(
        not isinstance(lower, int)
        or not isinstance(upper, int)
        or lower < 0
        or upper < lower
        for lower, upper in zip(lower_bounds, upper_bounds)
    ):
        raise AllocationError("invalid bounded allocation interval")
    denominator = sum(weights)
    if denominator <= 0:
        raise AllocationError("bounded allocation weights must have a positive sum")
    if total < sum(lower_bounds) or total > sum(upper_bounds):
        raise AllocationError(
            "bounded allocation total falls outside aggregate lower/upper bounds"
        )

    counts = list(lower_bounds)
    queue = []
    for index, (weight, count, upper) in enumerate(
        zip(weights, counts, upper_bounds)
    ):
        if count < upper:
            # All priorities share the denominator.  The integer numerator is
            # the distance from this scope's proportional ideal; lower index
            # is the stable tie-break.
            deficit = total * weight - count * denominator
            heappush(queue, (-deficit, index))
    remaining = total - sum(counts)
    while remaining:
        if not queue:
            raise AllocationError("bounded allocation exhausted its upper bounds")
        _, index = heappop(queue)
        counts[index] += 1
        remaining -= 1
        if counts[index] < upper_bounds[index]:
            deficit = total * weights[index] - counts[index] * denominator
            heappush(queue, (-deficit, index))
    return tuple(counts)


def _contributor_file_targets(
    contributor_files,
    scope_rows,
    scope_totals,
    contributor_minima,
    chunk_targets,
):
    scope_keys = tuple(scope["scope_key"] for scope in scope_rows)
    lower_bounds = tuple(contributor_minima[key] for key in scope_keys)
    upper_bounds = tuple(
        min(chunk_targets[key], scope_totals[key]) for key in scope_keys
    )
    if contributor_files < sum(lower_bounds):
        raise AllocationError(
            f"contributor inventory has {contributor_files} files but scope minima "
            f"require {sum(lower_bounds)}"
        )
    if contributor_files > sum(upper_bounds):
        raise AllocationError(
            f"contributor inventory has {contributor_files} files but scope one-chunk "
            f"upper bounds allow only {sum(upper_bounds)}"
        )
    values = _bounded_proportional_counts(
        contributor_files,
        tuple(chunk_targets[key] for key in scope_keys),
        lower_bounds,
        upper_bounds,
    )
    return dict(zip(scope_keys, values))


def scope_contributor_file_targets(persona_or_id, profile_name):
    """Return exact per-scope contributor file quotas for chunk generation."""
    persona = _resolve_persona(persona_or_id)
    try:
        rows = _variant_rows(persona, profile_name)
        scopes = spec.scope_specs(persona)
        scope_totals = spec.scope_file_counts(persona, profile_name)
        minima = spec.scope_contributor_file_minima(persona, profile_name)
        chunk_targets = spec.scope_contributor_chunk_targets(persona, profile_name)
    except (KeyError, ZeroDivisionError, ValueError) as error:
        raise AllocationError(str(error)) from error
    contributor_files = sum(
        row["count"] for row in rows if row["gate_role"] == "contract_contributor"
    )
    try:
        return _contributor_file_targets(
            contributor_files,
            scopes,
            scope_totals,
            minima,
            chunk_targets,
        )
    except AllocationError as error:
        raise AllocationError(f"{persona['id']} {profile_name}: {error}") from error


def _scope_slots(scope_rows, scope_totals, contributor_targets):
    slots = []
    for scope_index, scope_row in enumerate(scope_rows):
        scope_key = scope_row["scope_key"]
        capacity = scope_totals[scope_key]
        contributor_target = contributor_targets[scope_key]
        if contributor_target:
            slots.append({
                "scope_index": scope_index,
                "slot_kind": "contract_contributor",
                "demand": contributor_target,
            })
        if capacity - contributor_target:
            slots.append({
                "scope_index": scope_index,
                "slot_kind": "other",
                "demand": capacity - contributor_target,
            })
    return tuple(slots)


def _minimum_cost_allocation(rows, scope_rows, slots):
    """Return a variant-row by scope matrix with maximum routing affinity."""
    row_count = len(rows)
    slot_count = len(slots)
    source = 0
    first_row = 1
    first_slot = first_row + row_count
    sink = first_slot + slot_count
    graph = [[] for _ in range(sink + 1)]

    for row_index, row in enumerate(rows):
        _add_edge(graph, source, first_row + row_index, row["count"], 0)

    affinities = tuple(
        tuple(
            route_affinity(row["family"], scope_row["relative_path"])
            for scope_row in scope_rows
        )
        for row in rows
    )
    maximum_affinity = max(
        (score for row_scores in affinities for score in row_scores),
        default=0,
    )

    edge_refs = {}
    for row_index, row in enumerate(rows):
        if not row["count"]:
            continue
        for slot_index, slot in enumerate(slots):
            row_slot_kind = (
                "contract_contributor"
                if row["gate_role"] == "contract_contributor"
                else "other"
            )
            if slot["slot_kind"] != row_slot_kind:
                continue
            capacity = min(row["count"], slot["demand"])
            if not capacity:
                continue
            scope_index = slot["scope_index"]
            # Every transported unit pays the same maximum-affinity constant,
            # so minimizing this non-negative cost maximizes total affinity.
            edge_refs[(row_index, slot_index)] = _add_edge(
                graph,
                first_row + row_index,
                first_slot + slot_index,
                capacity,
                maximum_affinity - affinities[row_index][scope_index],
            )

    for slot_index, slot in enumerate(slots):
        _add_edge(
            graph,
            first_slot + slot_index,
            sink,
            slot["demand"],
            0,
        )

    target = sum(slot["demand"] for slot in slots)
    sent = 0
    potentials = [0] * len(graph)
    infinity = None

    while sent < target:
        distances = [infinity] * len(graph)
        previous_node = [-1] * len(graph)
        previous_edge = [-1] * len(graph)
        distances[source] = 0
        queue = [(0, source)]
        while queue:
            distance, node = heappop(queue)
            if distance != distances[node]:
                continue
            for edge_index, edge in enumerate(graph[node]):
                if edge.capacity <= 0:
                    continue
                reduced_cost = edge.cost + potentials[node] - potentials[edge.to]
                if reduced_cost < 0:
                    raise AssertionError("negative reduced cost in deterministic flow")
                candidate = distance + reduced_cost
                if distances[edge.to] is None or candidate < distances[edge.to]:
                    distances[edge.to] = candidate
                    previous_node[edge.to] = node
                    previous_edge[edge.to] = edge_index
                    heappush(queue, (candidate, edge.to))

        if distances[sink] is None:
            raise AllocationError("format and scope constraints have no feasible joint allocation")
        for node, distance in enumerate(distances):
            if distance is not None:
                potentials[node] += distance

        amount = target - sent
        node = sink
        while node != source:
            predecessor = previous_node[node]
            if predecessor < 0:
                raise AssertionError("incomplete augmenting path")
            edge = graph[predecessor][previous_edge[node]]
            amount = min(amount, edge.capacity)
            node = predecessor
        node = sink
        while node != source:
            predecessor = previous_node[node]
            edge = graph[predecessor][previous_edge[node]]
            edge.capacity -= amount
            graph[node][edge.reverse].capacity += amount
            node = predecessor
        sent += amount

    matrix = [[0 for _ in scope_rows] for _ in rows]
    for (row_index, slot_index), edge in edge_refs.items():
        flow = edge.initial_capacity - edge.capacity
        matrix[row_index][slots[slot_index]["scope_index"]] += flow
    return tuple(tuple(row) for row in matrix)


def build_allocation_plan(persona_or_id, profile_name):
    """Build and validate one JSON-compatible W0 generator allocation plan."""
    persona = _resolve_persona(persona_or_id)
    try:
        total_files = spec.raw_file_count(persona, profile_name)
        family_totals = spec.format_file_counts(persona, profile_name)
        scope_totals = spec.scope_file_counts(persona, profile_name)
        contributor_minima = spec.scope_contributor_file_minima(persona, profile_name)
        chunk_targets = spec.scope_contributor_chunk_targets(persona, profile_name)
    except (KeyError, ZeroDivisionError, ValueError) as error:
        raise AllocationError(str(error)) from error

    rows = _variant_rows(persona, profile_name)
    scopes = spec.scope_specs(persona)
    if sum(row["count"] for row in rows) != total_files:
        raise AllocationError("variant rows do not equal the raw-file total")
    if sum(scope_totals.values()) != total_files:
        raise AllocationError("scope columns do not equal the raw-file total")
    for scope in scopes:
        scope_key = scope["scope_key"]
        capacity = scope_totals[scope_key]
        minimum = contributor_minima[scope_key]
        if capacity >= spec.MAX_DIRECT_FILES_PER_SCOPE:
            raise AllocationError(f"scope lacks required direct-file headroom: {scope_key}")
        if minimum > capacity:
            raise AllocationError(f"contributor minimum exceeds scope capacity: {scope_key}")
        if minimum * spec.MAX_CONTRIBUTOR_CHUNKS_PER_FILE < chunk_targets[scope_key]:
            raise AllocationError(f"contributor minimum cannot carry chunk target: {scope_key}")

    contributor_files = sum(
        row["count"] for row in rows if row["gate_role"] == "contract_contributor"
    )
    required_contributor_files = sum(contributor_minima.values())
    if contributor_files < required_contributor_files:
        raise AllocationError(
            f"{persona['id']} {profile_name} has {contributor_files} contributor files "
            f"but scope minima require {required_contributor_files}"
        )

    try:
        contributor_targets = _contributor_file_targets(
            contributor_files,
            scopes,
            scope_totals,
            contributor_minima,
            chunk_targets,
        )
    except AllocationError as error:
        raise AllocationError(f"{persona['id']} {profile_name}: {error}") from error

    slots = _scope_slots(scopes, scope_totals, contributor_targets)
    matrix = _minimum_cost_allocation(rows, scopes, slots)

    assignments = []
    scope_allocations = []
    routing_affinity_total = 0
    for scope_index, scope in enumerate(scopes):
        scope_key = scope["scope_key"]
        relative_path = scope["relative_path"]
        format_counts = {family: 0 for family in spec.FORMAT_KEYS}
        assigned_contributors = 0
        for row_index, row in enumerate(rows):
            count = matrix[row_index][scope_index]
            if not count:
                continue
            affinity = route_affinity(row["family"], relative_path)
            hints = matched_route_hints(row["family"], relative_path)
            format_counts[row["family"]] += count
            if row["gate_role"] == "contract_contributor":
                assigned_contributors += count
            routing_affinity_total += count * affinity
            assignments.append({
                "scope_key": scope_key,
                "relative_path": relative_path,
                "family": row["family"],
                "variant": row["variant"],
                "gate_role": row["gate_role"],
                "expected_disposition": row["expected_disposition"],
                "count": count,
                "route_affinity": affinity,
                "matched_route_hints": list(hints),
            })
        scope_allocations.append({
            "scope_key": scope_key,
            "kind": scope["kind"],
            "relative_path": relative_path,
            "file_count": scope_totals[scope_key],
            "contributor_file_minimum": contributor_minima[scope_key],
            "contributor_files": assigned_contributors,
            "contributor_chunk_target": chunk_targets[scope_key],
            "contributor_chunk_capacity": (
                assigned_contributors * spec.MAX_CONTRIBUTOR_CHUNKS_PER_FILE
            ),
            "format_counts": format_counts,
        })

    plan = {
        "allocation_schema_version": ALLOCATION_SCHEMA_VERSION,
        "fixture_schema_version": spec.SCHEMA_VERSION,
        "fixture_id": spec.FIXTURE_ID,
        "persona_id": persona["id"],
        "profile": profile_name,
        "total_files": total_files,
        "format_totals": family_totals,
        "variant_totals": list(rows),
        "scope_totals": scope_totals,
        "scope_contributor_file_minima": contributor_minima,
        "scope_contributor_file_targets": contributor_targets,
        "scope_contributor_chunk_targets": chunk_targets,
        "routing_affinity_total": routing_affinity_total,
        "scope_allocations": scope_allocations,
        "assignments": assignments,
    }
    validate_allocation_plan(plan, persona)
    return plan


def validate_allocation_plan(plan, persona_or_id=None):
    """Fail closed unless a plan exactly attests every frozen marginal."""
    if not isinstance(plan, dict):
        raise AllocationError("allocation plan must be a dictionary")
    persona = _resolve_persona(persona_or_id or plan.get("persona_id"))
    profile_name = plan.get("profile")
    try:
        expected_total = spec.raw_file_count(persona, profile_name)
        expected_families = spec.format_file_counts(persona, profile_name)
        expected_variants = {
            (family, entry["variant"]): (
                entry["count"],
                entry["gate_role"],
                entry["expected_disposition"],
            )
            for family, entries in spec.format_variant_counts(persona, profile_name).items()
            for entry in entries
        }
        expected_scopes = spec.scope_file_counts(persona, profile_name)
        expected_minima = spec.scope_contributor_file_minima(persona, profile_name)
        expected_chunks = spec.scope_contributor_chunk_targets(persona, profile_name)
    except (KeyError, ZeroDivisionError, ValueError) as error:
        raise AllocationError(str(error)) from error
    contributor_inventory = sum(
        values[0]
        for values in expected_variants.values()
        if values[1] == "contract_contributor"
    )
    try:
        expected_contributor_targets = _contributor_file_targets(
            contributor_inventory,
            spec.scope_specs(persona),
            expected_scopes,
            expected_minima,
            expected_chunks,
        )
    except AllocationError as error:
        raise AllocationError(f"{persona['id']} {profile_name}: {error}") from error

    header = {
        "allocation_schema_version": ALLOCATION_SCHEMA_VERSION,
        "fixture_schema_version": spec.SCHEMA_VERSION,
        "fixture_id": spec.FIXTURE_ID,
        "persona_id": persona["id"],
        "profile": profile_name,
        "total_files": expected_total,
        "format_totals": expected_families,
        "scope_totals": expected_scopes,
        "scope_contributor_file_minima": expected_minima,
        "scope_contributor_file_targets": expected_contributor_targets,
        "scope_contributor_chunk_targets": expected_chunks,
    }
    for key, expected in header.items():
        if plan.get(key) != expected:
            raise AllocationError(f"allocation header mismatch: {key}")

    declared_variant_rows = plan.get("variant_totals", ())
    declared_variants = {
        (row.get("family"), row.get("variant")): (
            row.get("count"),
            row.get("gate_role"),
            row.get("expected_disposition"),
        )
        for row in declared_variant_rows
    }
    if (
        len(declared_variant_rows) != len(expected_variants)
        or declared_variants != expected_variants
    ):
        raise AllocationError("variant totals differ from the specification")

    path_by_scope = {
        scope["scope_key"]: scope["relative_path"] for scope in spec.scope_specs(persona)
    }
    variant_counts = {key: 0 for key in expected_variants}
    family_counts = {family: 0 for family in spec.FORMAT_KEYS}
    scope_counts = {scope_key: 0 for scope_key in expected_scopes}
    scope_contributors = {scope_key: 0 for scope_key in expected_scopes}
    seen_cells = set()
    actual_cell_counts = {}
    affinity_total = 0
    for assignment in plan.get("assignments", ()):
        scope_key = assignment.get("scope_key")
        family = assignment.get("family")
        variant = assignment.get("variant")
        cell = (scope_key, family, variant)
        if cell in seen_cells:
            raise AllocationError(f"duplicate allocation cell: {cell}")
        seen_cells.add(cell)
        if scope_key not in expected_scopes or (family, variant) not in expected_variants:
            raise AllocationError(f"unknown allocation cell: {cell}")
        count = assignment.get("count")
        if not isinstance(count, int) or count <= 0:
            raise AllocationError(f"allocation count must be a positive integer: {cell}")
        actual_cell_counts[cell] = count
        _, gate_role, disposition = expected_variants[(family, variant)]
        relative_path = path_by_scope[scope_key]
        affinity = route_affinity(family, relative_path)
        hints = list(matched_route_hints(family, relative_path))
        expected_assignment = {
            "relative_path": relative_path,
            "gate_role": gate_role,
            "expected_disposition": disposition,
            "route_affinity": affinity,
            "matched_route_hints": hints,
        }
        for key, expected in expected_assignment.items():
            if assignment.get(key) != expected:
                raise AllocationError(f"allocation metadata mismatch for {cell}: {key}")
        variant_counts[(family, variant)] += count
        family_counts[family] += count
        scope_counts[scope_key] += count
        affinity_total += count * affinity
        if gate_role == "contract_contributor":
            scope_contributors[scope_key] += count

    expected_variant_counts = {key: value[0] for key, value in expected_variants.items()}
    if variant_counts != expected_variant_counts:
        raise AllocationError("variant row marginals do not match")
    if family_counts != expected_families:
        raise AllocationError("format-family row marginals do not match")
    if scope_counts != expected_scopes:
        raise AllocationError("scope column marginals do not match")

    # Marginals alone do not identify the frozen route: a caller could swap
    # equal counts between two scopes, update the declared score, and still
    # pass every row/column check.  Recompute the deterministic min-cost
    # transport and require its exact non-zero cells so an approved JSON plan
    # cannot silently weaken the declared format-to-scope affinity.
    canonical_rows = _variant_rows(persona, profile_name)
    canonical_scopes = spec.scope_specs(persona)
    canonical_slots = _scope_slots(
        canonical_scopes, expected_scopes, expected_contributor_targets
    )
    canonical_matrix = _minimum_cost_allocation(
        canonical_rows, canonical_scopes, canonical_slots
    )
    canonical_cell_counts = {
        (
            canonical_scopes[scope_index]["scope_key"],
            row["family"],
            row["variant"],
        ): count
        for row_index, row in enumerate(canonical_rows)
        for scope_index, count in enumerate(canonical_matrix[row_index])
        if count
    }
    if actual_cell_counts != canonical_cell_counts:
        raise AllocationError("allocation cells differ from the canonical min-cost route")
    if affinity_total != plan.get("routing_affinity_total"):
        raise AllocationError("routing affinity total does not match")

    declared_scope_values = plan.get("scope_allocations", ())
    declared_scope_rows = {row.get("scope_key"): row for row in declared_scope_values}
    if (
        len(declared_scope_values) != len(expected_scopes)
        or set(declared_scope_rows) != set(expected_scopes)
    ):
        raise AllocationError("scope allocation rows do not match")
    for scope_key, expected_count in expected_scopes.items():
        row = declared_scope_rows[scope_key]
        expected_format_counts = {family: 0 for family in spec.FORMAT_KEYS}
        for assignment in plan["assignments"]:
            if assignment["scope_key"] == scope_key:
                expected_format_counts[assignment["family"]] += assignment["count"]
        expected_scope_row = {
            "scope_key": scope_key,
            "kind": next(
                scope["kind"] for scope in spec.scope_specs(persona)
                if scope["scope_key"] == scope_key
            ),
            "relative_path": path_by_scope[scope_key],
            "file_count": expected_count,
            "contributor_file_minimum": expected_minima[scope_key],
            "contributor_files": scope_contributors[scope_key],
            "contributor_chunk_target": expected_chunks[scope_key],
            "contributor_chunk_capacity": (
                scope_contributors[scope_key] * spec.MAX_CONTRIBUTOR_CHUNKS_PER_FILE
            ),
            "format_counts": expected_format_counts,
        }
        if row != expected_scope_row:
            raise AllocationError(f"scope allocation summary mismatch: {scope_key}")
        if expected_count >= spec.MAX_DIRECT_FILES_PER_SCOPE:
            raise AllocationError(f"scope direct-file headroom violated: {scope_key}")
        if scope_contributors[scope_key] < expected_minima[scope_key]:
            raise AllocationError(f"scope contributor minimum violated: {scope_key}")
        if scope_contributors[scope_key] != expected_contributor_targets[scope_key]:
            raise AllocationError(f"scope contributor target violated: {scope_key}")
        if scope_contributors[scope_key] > expected_chunks[scope_key]:
            raise AllocationError(f"scope contributor one-chunk upper bound violated: {scope_key}")
        if (
            scope_contributors[scope_key] * spec.MAX_CONTRIBUTOR_CHUNKS_PER_FILE
            < expected_chunks[scope_key]
        ):
            raise AllocationError(f"scope contributor chunk headroom violated: {scope_key}")
    return True
