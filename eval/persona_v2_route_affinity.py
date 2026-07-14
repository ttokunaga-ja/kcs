"""Canonical non-authorizing candidate route-affinity matrix for persona-PC v2.

The generic solver policy defines ``R[persona,variant,scope]`` as a soft
physical-placement preference.  This sidecar materializes the exact 541
full-active persona/variant rows and their 10,820 integer scores.  The score
vectors are literal authored candidate data; construction never consults the
v1 hint, a hash, runtime order, file-count marginals, or topology load units.

Score zero means only "no specific affinity".  It is not an eligibility ban:
future source intents define hard scope eligibility separately.  The matrix
has not received the required independent human review, so it grants no G0,
solver, source-plan, filesystem-write, or history authority.
"""

from __future__ import annotations

import copy
from collections import Counter, defaultdict

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_input_bindings as input_bindings
    from . import persona_v2_joint_solver_policy as solver_policy
    from .persona_v2_route_affinity_data import CANDIDATE_ROUTE_SCORE_ROWS
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_input_bindings as input_bindings
    import persona_v2_joint_solver_policy as solver_policy
    from persona_v2_route_affinity_data import CANDIDATE_ROUTE_SCORE_ROWS


ARTIFACT_SCHEMA = "kcs.persona.pc-route-affinity/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-route-affinity-matrix"
COMPLETION_SCOPE = (
    "complete-candidate-route-matrix-only-not-reviewed-not-solver-executable-"
    "not-g0-root"
)
MAX_ROUTE_AFFINITY_BYTES = 128 * 1024
SCORES_PER_ROW = 20
SCORE_MINIMUM = 0
SCORE_MAXIMUM = 4
MAX_MAXIMUM_SCORE_SCOPES = 8
EXACT_GLOBAL_VARIANT_IDENTITIES = 71
EXACT_DECLARED_PERSONA_VARIANT_ROWS = 566
EXACT_FULL_ACTIVE_ROWS = 541
EXACT_DECLARED_HARD_ZERO_ROWS = 25
EXACT_OUT_OF_DOMAIN_PERSONA_VARIANT_PAIRS = 854
EXACT_ROUTE_SCORE_CELLS = 10_820
PRIMARY_SCOPE_COUNT = 12

SCORE_ZERO_SEMANTICS = "soft-no-specific-affinity-never-hard-eligibility-ban"

TOP_LEVEL_FIELD_ORDER = (
    "artifact_kind",
    "artifact_schema",
    "artifact_schema_version",
    "authority",
    "completion_scope",
    "envelope_contract_sha256",
    "fixture_id",
    "fixture_schema_version",
    "g0_contract_frozen",
    "joint_problem_sha256",
    "joint_solver_policy_sha256",
    "route_matrix_complete",
    "rows",
    "topology_contract_sha256",
)
TOP_LEVEL_FIELDS = frozenset(TOP_LEVEL_FIELD_ORDER)
ROW_FIELD_ORDER = (
    "persona_id",
    "family",
    "variant_id",
    "scores_by_scope_ordinal",
)
ROW_FIELDS = frozenset(ROW_FIELD_ORDER)
AUTHORITY_FIELD_ORDER = (
    "authorizes_g0_freeze",
    "authorizes_solver_execution",
    "authorizes_source_plan",
    "authorizes_write_or_history",
)
AUTHORITY_FIELDS = frozenset(AUTHORITY_FIELD_ORDER)


class PersonaV2RouteAffinityError(ValueError):
    """Raised when the candidate route matrix differs from the exact contract."""


def _envelope_declared_rows():
    rows = []
    for persona_id in envelope.PERSONA_IDS:
        counts = envelope.variant_counts(persona_id, "full")
        for family in envelope.FORMAT_KEYS:
            for row in sorted(
                counts[family], key=lambda item: item["variant_id"].encode("ascii")
            ):
                rows.append({
                    "family": family,
                    "full_count": row["count"],
                    "persona_id": persona_id,
                    "variant_id": row["variant_id"],
                })
    if len(envelope.VARIANT_CATALOG) != EXACT_GLOBAL_VARIANT_IDENTITIES:
        raise PersonaV2RouteAffinityError("global variant identity shape drifted")
    if len(rows) != EXACT_DECLARED_PERSONA_VARIANT_ROWS:
        raise PersonaV2RouteAffinityError("declared persona/variant shape drifted")
    return rows


def _require_policy_artifact_contract(route_future_input):
    if type(route_future_input) is not dict:
        raise PersonaV2RouteAffinityError("policy route input must be an exact object")
    contract = route_future_input.get("artifact_contract")
    if type(contract) is not dict:
        raise PersonaV2RouteAffinityError("policy route artifact contract is absent")
    expected_identity = {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "completion_scope": COMPLETION_SCOPE,
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
    }
    if any(contract.get(key) != value for key, value in expected_identity.items()):
        raise PersonaV2RouteAffinityError("policy route artifact identity drifted")
    expected_contract = {
        "authority_exact_false_fields": list(AUTHORITY_FIELD_ORDER),
        "missing_or_unknown_fields_allowed": False,
        "row_fields": list(ROW_FIELD_ORDER),
        "rows_container": "rows-exact-list-of-541",
        "top_level_fields": list(TOP_LEVEL_FIELD_ORDER),
        "top_level_required_values": {
            "g0_contract_frozen": False,
            "route_matrix_complete": True,
        },
    }
    if any(contract.get(key) != value for key, value in expected_contract.items()):
        raise PersonaV2RouteAffinityError("policy route artifact schema drifted")
    limits = contract.get("canonical_limits")
    if type(limits) is not dict or limits.get("max_route_affinity_bytes") != (
        MAX_ROUTE_AFFINITY_BYTES
    ):
        raise PersonaV2RouteAffinityError("policy route artifact byte cap drifted")
    if set(contract.get("exact_back_binding_rules", {})) != {
        "envelope_contract_sha256",
        "joint_problem_sha256",
        "joint_solver_policy_sha256",
        "topology_contract_sha256",
    }:
        raise PersonaV2RouteAffinityError("policy route back-binding schema drifted")
    expected_future = {
        "actual_matrix_present": False,
        "cell_max": SCORE_MAXIMUM,
        "cell_min": SCORE_MINIMUM,
        "cell_type": "exact-int-not-bool",
        "matrix_notation": "R[persona_id,variant_id,scope_ordinal]",
        "required_review_receipt_present": False,
        "route_affinity_input_schema_defined": True,
    }
    if any(
        route_future_input.get(key) != value
        for key, value in expected_future.items()
    ):
        raise PersonaV2RouteAffinityError("policy route input semantics drifted")
    shape = route_future_input.get("shape")
    if shape != {
        "cell_count": EXACT_ROUTE_SCORE_CELLS,
        "full_active_persona_variant_rows": EXACT_FULL_ACTIVE_ROWS,
        "scopes_per_row": SCORES_PER_ROW,
    }:
        raise PersonaV2RouteAffinityError("policy route input shape drifted")


def _validated_policy_axis(policy_value=None):
    if policy_value is None:
        policy_value = solver_policy.build_joint_solver_policy()
    try:
        solver_policy.validate_joint_solver_policy(policy_value)
    except solver_policy.PersonaV2JointSolverPolicyError as error:
        raise PersonaV2RouteAffinityError(
            f"bound solver policy is invalid: {error}"
        ) from None
    try:
        policy = policy_value["policy"]
        axes = policy["axes"]
        persona_axes = axes["persona_variant_axes"]
        route_future_input = policy["route_affinity_future_input"]
    except (KeyError, TypeError):
        raise PersonaV2RouteAffinityError(
            "bound solver policy route axes are absent"
        ) from None
    _require_policy_artifact_contract(route_future_input)
    if axes.get("persona_order") != list(envelope.PERSONA_IDS):
        raise PersonaV2RouteAffinityError("policy persona axis drifted")
    if axes.get("family_order") != list(envelope.FORMAT_KEYS):
        raise PersonaV2RouteAffinityError("policy family axis drifted")
    if type(persona_axes) is not list or len(persona_axes) != len(
        envelope.PERSONA_IDS
    ):
        raise PersonaV2RouteAffinityError("policy persona/variant axes drifted")

    rows = []
    for expected_persona, persona_axis in zip(envelope.PERSONA_IDS, persona_axes):
        if type(persona_axis) is not dict or persona_axis.get("persona_id") != (
            expected_persona
        ):
            raise PersonaV2RouteAffinityError("policy persona/variant axis order drifted")
        variant_axis = persona_axis.get("variant_axis")
        if type(variant_axis) is not list:
            raise PersonaV2RouteAffinityError("policy variant axis must be a list")
        if persona_axis.get("declared_variant_count") != len(variant_axis):
            raise PersonaV2RouteAffinityError("policy declared variant count drifted")
        active_count = 0
        for row in variant_axis:
            if type(row) is not dict or set(row) != {
                "family",
                "full_active",
                "gate_role",
                "variant_id",
            }:
                raise PersonaV2RouteAffinityError("policy variant axis row drifted")
            if (
                type(row["family"]) is not str
                or type(row["variant_id"]) is not str
                or type(row["full_active"]) is not bool
            ):
                raise PersonaV2RouteAffinityError("policy variant axis types drifted")
            active_count += row["full_active"]
            rows.append({
                "family": row["family"],
                "full_active": row["full_active"],
                "persona_id": expected_persona,
                "variant_id": row["variant_id"],
            })
        if persona_axis.get("full_active_variant_count") != active_count:
            raise PersonaV2RouteAffinityError("policy active variant count drifted")
    if (
        len(rows) != EXACT_DECLARED_PERSONA_VARIANT_ROWS
        or sum(row["full_active"] for row in rows) != EXACT_FULL_ACTIVE_ROWS
        or sum(not row["full_active"] for row in rows)
        != EXACT_DECLARED_HARD_ZERO_ROWS
    ):
        raise PersonaV2RouteAffinityError("policy route projection shape drifted")
    return rows


def _require_policy_axis_match(envelope_rows, policy_rows):
    expected = [
        (
            row["persona_id"],
            row["family"],
            row["variant_id"],
            row["full_count"] > 0,
        )
        for row in envelope_rows
    ]
    actual = [
        (
            row["persona_id"],
            row["family"],
            row["variant_id"],
            row["full_active"],
        )
        for row in policy_rows
    ]
    if actual != expected:
        raise PersonaV2RouteAffinityError(
            "validated policy route axis differs from the envelope projection"
        )


def _declared_rows():
    rows = _envelope_declared_rows()
    policy_rows = _validated_policy_axis()
    _require_policy_axis_match(rows, policy_rows)
    active = [row for row in rows if row["full_count"] > 0]
    hard_zero = [row for row in rows if row["full_count"] == 0]
    if (
        len(active) != EXACT_FULL_ACTIVE_ROWS
        or len(hard_zero) != EXACT_DECLARED_HARD_ZERO_ROWS
    ):
        raise PersonaV2RouteAffinityError("active versus hard-zero shape drifted")
    out_of_domain = (
        len(envelope.PERSONA_IDS) * len(envelope.VARIANT_CATALOG) - len(rows)
    )
    if out_of_domain != EXACT_OUT_OF_DOMAIN_PERSONA_VARIANT_PAIRS:
        raise PersonaV2RouteAffinityError("out-of-domain route shape drifted")
    return rows, active, hard_zero


def _literal_vectors_by_identity(active_rows):
    if type(CANDIDATE_ROUTE_SCORE_ROWS) is not tuple:
        raise PersonaV2RouteAffinityError("candidate score data must be an exact tuple")
    expected_personas = tuple(envelope.PERSONA_IDS)
    actual_personas = tuple(row[0] for row in CANDIDATE_ROUTE_SCORE_ROWS)
    if actual_personas != expected_personas:
        raise PersonaV2RouteAffinityError("candidate persona order drifted")

    expected_by_persona = defaultdict(list)
    for row in active_rows:
        expected_by_persona[row["persona_id"]].append(row["variant_id"])

    result = {}
    for persona_row in CANDIDATE_ROUTE_SCORE_ROWS:
        if type(persona_row) is not tuple or len(persona_row) != 2:
            raise PersonaV2RouteAffinityError("candidate persona row must have two fields")
        persona_id, variant_rows = persona_row
        if type(persona_id) is not str or type(variant_rows) is not tuple:
            raise PersonaV2RouteAffinityError("candidate persona row types are invalid")
        variants = []
        for variant_row in variant_rows:
            if type(variant_row) is not tuple or len(variant_row) != 2:
                raise PersonaV2RouteAffinityError(
                    "candidate variant row must have two fields"
                )
            variant_id, encoded_scores = variant_row
            if type(variant_id) is not str or type(encoded_scores) is not str:
                raise PersonaV2RouteAffinityError("candidate variant row types are invalid")
            if len(encoded_scores) != SCORES_PER_ROW or any(
                character not in "01234" for character in encoded_scores
            ):
                raise PersonaV2RouteAffinityError(
                    f"invalid score vector: {persona_id}/{variant_id}"
                )
            identity = (persona_id, variant_id)
            if identity in result:
                raise PersonaV2RouteAffinityError(
                    f"duplicate candidate route identity: {identity!r}"
                )
            variants.append(variant_id)
            result[identity] = [int(character) for character in encoded_scores]
        if variants != expected_by_persona[persona_id]:
            raise PersonaV2RouteAffinityError(
                f"candidate variant identity/order drifted: {persona_id}"
            )
    if len(result) != EXACT_FULL_ACTIVE_ROWS:
        raise PersonaV2RouteAffinityError("candidate route row count drifted")
    return result


def _diagnostics(rows, *, declared_rows, hard_zero_rows):
    score_histogram = Counter()
    row_maximum_not_four = []
    maximum_scope_count_out_of_bounds = []
    secondary_only_maximum_rows = []
    vectors_by_variant = defaultdict(lambda: defaultdict(list))
    rows_by_persona = defaultdict(list)

    for row in rows:
        identity = f"{row['persona_id']}+{row['variant_id']}"
        scores = row["scores_by_scope_ordinal"]
        score_histogram.update(scores)
        maximum = max(scores)
        maximum_ordinals = [
            ordinal for ordinal, score in enumerate(scores, 1) if score == maximum
        ]
        if maximum != SCORE_MAXIMUM:
            row_maximum_not_four.append(identity)
        if not 1 <= len(maximum_ordinals) <= MAX_MAXIMUM_SCORE_SCOPES:
            maximum_scope_count_out_of_bounds.append(identity)
        if all(ordinal > PRIMARY_SCOPE_COUNT for ordinal in maximum_ordinals):
            secondary_only_maximum_rows.append(identity)
        vectors_by_variant[row["variant_id"]][tuple(scores)].append(row["persona_id"])
        rows_by_persona[row["persona_id"]].append(row)

    clones = []
    for variant_id in sorted(vectors_by_variant, key=lambda value: value.encode("ascii")):
        for personas in vectors_by_variant[variant_id].values():
            if len(personas) > 1:
                clones.append({
                    "persona_ids": personas,
                    "variant_id": variant_id,
                })

    uncovered = []
    persona_scope_minimums = []
    for persona_id in envelope.PERSONA_IDS:
        persona_rows = rows_by_persona[persona_id]
        scope_maxima = [
            max(row["scores_by_scope_ordinal"][scope_index] for row in persona_rows)
            for scope_index in range(SCORES_PER_ROW)
        ]
        persona_scope_minimums.append({
            "minimum_of_scope_maxima": min(scope_maxima),
            "persona_id": persona_id,
        })
        uncovered.extend(
            {
                "persona_id": persona_id,
                "scope_ordinal": scope_index + 1,
            }
            for scope_index, maximum in enumerate(scope_maxima)
            if maximum < 2
        )

    return {
        "cross_person_same_variant_vector_clones": clones,
        "declared_hard_zero_rows": len(hard_zero_rows),
        "declared_persona_variant_rows": len(declared_rows),
        "full_active_rows": len(rows),
        "independent_review_complete": False,
        "maximum_scope_count_out_of_bounds": maximum_scope_count_out_of_bounds,
        "out_of_domain_persona_variant_pairs": (
            len(envelope.PERSONA_IDS) * len(envelope.VARIANT_CATALOG)
            - len(declared_rows)
        ),
        "persona_scope_minimums": persona_scope_minimums,
        "review_receipt_present": False,
        "route_score_cells": sum(
            len(row["scores_by_scope_ordinal"]) for row in rows
        ),
        "row_maximum_not_four": row_maximum_not_four,
        "score_histogram": {
            str(score): score_histogram[score]
            for score in range(SCORE_MINIMUM, SCORE_MAXIMUM + 1)
        },
        "score_zero_semantics": SCORE_ZERO_SEMANTICS,
        "secondary_only_maximum_rows": secondary_only_maximum_rows,
        "uncovered_persona_scopes_below_score_two": uncovered,
    }


def _build_rows():
    declared, active, hard_zero = _declared_rows()
    vectors = _literal_vectors_by_identity(active)
    rows = []
    for expected in active:
        scores = vectors[(expected["persona_id"], expected["variant_id"])]
        if len(scores) != SCORES_PER_ROW or any(
            type(score) is not int
            or score < SCORE_MINIMUM
            or score > SCORE_MAXIMUM
            for score in scores
        ):
            raise PersonaV2RouteAffinityError("route scores differ from exact domain")
        rows.append({
            "family": expected["family"],
            "persona_id": expected["persona_id"],
            "scores_by_scope_ordinal": scores,
            "variant_id": expected["variant_id"],
        })
    diagnostics = _diagnostics(
        rows,
        declared_rows=declared,
        hard_zero_rows=hard_zero,
    )
    required_empty = (
        "cross_person_same_variant_vector_clones",
        "maximum_scope_count_out_of_bounds",
        "row_maximum_not_four",
        "secondary_only_maximum_rows",
        "uncovered_persona_scopes_below_score_two",
    )
    if any(diagnostics[key] for key in required_empty):
        raise PersonaV2RouteAffinityError(
            "candidate route data violates a machine-checkable review precursor"
        )
    if diagnostics["route_score_cells"] != EXACT_ROUTE_SCORE_CELLS:
        raise PersonaV2RouteAffinityError("route score cell count drifted")
    return rows, diagnostics


def _canonical_route_affinity_value():
    rows, _ = _build_rows()
    bindings = {
        row["name"]: row for row in input_bindings.build_upstream_bindings()
    }
    if set(bindings) != set(input_bindings.UPSTREAM_ORDER):
        raise PersonaV2RouteAffinityError("upstream route bindings drifted")
    value = {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {
            "authorizes_g0_freeze": False,
            "authorizes_solver_execution": False,
            "authorizes_source_plan": False,
            "authorizes_write_or_history": False,
        },
        "completion_scope": COMPLETION_SCOPE,
        "envelope_contract_sha256": bindings["envelope"]["sha256"],
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "joint_problem_sha256": bindings["joint-problem"]["sha256"],
        "joint_solver_policy_sha256": bindings["joint-solver-policy"]["sha256"],
        "route_matrix_complete": True,
        "rows": rows,
        "topology_contract_sha256": bindings["topology"]["sha256"],
    }
    if set(value) != TOP_LEVEL_FIELDS or set(value["authority"]) != AUTHORITY_FIELDS:
        raise PersonaV2RouteAffinityError("route artifact schema drifted")
    if any(value["authority"].values()):
        raise PersonaV2RouteAffinityError("route artifact authority must remain false")
    if any(set(row) != ROW_FIELDS for row in rows):
        raise PersonaV2RouteAffinityError("route row schema drifted")
    return value


def build_route_affinity():
    """Return a detached exact candidate matrix with no review or authority."""

    return copy.deepcopy(_canonical_route_affinity_value())


def candidate_review_diagnostics():
    """Return deterministic machine checks; never an independent review receipt."""

    _, diagnostics = _build_rows()
    return copy.deepcopy(diagnostics)


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 route-affinity matrix",
            max_bytes=MAX_ROUTE_AFFINITY_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RouteAffinityError(str(error)) from None


def validate_route_affinity(value):
    try:
        return artifact_common.validate_exact_regeneration(
            value,
            builder=build_route_affinity,
            label="persona v2 route-affinity matrix",
            max_bytes=MAX_ROUTE_AFFINITY_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RouteAffinityError(str(error)) from None


def route_affinity_sha256(value=None):
    try:
        return artifact_common.canonical_sha256(
            value,
            builder=build_route_affinity,
            label="persona v2 route-affinity matrix",
            max_bytes=MAX_ROUTE_AFFINITY_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RouteAffinityError(str(error)) from None


def require_independently_reviewed_route_affinity():
    raise PersonaV2RouteAffinityError(
        "candidate matrix is complete, but the independent human-review receipt "
        "is absent and no solver, source-plan, G0, write, or history authority exists"
    )
