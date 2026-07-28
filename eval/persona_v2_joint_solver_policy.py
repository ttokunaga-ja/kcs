"""Canonical, non-authorizing aggregate solver semantics for persona-PC v2.

This sidecar binds the current envelope, topology, and joint-allocation problem
in one direction and defines the deterministic *generic aggregate core* of a
future exact solver.  It intentionally omits the route-affinity matrix,
realism/duplicate-cluster overlay, source recipe, allocation solution, and any
certificate.  Those omissions make the exact objective unevaluable and the
policy unfit for execution or G0 authority.

The variables described here are aggregate integer cells, not source rows.
Passing validation only proves byte-for-byte agreement with these semantics;
it never proves feasibility, optimality, pilot source identity, or permission
to write a filesystem or history root.
"""

import copy
import hashlib
import json
import math
import unicodedata

from eval import persona_v2_contract as envelope
from eval import persona_v2_joint_problem as joint_problem
from eval import persona_v2_topology as topology


ARTIFACT_SCHEMA = "kio.persona.pc-joint-solver-policy/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-joint-solver-policy"
COMPLETION_SCOPE = (
    "generic-aggregate-core-exact-semantics-only-not-complete-policy-not-"
    "solution-not-certificate-not-g0-root"
)

MAX_POLICY_BYTES = 512 * 1024
MAX_ROUTE_AFFINITY_BYTES = 128 * 1024
MAX_CANONICAL_DEPTH = 64
MAX_CANONICAL_STRING_BYTES = 4_096
MAX_INTEGER_BITS = 127
MAX_INTEGER_MAGNITUDE = 2**MAX_INTEGER_BITS - 1

MAX_EXACT_EXPANDED_NODES_PER_PERSONA_PAIR = 2_000_000
MAX_RETAINED_OR_TRANSPOSITION_STATES_PER_PERSONA_PAIR = 262_144
MAX_EXACT_FLOW_AUGMENTATIONS_PER_PERSONA_PAIR = 2_000_000
MAX_SOLUTION_OR_EXECUTION_RECEIPT_BYTES_PER_PERSONA = 8 * 2**20
MAX_SOURCE_PLAN_BYTES_PER_PERSONA = 16 * 2**20

PROFILES = ("pilot", "full")
SOURCE_ORIGINS = ("pilot", "full-minus-pilot")
REQUIRED_SCOPE_HISTORY_COHORTS = envelope.REQUIRED_SCOPE_HISTORY_COHORTS
QUOTA_WIDTH_LCM = math.lcm(
    *(
        maximum - minimum + 1
        for minimum, maximum in envelope.DENSITY_BUCKET_BOUNDS.values()
    )
)


class PersonaV2JointSolverPolicyError(ValueError):
    """Raised when the v2 solver-policy sidecar is invalid or overclaimed."""


def _contains_key(value, rejected_keys):
    if type(value) is dict:
        if any(key in rejected_keys for key in value):
            return True
        return any(_contains_key(item, rejected_keys) for item in value.values())
    if type(value) is list:
        return any(_contains_key(item, rejected_keys) for item in value)
    return False


def _validated_bound_inputs():
    envelope_value = envelope.build_envelope_contract()
    topology_value = topology.build_topology_contract()
    problem_value = joint_problem.build_joint_problem()

    envelope.validate_envelope_contract(envelope_value)
    topology.validate_topology_contract(topology_value)
    joint_problem.validate_joint_problem(problem_value)

    envelope_sha = envelope.envelope_contract_sha256(envelope_value)
    topology_sha = topology.topology_contract_sha256(topology_value)
    problem_sha = joint_problem.joint_problem_sha256(problem_value)
    envelope_bytes = len(envelope.canonical_json_bytes(envelope_value))
    topology_bytes = len(topology.canonical_json_bytes(topology_value))
    problem_bytes = len(joint_problem.canonical_json_bytes(problem_value))
    if topology_value["envelope_contract_sha256"] != envelope_sha:
        raise PersonaV2JointSolverPolicyError(
            "bound topology does not reference the current envelope"
        )
    if problem_value["envelope_contract_sha256"] != envelope_sha:
        raise PersonaV2JointSolverPolicyError(
            "bound joint problem does not reference the current envelope"
        )
    if problem_value["topology_contract_sha256"] != topology_sha:
        raise PersonaV2JointSolverPolicyError(
            "bound joint problem does not reference the current topology"
        )
    if problem_value["proof_status"]["solver_policy_bound"] is not False:
        raise PersonaV2JointSolverPolicyError(
            "upstream joint problem must retain solver_policy_bound=false"
        )
    if (
        envelope_value["g0_contract_frozen"] is not False
        or topology_value["g0_contract_frozen"] is not False
        or problem_value["g0_contract_frozen"] is not False
    ):
        raise PersonaV2JointSolverPolicyError(
            "every bound upstream artifact must remain non-G0"
        )
    for artifact in (envelope_value, topology_value, problem_value):
        authority = artifact["authority"]
        if not authority or any(
            type(flag) is not bool or flag is not False
            for flag in authority.values()
        ):
            raise PersonaV2JointSolverPolicyError(
                "every bound upstream authority flag must be exact false"
            )

    # A policy hash in an upstream artifact would make the intended one-way
    # envelope -> topology -> problem -> policy graph cyclic.
    if _contains_key(
        [envelope_value, topology_value, problem_value],
        {
            "joint_solver_policy_sha256",
            "solver_policy_contract_sha256",
        },
    ):
        raise PersonaV2JointSolverPolicyError(
            "upstream artifact contains a forbidden forward policy hash"
        )
    return (
        envelope_value,
        topology_value,
        problem_value,
        envelope_sha,
        topology_sha,
        problem_sha,
        envelope_bytes,
        topology_bytes,
        problem_bytes,
    )


def _ascii_variant_id(value):
    if type(value) is not str or not value:
        raise PersonaV2JointSolverPolicyError(
            "variant_id must be a non-empty ASCII string"
        )
    try:
        encoded = value.encode("ascii", "strict")
    except UnicodeEncodeError:
        raise PersonaV2JointSolverPolicyError(
            "variant_id must be a non-empty ASCII string"
        ) from None
    if len(encoded) > 128:
        raise PersonaV2JointSolverPolicyError(
            "variant_id exceeds the solver-axis byte bound"
        )
    return value


def _derived_axes(problem_value):
    declared_rows = 0
    full_active_rows = 0
    contributor_rows = 0
    per_persona = []
    for persona in problem_value["personas"]:
        profiles = {row["profile"]: row for row in persona["profiles"]}
        if tuple(profiles) != PROFILES:
            raise PersonaV2JointSolverPolicyError(
                f"profile order differs for {persona['persona_id']}"
            )
        pilot = profiles["pilot"]
        full = profiles["full"]
        pilot_families = {
            row["family"]: row for row in pilot["family_variant_marginals"]
        }
        full_families = {
            row["family"]: row for row in full["family_variant_marginals"]
        }
        if tuple(pilot_families) != envelope.FORMAT_KEYS or tuple(
            full_families
        ) != envelope.FORMAT_KEYS:
            raise PersonaV2JointSolverPolicyError(
                f"family order differs for {persona['persona_id']}"
            )

        variants = []
        seen = set()
        for family in envelope.FORMAT_KEYS:
            pilot_variants = {
                row["variant_id"]: row
                for row in pilot_families[family]["variants"]
            }
            full_variants = {
                row["variant_id"]: row
                for row in full_families[family]["variants"]
            }
            if set(pilot_variants) != set(full_variants):
                raise PersonaV2JointSolverPolicyError(
                    f"pilot/full variant identity differs for "
                    f"{persona['persona_id']}/{family}"
                )
            for variant_id in sorted(
                full_variants,
                key=lambda item: _ascii_variant_id(item).encode("ascii"),
            ):
                if variant_id in seen:
                    raise PersonaV2JointSolverPolicyError(
                        f"variant_id is not persona-unique: "
                        f"{persona['persona_id']}/{variant_id}"
                    )
                seen.add(variant_id)
                pilot_row = pilot_variants[variant_id]
                full_row = full_variants[variant_id]
                if pilot_row["gate_role"] != full_row["gate_role"]:
                    raise PersonaV2JointSolverPolicyError(
                        f"pilot/full gate role differs for "
                        f"{persona['persona_id']}/{variant_id}"
                    )
                variants.append({
                    "family": family,
                    "full_active": full_row["file_count"] > 0,
                    "gate_role": full_row["gate_role"],
                    "variant_id": variant_id,
                })
                declared_rows += 1
                full_active_rows += int(full_row["file_count"] > 0)
                contributor_rows += int(
                    full_row["gate_role"] == "contract_contributor"
                )
        per_persona.append({
            "declared_variant_count": len(variants),
            "full_active_variant_count": sum(
                int(row["full_active"]) for row in variants
            ),
            "persona_id": persona["persona_id"],
            "variant_axis": variants,
        })

    if tuple(row["persona_id"] for row in per_persona) != envelope.PERSONA_IDS:
        raise PersonaV2JointSolverPolicyError(
            "joint-problem persona order differs from the envelope"
        )
    valid_quota_count = sum(
        maximum - minimum + 1
        for minimum, maximum in envelope.DENSITY_BUCKET_BOUNDS.values()
    )
    scope_count = topology.SCOPES_PER_PERSONA
    history_count = len(envelope.HISTORY_COHORT_ORDER)
    dense_a_cells = declared_rows * scope_count
    route_cells = full_active_rows * scope_count
    dense_c_cells = (
        contributor_rows * scope_count * history_count * valid_quota_count
    )
    expected = {
        "contributor_persona_variant_rows": 116,
        "declared_persona_variant_rows": 566,
        "dense_a_cells_per_tensor": 11_320,
        "dense_a_plus_c_cells_per_tensor": 823_320,
        "dense_c_cells_per_tensor": 812_000,
        "full_active_persona_variant_rows": 541,
        "pilot_plus_residual_decision_a_cells": 22_640,
        "pilot_plus_residual_decision_a_plus_c_cells": 1_646_640,
        "pilot_plus_residual_decision_c_cells": 1_624_000,
        "route_matrix_cells": 10_820,
    }
    actual = {
        "contributor_persona_variant_rows": contributor_rows,
        "declared_persona_variant_rows": declared_rows,
        "dense_a_cells_per_tensor": dense_a_cells,
        "dense_a_plus_c_cells_per_tensor": dense_a_cells + dense_c_cells,
        "dense_c_cells_per_tensor": dense_c_cells,
        "full_active_persona_variant_rows": full_active_rows,
        "pilot_plus_residual_decision_a_cells": 2 * dense_a_cells,
        "pilot_plus_residual_decision_a_plus_c_cells": 2
        * (dense_a_cells + dense_c_cells),
        "pilot_plus_residual_decision_c_cells": 2 * dense_c_cells,
        "route_matrix_cells": route_cells,
    }
    if actual != expected:
        raise PersonaV2JointSolverPolicyError(
            f"derived solver axes differ from reviewed shape: {actual!r}"
        )
    return per_persona, actual


def _hard_constraints():
    return [
        {
            "constraint_id": "nonnegative-integral-A-cells",
            "formula": "A[i,o,v,s] in Z>=0",
            "quantified_axes": {
                "i": "persona",
                "o": "source_origin",
                "s": "scope",
                "v": "declared_variant[i]",
            },
            "relation": "membership-in-nonnegative-checked-integers",
            "tensor": "A",
        },
        {
            "constraint_id": "nonnegative-integral-C-cells",
            "formula": "C[i,o,v,s,b,h,q] in Z>=0",
            "quantified_axes": {
                "b": "density_bucket",
                "h": "history_cohort",
                "i": "persona",
                "o": "source_origin",
                "q": "valid_quota[b]",
                "s": "scope",
                "v": "contract_contributor_variant[i]",
            },
            "relation": "membership-in-nonnegative-checked-integers",
            "tensor": "C",
        },
        {
            "constraint_id": "exact-variant-physical-marginals",
            "formula": "for each i,o,v: sum_s A[i,o,v,s] = M[i,o,v]",
            "lhs": {"reduce_axis": "scope", "tensor": "A"},
            "quantified_axes": {
                "i": "persona",
                "o": "source_origin",
                "v": "declared_variant[i]",
            },
            "relation": "exact-equality",
            "rhs": "bound_variant_physical_marginal",
        },
        {
            "constraint_id": "exact-scope-physical-marginals",
            "formula": "for each i,o,s: sum_v A[i,o,v,s] = F[i,o,s]",
            "lhs": {"reduce_axis": "declared_variant[i]", "tensor": "A"},
            "quantified_axes": {
                "i": "persona",
                "o": "source_origin",
                "s": "scope",
            },
            "relation": "exact-equality",
            "rhs": "bound_scope_physical_marginal",
        },
        {
            "constraint_id": "contributor-refinement",
            "formula": (
                "for contributor v: A[i,o,v,s] = sum_b,h,q "
                "C[i,o,v,s,b,h,q]; for non-contributor v no C cell exists"
            ),
            "lhs": {"tensor": "A"},
            "quantified_axes": {
                "i": "persona",
                "o": "source_origin",
                "s": "scope",
                "v": "contract_contributor_variant[i]",
            },
            "relation": "exact-equality",
            "rhs": {
                "reduce_axes": ["density_bucket", "history_cohort", "valid_quota[b]"],
                "tensor": "C",
            },
        },
        {
            "constraint_id": "exact-density-source-marginals",
            "formula": "for each i,o,b: sum_v,s,h,q C[i,o,v,s,b,h,q] = D[i,o,b]",
            "lhs": {
                "reduce_axes": [
                    "contract_contributor_variant[i]",
                    "scope",
                    "history_cohort",
                    "valid_quota[b]",
                ],
                "tensor": "C",
            },
            "quantified_axes": {
                "b": "density_bucket",
                "i": "persona",
                "o": "source_origin",
            },
            "relation": "exact-equality",
            "rhs": "bound_density_source_marginal",
        },
        {
            "constraint_id": "exact-scope-chunk-marginals",
            "formula": "for each i,o,s: sum_v,b,h,q q*C[i,o,v,s,b,h,q] = t[i,o,s]",
            "lhs": {
                "coefficient_axis": "quota",
                "reduce_axes": [
                    "contract_contributor_variant[i]",
                    "density_bucket",
                    "history_cohort",
                    "valid_quota[b]",
                ],
                "tensor": "C",
            },
            "quantified_axes": {
                "i": "persona",
                "o": "source_origin",
                "s": "scope",
            },
            "relation": "exact-equality",
            "rhs": "bound_scope_chunk_marginal",
        },
        {
            "constraint_id": "exact-whole-source-cohort-chunk-marginals",
            "formula": "for each i,o,h: sum_v,s,b,q q*C[i,o,v,s,b,h,q] = H[i,o,h]",
            "lhs": {
                "coefficient_axis": "quota",
                "reduce_axes": [
                    "contract_contributor_variant[i]",
                    "scope",
                    "density_bucket",
                    "valid_quota[b]",
                ],
                "tensor": "C",
            },
            "quantified_axes": {
                "h": "history_cohort",
                "i": "persona",
                "o": "source_origin",
            },
            "relation": "exact-equality",
            "rhs": "bound_history_cohort_chunk_marginal",
        },
        {
            "constraint_id": "exact-contributor-source-total",
            "formula": (
                "for each i,phi: sum_v,s,b,h,q "
                "C_phi[i,phi,v,s,b,h,q] = N[i,phi]"
            ),
            "lhs": {
                "reduce_axes": [
                    "contract_contributor_variant[i]",
                    "scope",
                    "density_bucket",
                    "history_cohort",
                    "valid_quota[b]",
                ],
                "tensor": "C_phi-derived-evaluation-view",
            },
            "profile_context": ["pilot", "full"],
            "relation": "exact-equality",
            "rhs": "bound_contributor_source_total",
        },
        {
            "constraint_id": "exact-physical-total-identities",
            "formula": (
                "for each i,phi: sum_v M[i,phi,v] = "
                "sum_s F[i,phi,s] = physical_total[i,phi]"
            ),
            "profile_context": ["pilot", "full"],
            "relation": "exact-input-marginal-total-identity",
            "terms": [
                "sum_declared_variant_marginals",
                "sum_scope_physical_marginals",
                "bound_physical_total",
            ],
        },
        {
            "constraint_id": "exact-density-total-identity",
            "formula": "for each i,phi: sum_b D[i,phi,b] = N[i,phi]",
            "profile_context": ["pilot", "full"],
            "relation": "exact-input-marginal-total-identity",
            "terms": [
                "sum_density_source_marginals",
                "bound_contributor_source_total",
            ],
        },
        {
            "constraint_id": "exact-chunk-total-identities",
            "formula": (
                "for each i,phi: sum_s t[i,phi,s] = "
                "sum_h H[i,phi,h] = T[i,phi]"
            ),
            "profile_context": ["pilot", "full"],
            "relation": "exact-input-marginal-total-identity",
            "terms": [
                "sum_scope_chunk_marginals",
                "sum_history_cohort_chunk_marginals",
                "bound_contributor_chunk_total",
            ],
        },
        {
            "constraint_id": "required-cohort-scope-coverage",
            "formula": (
                "for phi in {pilot,full}, h in {P,X,Y,N}, each i,s: "
                "sum_v,b,q C_phi[i,phi,v,s,b,h,q] >= 1"
            ),
            "lhs": {
                "reduce_axes": [
                    "contract_contributor_variant[i]",
                    "density_bucket",
                    "valid_quota[b]",
                ],
                "tensor": "C_phi-derived-evaluation-view",
            },
            "quantified_axes": {
                "h": "required_scope_history_cohort",
                "i": "persona",
                "s": "scope",
                "phi": "coverage_profile_context",
            },
            "relation": "greater-than-or-equal",
            "rhs_integer": 1,
        },
        {
            "constraint_id": "quota-membership",
            "formula": "C[i,o,v,s,b,h,q] exists only when quota_min[b] <= q <= quota_max[b]",
            "cell_existence_predicate": {
                "maximum": "quota_max[b]",
                "minimum": "quota_min[b]",
                "subject": "q",
            },
            "relation": "inclusive-integer-range",
            "tensor": "C",
        },
        {
            "constraint_id": "coordinatewise-pilot-lock",
            "formula": (
                "A_full=A_pilot+deltaA and C_full=C_pilot+deltaC, with "
                "deltaA,deltaC in Z>=0; full is derived, not an independent variable"
            ),
            "derived_tensor_rules": [
                {
                    "derived": "A_full",
                    "operands": ["A_pilot", "deltaA_full-minus-pilot"],
                    "operator": "checked-coordinatewise-addition",
                },
                {
                    "derived": "C_full",
                    "operands": ["C_pilot", "deltaC_full-minus-pilot"],
                    "operator": "checked-coordinatewise-addition",
                },
            ],
            "relation": "exact-coordinatewise-identity",
        },
        {
            "constraint_id": "exact-full-aggregate-bound-marginals",
            "formula": (
                "pilot plus residual must equal every bound full variant, scope, "
                "density-source, scope-chunk, and cohort-chunk marginal"
            ),
            "marginal_sets": [
                "variant_physical",
                "scope_physical",
                "density_source",
                "scope_chunk",
                "history_cohort_chunk",
            ],
            "profile_context": "derived-full-aggregate",
            "relation": "exact-equality-to-bound-full-marginals",
        },
        {
            "constraint_id": "pilot-full-extension",
            "formula": (
                "a pilot candidate is admissible only after an exact witness "
                "deltaA,deltaC proves every full-aggregate hard constraint"
            ),
            "candidate": ["A_pilot", "C_pilot"],
            "quantifier": "exists",
            "relation": "admissible-if-and-only-if-exact-extension-witness-exists",
            "witness": [
                "nonnegative-deltaA_full-minus-pilot",
                "nonnegative-deltaC_full-minus-pilot",
            ],
        },
    ]


def _objective():
    component_order = [
        "pilot.L_scope",
        "pilot.L_density",
        "pilot.L_cohort_sources",
        "pilot.L_cohort_chunks",
        "pilot.L_quota",
        "pilot.route_loss",
        "pilot.Flat(A)",
        "pilot.Flat(C)",
        "full_aggregate.L_scope",
        "full_aggregate.L_density",
        "full_aggregate.L_cohort_sources",
        "full_aggregate.L_cohort_chunks",
        "full_aggregate.L_quota",
        "full_aggregate.route_loss",
        "residual.Flat(deltaA)",
        "residual.Flat(deltaC)",
    ]
    formulas = {
        "L_scope": "sum_s abs(T[phi]*n[phi,s] - N[phi]*t[phi,s])",
        "L_density": (
            "sum_b,s abs(N[phi]*d[phi,b,s] - D[phi,b]*n[phi,s])"
        ),
        "L_cohort_sources": (
            "sum_h,s abs(T[phi]*csrc[phi,h,s] - H[phi,h]*n[phi,s])"
        ),
        "L_cohort_chunks": (
            "sum_h,s abs(T[phi]*k[phi,h,s] - H[phi,h]*t[phi,s])"
        ),
        "L_quota": (
            "sum_b,s,q-in-Q[b] (W/w[b])*abs(w[b]*z[phi,b,s,q] - d[phi,b,s])"
        ),
        "route_loss": (
            "sum_v-in-V_active[i] (M[phi,v]*max_s R[i,v,s]) - "
            "sum_v-in-V_active[i],s A_phi[phi,v,s]*R[i,v,s]"
        ),
    }
    component_rules = {
        "L_scope": {
            "absolute_cross_products": [
                ["T[phi]", "n[phi,s]"],
                ["N[phi]", "t[phi,s]"],
            ],
            "operation": "sum-absolute-left-minus-right",
            "reduce_axes": ["scope"],
        },
        "L_density": {
            "absolute_cross_products": [
                ["N[phi]", "d[phi,b,s]"],
                ["D[phi,b]", "n[phi,s]"],
            ],
            "operation": "sum-absolute-left-minus-right",
            "reduce_axes": ["density_bucket", "scope"],
        },
        "L_cohort_sources": {
            "absolute_cross_products": [
                ["T[phi]", "csrc[phi,h,s]"],
                ["H[phi,h]", "n[phi,s]"],
            ],
            "operation": "sum-absolute-left-minus-right",
            "reduce_axes": ["history_cohort", "scope"],
        },
        "L_cohort_chunks": {
            "absolute_cross_products": [
                ["T[phi]", "k[phi,h,s]"],
                ["H[phi,h]", "t[phi,s]"],
            ],
            "operation": "sum-absolute-left-minus-right",
            "reduce_axes": ["history_cohort", "scope"],
        },
        "L_quota": {
            "absolute_cross_products": [
                ["w[b]", "z[phi,b,s,q]"],
                ["1", "d[phi,b,s]"],
            ],
            "exact_outer_multiplier": {
                "denominator": "w[b]",
                "numerator": "W",
            },
            "operation": "sum-exact-multiplier-times-absolute-left-minus-right",
            "reduce_axes": ["density_bucket", "scope", "valid_quota[b]"],
        },
        "route_loss": {
            "achieved": "sum_v-in-V_active[i],s A_phi[phi,v,s]*R[i,v,s]",
            "ideal": "sum_v-in-V_active[i] M[phi,v]*max_s R[i,v,s]",
            "operation": "checked-ideal-minus-achieved",
            "variant_set": "full-active-variant_id-projection-for-persona-i",
        },
    }
    return {
        "aggregate_definitions": {
            "csrc[phi,h,s]": "sum_v,b,q C_phi[phi,v,s,b,h,q]",
            "d[phi,b,s]": "sum_v,h,q C_phi[phi,v,s,b,h,q]",
            "k[phi,h,s]": "sum_v,b,q q*C_phi[phi,v,s,b,h,q]",
            "n[phi,s]": "sum_v,b,h,q C_phi[phi,v,s,b,h,q]",
            "z[phi,b,s,q]": "sum_v,h C_phi[phi,v,s,b,h,q]",
        },
        "component_rule_schema": (
            "kio.persona.pc-joint-objective-components/v1"
        ),
        "component_rules": component_rules,
        "component_formulas": formulas,
        "component_order": component_order,
        "evaluation_stages": [
            {
                "components": component_order[:8],
                "stage": "pilot-over-projection-of-full-feasible-pairs",
            },
            {
                "components": component_order[8:14],
                "stage": "locked-pilot-plus-residual-full-aggregate",
            },
            {
                "components": component_order[14:],
                "stage": "full-minus-locked-pilot-residual-tie-break",
            },
        ],
        "excluded_terms": [
            "variant-by-scope-proportional-L1",
            "hash-spread-as-aggregate-tie-break",
        ],
        "flatten_semantics": {
            "Flat(A)": (
                "dense nonnegative integer vector over declared variants, including "
                "zero-marginal rows, in canonical axes order"
            ),
            "Flat(A)-axis-order": (
                "within one persona: envelope-family, ASCII-variant_id, scope-ordinal"
            ),
            "Flat(C)": (
                "dense nonnegative integer vector over contributor variants and "
                "valid bucket-specific quotas in canonical axes order"
            ),
            "Flat(C)-axis-order": (
                "within one persona: envelope-family, ASCII-contributor-variant_id, "
                "scope-ordinal, envelope-bucket, P-X-Y-N-U-cohort, ascending-quota"
            ),
            "comparison": "lexicographic-minimum-integer-vector",
            "residual": "delta coordinates use the same axes as their aggregate variables",
        },
        "lexicographic_direction": "minimize-each-component-in-listed-order",
        "per_fixed_persona_profile_symbols": {
            "D[phi,b]": "bound density-bucket contributor-source marginal",
            "F[phi,s]": "bound scope physical-file marginal",
            "H[phi,h]": "bound whole-source history-cohort chunk marginal",
            "M[phi,v]": "bound physical variant marginal",
            "N[phi]": "bound contributor-source total",
            "Q[b]": "ascending quota integers from quota_min[b] through quota_max[b]",
            "T[phi]": "bound contributor-chunk total",
            "i": "one fixed persona_id; never an optimization summation axis",
            "phi": "the objective evaluation profile: pilot or derived full",
            "t[phi,s]": "bound scope contributor-chunk marginal",
            "w[b]": "quota_max[b]-quota_min[b]+1",
        },
        "quota_width_lcm_W": QUOTA_WIDTH_LCM,
        "scope": (
            "the strict tuple is minimized independently for each fixed persona; "
            "there is no cross-person objective tradeoff, and completed persona "
            "results serialize only in canonical persona order"
        ),
        "status": "exact-formulas-defined-but-route-dependent-objective-not-evaluable",
        "term_classification": {
            "L_cohort_sources": "benchmark-canonicality-regularizer-not-observed-statistic",
            "L_quota": "benchmark-canonicality-regularizer-not-observed-statistic",
        },
    }


def _canonical_policy_value():
    (
        envelope_value,
        topology_value,
        problem_value,
        envelope_sha,
        topology_sha,
        problem_sha,
        envelope_bytes,
        topology_bytes,
        problem_bytes,
    ) = _validated_bound_inputs()
    persona_axes, shape = _derived_axes(problem_value)
    quota_bounds = [
        {
            "bucket_id": bucket,
            "quota_max": envelope.DENSITY_BUCKET_BOUNDS[bucket][1],
            "quota_min": envelope.DENSITY_BUCKET_BOUNDS[bucket][0],
            "width": (
                envelope.DENSITY_BUCKET_BOUNDS[bucket][1]
                - envelope.DENSITY_BUCKET_BOUNDS[bucket][0]
                + 1
            ),
        }
        for bucket in envelope.DENSITY_BUCKET_ORDER
    ]
    if QUOTA_WIDTH_LCM != 240 or any(
        QUOTA_WIDTH_LCM % row["width"] != 0 for row in quota_bounds
    ):
        raise PersonaV2JointSolverPolicyError(
            "quota-width LCM differs from the reviewed exact objective"
        )
    blockers = list(problem_value["remaining_g0_blockers"])
    for blocker in (
        "route_affinity_matrix_and_review_receipt_missing",
        "complete_solver_policy_binding_missing",
        "bounded_exact_solver_execution_missing",
        "canonical_joint_allocation_solution_missing",
        "exact_optimality_evidence_or_bounded_canonical_resolve_missing",
        "pilot_aggregate_cell_subset_proof_missing",
        "pilot_source_id_subset_proof_missing",
        "pilot_materialization_subset_proof_missing",
        "pilot_byte_subset_proof_missing",
        "immutable_intent_and_duplicate_cluster_refinement_missing",
        "solver_resource_limits_empirical_calibration_missing",
    ):
        if blocker not in blockers:
            blockers.append(blocker)

    authority = copy.deepcopy(problem_value["authority"])
    authority.update({
        "canonical_joint_allocation_solution_present": False,
        "exact_optimality_proved": False,
        "policy_authorizes_solver_execution": False,
        "policy_authorizes_source_plan": False,
        "route_affinity_matrix_bound": False,
    })
    if any(type(flag) is not bool or flag is not False for flag in authority.values()):
        raise PersonaV2JointSolverPolicyError(
            "policy authority must contain only exact false booleans"
        )

    return {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": authority,
        "binding_graph": {
            "direction": "envelope-to-topology-to-joint-problem-to-policy",
            "policy_self_hash_embedded": False,
            "upstream_forward_policy_hash_allowed": False,
        },
        "bound_input_hashes_validated": True,
        "completion_scope": COMPLETION_SCOPE,
        "envelope_contract_sha256": envelope_sha,
        "exact_objective_evaluable": False,
        "exact_solver_executable": False,
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "generic_aggregate_core_semantics_defined": True,
        "input_bindings": {
            "envelope": {
                "artifact_kind": envelope.ARTIFACT_KIND,
                "artifact_schema": envelope.ARTIFACT_SCHEMA,
                "artifact_schema_version": envelope.ARTIFACT_SCHEMA_VERSION,
                "canonical_bytes": envelope_bytes,
                "sha256": envelope_sha,
            },
            "joint_problem": {
                "artifact_kind": joint_problem.ARTIFACT_KIND,
                "artifact_schema": joint_problem.ARTIFACT_SCHEMA,
                "artifact_schema_version": joint_problem.ARTIFACT_SCHEMA_VERSION,
                "canonical_bytes": problem_bytes,
                "sha256": problem_sha,
            },
            "topology": {
                "artifact_kind": topology.ARTIFACT_KIND,
                "artifact_schema": topology.ARTIFACT_SCHEMA,
                "artifact_schema_version": topology.ARTIFACT_SCHEMA_VERSION,
                "canonical_bytes": topology_bytes,
                "sha256": topology_sha,
            },
        },
        "joint_problem_sha256": problem_sha,
        "policy": {
            "arithmetic": {
                "absolute_value_rule": (
                    "compare checked nonnegative products, checked-subtract smaller "
                    "from larger, then return the checked nonnegative difference"
                ),
                "allowed_operand_and_result_range": (
                    f"0..{MAX_INTEGER_MAGNITUDE} inclusive"
                ),
                "checked_operations": [
                    "addition",
                    "exact-division-with-zero-remainder",
                    "multiplication",
                    "ordered-subtraction-before-absolute-value",
                    "summation",
                ],
                "integer_model": "unsigned-magnitude-exact-integers",
                "max_integer_bits": MAX_INTEGER_BITS,
                "max_integer_magnitude": MAX_INTEGER_MAGNITUDE,
                "min_integer_magnitude": 0,
                "negative-or-overflow_outcome": (
                    "invalid_problem_or_policy-no-result"
                ),
                "no-INT_MIN-absolute-value-path": True,
                "operand_and_result_validation": (
                    "before-and-after-every-checked-operation"
                ),
                "quota_width_division": "W-mod-w[b]-equals-zero-before-solve",
            },
            "axes": {
                "bucket_order": list(envelope.DENSITY_BUCKET_ORDER),
                "family_order": list(envelope.FORMAT_KEYS),
                "history_cohort_order": list(envelope.HISTORY_COHORT_ORDER),
                "persona_order": list(envelope.PERSONA_IDS),
                "persona_order_semantics": (
                    "independent-solve-result-serialization-only-not-shared-objective-axis"
                ),
                "persona_variant_axes": persona_axes,
                "profile_order": list(PROFILES),
                "quota_bounds": quota_bounds,
                "quota_order": "ascending-integer-within-each-bucket",
                "scope_order": "bound-topology-ordinal-1-through-20",
                "scope_ordinals": list(
                    range(1, topology.SCOPES_PER_PERSONA + 1)
                ),
                "source_origin_order": list(SOURCE_ORIGINS),
                "required_scope_history_cohorts": list(
                    REQUIRED_SCOPE_HISTORY_COHORTS
                ),
                "variant_mapping": (
                    "join-by-exact-ASCII-variant_id-within-persona; sort by ASCII "
                    "bytes within envelope family order; never positional-zip"
                ),
            },
            "bound_problem_projection": {
                "evaluation_profile_views": {
                    "full": {
                        "bound_profile_selector": "profiles[row.profile=full]",
                        "decision_view": "pilot-plus-full-minus-pilot",
                    },
                    "pilot": {
                        "bound_profile_selector": "profiles[row.profile=pilot]",
                        "decision_view": "pilot",
                    },
                },
                "field_projection": {
                    "D": "density_bucket_marginals[].contributor_source_count joined by bucket_id",
                    "F": "scope_marginals[].physical_file_count joined by scope ordinal and scope_key",
                    "H": "history_cohort_chunk_marginals[].contract_contributor_chunks joined by cohort_id",
                    "M": (
                        "family_variant_marginals[].variants[].file_count joined by "
                        "family and exact variant_id"
                    ),
                    "N": "contributor_source_count",
                    "T": "target_contract_contributor_chunks",
                    "physical_total": "physical_file_count",
                    "t": "scope_marginals[].contributor_chunk_count joined by scope ordinal and scope_key",
                },
                "persona_selector": "personas[] row joined by exact persona_id i",
                "source_origin_views": {
                    "full-minus-pilot": {
                        "bound_row_selector": "full_minus_pilot_residual",
                        "required_profile_value": "full-minus-pilot",
                    },
                    "pilot": {
                        "bound_row_selector": "profiles[row.profile=pilot]",
                        "required_profile_value": "pilot",
                    },
                },
                "status": "exact-symbol-to-bound-joint-problem-field-projection",
            },
            "canonical_limits": {
                "allowed_plain_value_types": [
                    "exact-bool",
                    "exact-int",
                    "exact-str",
                    "exact-list",
                    "exact-dict-with-string-keys",
                ],
                "floats_allowed": False,
                "max_nesting_depth": MAX_CANONICAL_DEPTH,
                "max_policy_bytes": MAX_POLICY_BYTES,
                "policy_byte_cap_scope": (
                    "in-memory-canonical-value-only-not-a-framed-loader-guarantee"
                ),
                "max_string_bytes": MAX_CANONICAL_STRING_BYTES,
                "null_allowed": False,
                "unicode_normalization": "NFC",
            },
            "hard_constraints": {
                "aggregate_core_complete": True,
                "constraints": _hard_constraints(),
                "declarative_rule_schema": (
                    "kio.persona.pc-generic-aggregate-core-rules/v1"
                ),
                "derived_redundant_consequences": [
                    {
                        "consequence_id": "scope-contributor-source-interval",
                        "lower_bound": (
                            "max(required_scope_history_cohort_count,"
                            "ceil(t[phi,s]/max_contributor_chunks_per_source))"
                        ),
                        "profile_context": ["pilot", "full"],
                        "proof_basis_constraint_ids": [
                            "nonnegative-integral-A-cells",
                            "nonnegative-integral-C-cells",
                            "contributor-refinement",
                            "exact-scope-physical-marginals",
                            "exact-scope-chunk-marginals",
                            "required-cohort-scope-coverage",
                            "quota-membership",
                            "coordinatewise-pilot-lock",
                            "exact-full-aggregate-bound-marginals",
                        ],
                        "source_count": (
                            "sum_v,b,h,q C_phi[i,phi,v,s,b,h,q]"
                        ),
                        "upper_bound": "min(t[phi,s],F[phi,s])",
                    },
                    {
                        "consequence_id": "whole-source-cohort-global-lower-bound",
                        "cohort_lower_bound": (
                            "max(scope_count if h is required else 0,"
                            "ceil(H[phi,h]/max_contributor_chunks_per_source))"
                        ),
                        "profile_context": ["pilot", "full"],
                        "bound_total_identity": "N[phi]=sum_b D[phi,b]",
                        "proof_basis_constraint_ids": [
                            "nonnegative-integral-C-cells",
                            "exact-density-source-marginals",
                            "exact-density-total-identity",
                            "exact-whole-source-cohort-chunk-marginals",
                            "required-cohort-scope-coverage",
                            "quota-membership",
                            "coordinatewise-pilot-lock",
                            "exact-full-aggregate-bound-marginals",
                        ],
                        "relation": (
                            "N[phi]>=sum_h cohort_lower_bound[phi,h]"
                        ),
                    },
                ],
                "evaluator_implementation_present": False,
                "full_hard_constraint_set_complete_for_fixture": False,
                "index_sets": {
                    "coverage_profile_context": ["pilot", "full"],
                    "declared_variant": (
                        "exact persona-specific variant_axis under policy.axes"
                    ),
                    "density_bucket": list(envelope.DENSITY_BUCKET_ORDER),
                    "history_cohort": list(envelope.HISTORY_COHORT_ORDER),
                    "persona": list(envelope.PERSONA_IDS),
                    "required_scope_history_cohort": list(
                        REQUIRED_SCOPE_HISTORY_COHORTS
                    ),
                    "required_scope_history_cohort_count": len(
                        REQUIRED_SCOPE_HISTORY_COHORTS
                    ),
                    "scope": list(range(1, topology.SCOPES_PER_PERSONA + 1)),
                    "scope_count": topology.SCOPES_PER_PERSONA,
                    "source_origin": list(SOURCE_ORIGINS),
                    "valid_quota": quota_bounds,
                    "max_contributor_chunks_per_source": (
                        envelope.MAX_CONTRIBUTOR_CHUNKS_PER_SOURCE
                    ),
                },
                "missing_refinements": [
                    "realism duplicate-cluster and placement constraints keyed by immutable intent_key",
                    "distinct-chunk constraints",
                    "variant renderer complexity and quota feasibility constraints",
                ],
                "status": "generic-aggregate-core-only",
            },
            "intent_and_identity_boundary": {
                "final_identity_derivation": (
                    "source_id and materialization_id are derived only after exact "
                    "aggregate-and-intent assignment succeeds"
                ),
                "pre_solve_key": "immutable-intent_key-required",
                "pre_solve_prohibited_fields": [
                    "source_id",
                    "materialization_id",
                ],
                "required_sequence": [
                    "bind-realism-recipe-and-immutable-intent-overlay",
                    "bind-reviewed-route-matrix-and-independent-review-receipt",
                    "bind-fact-oracle-query-spec-and-variant-feasibility",
                    "refine-complete-A-C-hard-constraint-instance",
                    "solve-exact-aggregate-and-intent-assignment",
                    "establish-optimality-by-bounded-canonical-resolve-or-complete-proof",
                    "derive-final-source-and-materialization-identities",
                    "emit-source-plan",
                ],
                "refinement_status": (
                    "per-intent duplicate-cluster placement semantics absent"
                ),
            },
            "objective": _objective(),
            "resource_limits": {
                "cap_boundary_rule": (
                    "a counter value equal to its cap is allowed; the next operation "
                    "that would exceed the cap is not performed and returns "
                    "resource_exhausted-unknown"
                ),
                "canonical_counters": "per-persona-pilot-full-pair",
                "cap_exhaustion_outcome": "resource_exhausted-unknown",
                "counter_definitions": {
                    "exact_expanded_nodes": (
                        "increment once when a canonical state is first selected "
                        "from the frontier for terminal, prune, or successor "
                        "processing; the root is counted and rejected duplicate "
                        "insertions do not count"
                    ),
                    "exact_flow_augmentations": (
                        "increment once immediately before committing each strictly "
                        "positive residual-path augmentation; zero-flow attempts do "
                        "not count"
                    ),
                    "retained_or_transposition_states": (
                        "high-water size of the union of distinct canonical state "
                        "identities retained in the frontier or transposition store; "
                        "one identity present in both counts once"
                    ),
                },
                "future_max_solution_or_execution_receipt_bytes_per_persona": (
                    MAX_SOLUTION_OR_EXECUTION_RECEIPT_BYTES_PER_PERSONA
                ),
                "future_max_source_plan_bytes_per_persona": (
                    MAX_SOURCE_PLAN_BYTES_PER_PERSONA
                ),
                "max_exact_expanded_nodes_per_persona_pair": (
                    MAX_EXACT_EXPANDED_NODES_PER_PERSONA_PAIR
                ),
                "max_exact_flow_augmentations_per_persona_pair": (
                    MAX_EXACT_FLOW_AUGMENTATIONS_PER_PERSONA_PAIR
                ),
                "max_retained_or_transposition_states_per_persona_pair": (
                    MAX_RETAINED_OR_TRANSPOSITION_STATES_PER_PERSONA_PAIR
                ),
                "pair_counter_lifecycle": (
                    "reset before each persona pair; never reset between pilot, "
                    "extension-oracle, full-aggregate, residual, search, or flow work"
                ),
                "pilot_and_extension_oracle_share_all_pair_counters": True,
                "resource_limits_empirically_calibrated": False,
                "wall_clock_or_rss_abort_outcome": "resource_exhausted-unknown",
                "wall_clock_or_rss_is_canonical": False,
            },
            "route_affinity_future_input": {
                "actual_matrix_present": False,
                "artifact_contract": {
                    "artifact_kind": "persona-pc-v2-route-affinity-matrix",
                    "artifact_schema": "kio.persona.pc-route-affinity/v2",
                    "artifact_schema_version": 2,
                    "authority_exact_false_fields": [
                        "authorizes_g0_freeze",
                        "authorizes_solver_execution",
                        "authorizes_source_plan",
                        "authorizes_write_or_history",
                    ],
                    "canonical_limits": {
                        "max_nesting_depth": MAX_CANONICAL_DEPTH,
                        "max_route_affinity_bytes": MAX_ROUTE_AFFINITY_BYTES,
                        "max_string_bytes": MAX_CANONICAL_STRING_BYTES,
                        "null_allowed": False,
                        "score_values_exact_int_not_bool": True,
                        "unicode_normalization": "NFC",
                    },
                    "canonical_transport": {
                        "body_encoding": "sorted-key-compact-UTF-8-JSON",
                        "duplicate_object_keys_allowed": False,
                        "framed_byte_cap_before_body_required": True,
                        "self_hash_embedded": False,
                        "trailing_bytes_allowed": False,
                    },
                    "fixture_id": envelope.FIXTURE_ID,
                    "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
                    "completion_scope": (
                        "complete-candidate-route-matrix-only-not-reviewed-not-"
                        "solver-executable-not-g0-root"
                    ),
                    "exact_back_binding_rules": {
                        "envelope_contract_sha256": "equals-bound-policy-envelope-contract-sha256",
                        "joint_problem_sha256": "equals-bound-policy-joint-problem-sha256",
                        "joint_solver_policy_sha256": (
                            "equals-canonical-sha256-of-this-generic-policy-sidecar"
                        ),
                        "topology_contract_sha256": "equals-bound-policy-topology-contract-sha256",
                    },
                    "missing_or_unknown_fields_allowed": False,
                    "row_fields": [
                        "persona_id",
                        "family",
                        "variant_id",
                        "scores_by_scope_ordinal",
                    ],
                    "row_identity_set": (
                        "exact full-active persona plus family plus variant_id "
                        "projection from policy axes; missing, duplicate, inactive, "
                        "or foreign rows are invalid"
                    ),
                    "row_order": (
                        "persona order, envelope family order, ASCII variant_id; "
                        "scores list is scope ordinal 1 through 20"
                    ),
                    "rows_container": "rows-exact-list-of-541",
                    "top_level_fields": [
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
                    ],
                    "top_level_required_values": {
                        "g0_contract_frozen": False,
                        "route_matrix_complete": True,
                    },
                },
                "cell_domain": "exact-integer-0-through-4",
                "cell_max": 4,
                "cell_min": 0,
                "cell_type": "exact-int-not-bool",
                "matrix_notation": "R[persona_id,variant_id,scope_ordinal]",
                "projection": (
                    "exact variant_id projection from declared A rows to full-active "
                    "rows; zero-count A rows remain in Flat(A) but have no R row"
                ),
                "required_review_receipt_present": False,
                "review_receipt_artifact_schema_defined": False,
                "review_rubric": {
                    "future_receipt_must_bind_exact_route_matrix_sha256": True,
                    "cross_person_same_variant_vector_clone": (
                        "reject-unless-independent-reasoned-waiver"
                    ),
                    "full_active_row_maximum": "at-least-one",
                    "maximum_score_scope_count": "at-most-eight-unless-reasoned-waiver",
                    "secondary_only_maximum": "requires-independent-reasoned-waiver",
                    "status": "required-future-independent-review-not-present",
                },
                "route_loss_checked_subtraction": (
                    "validate achieved_score<=ideal_score then checked-subtract; "
                    "otherwise arithmetic-invalid-no-result"
                ),
                "route_affinity_input_schema_defined": True,
                "score_semantics": (
                    "physical A only, exactly once; never C, family, cohort, quota, "
                    "profile-origin, or source-row scoring"
                ),
                "shape": {
                    "cell_count": shape["route_matrix_cells"],
                    "full_active_persona_variant_rows": shape[
                        "full_active_persona_variant_rows"
                    ],
                    "scopes_per_row": topology.SCOPES_PER_PERSONA,
                },
                "status": "required-future-reviewed-input-not-bound",
            },
            "search_semantics": {
                "accept_heuristic_incumbent": False,
                "algorithm_class": "bounded-exact-lexicographic-search",
                "cap_exhaustion_may_claim_infeasible": False,
                "cap_exhaustion_may_claim_optimal": False,
                "cap_exhaustion_may_return_incumbent_as_solution": False,
                "full_stage": (
                    "after pilot is locked, optimize full-aggregate objective then "
                    "residual flattened tie-break"
                ),
                "pilot_domain": (
                    "projection of pilot-plus-residual pairs satisfying all bound "
                    "pilot and full-aggregate constraints"
                ),
                "pilot_extension_oracle": (
                    "admissible only on exact extension witness; exhausted oracle "
                    "makes the entire result resource_exhausted-unknown"
                ),
                "warm_start_authority": "advisory-only-never-acceptance-evidence",
            },
            "shape": shape,
            "variable_model": {
                "A": (
                    "A[i,o,v,s] physical-file decision count for origin o and every "
                    "declared variant; "
                    "zero-marginal declared rows remain explicit dense coordinates"
                ),
                "A_phi_evaluation_view": {
                    "full": "A[i,pilot,v,s]+A[i,full-minus-pilot,v,s]",
                    "pilot": "A[i,pilot,v,s]",
                },
                "C": (
                    "C[i,o,v,s,b,h,q] whole-source contributor decision refinement, "
                    "defined "
                    "only for contract_contributor variants and valid q in bucket b"
                ),
                "C_phi_evaluation_view": {
                    "full": (
                        "C[i,pilot,v,s,b,h,q]+"
                        "C[i,full-minus-pilot,v,s,b,h,q]"
                    ),
                    "pilot": "C[i,pilot,v,s,b,h,q]",
                },
                "full_aggregate": (
                    "derived coordinatewise as pilot plus full-minus-pilot residual"
                ),
                "source_rows_present": False,
            },
        },
        "policy_definition_complete_for_bound_problem": False,
        "policy_ready_for_execution": False,
        "policy_sidecar_bound_to_joint_problem": True,
        "proof_status": {
            "canonical_solution_present": False,
            "exact_optimality_evidence_or_bounded_canonical_resolve_present": False,
            "joint_allocation_proved": False,
            "joint_allocation_proved_for_g0": False,
            "necessary_marginal_inputs_bound": True,
            "objective_instance_bound": False,
            "persona_realism_overlay_bound": False,
            "persona_realism_profile_bound": False,
            "pilot_aggregate_cell_subset_proved": False,
            "pilot_byte_subset_proved": False,
            "pilot_materialization_subset_proved": False,
            "pilot_source_id_subset_proved": False,
            "route_affinity_matrix_bound": False,
            "route_affinity_matrix_review_receipt_bound": False,
            "solver_execution_attested": False,
            "solver_policy_bound": False,
            "solver_policy_bound_by_g0_root": False,
            "source_recipe_bound": False,
            "source_intent_refinement_policy_bound": False,
        },
        "remaining_g0_blockers": blockers,
        "required_policy_inputs_intentionally_absent": [
            "route-affinity-matrix",
            "persona-realism-profile-and-overlay",
            "immutable-intent-and-duplicate-cluster-refinement",
            "source-recipe-and-variant-feasibility",
            "fact-oracle-and-query-spec",
        ],
        "required_input_review_evidence_intentionally_absent": [
            "route-affinity-matrix-review-receipt",
        ],
        "required_solver_outputs_and_optimality_evidence_intentionally_absent": [
            "canonical-joint-allocation-solution",
            "exact-optimality-evidence-or-bounded-canonical-resolve",
            "pilot-aggregate-cell-subset-proof",
            "pilot-source-id-subset-proof",
            "pilot-materialization-subset-proof",
            "pilot-byte-subset-proof",
        ],
        "solver_policy_complete": False,
        "resource_limits_empirically_calibrated": False,
        "topology_contract_sha256": topology_sha,
    }


def build_joint_solver_policy():
    """Return a detached, canonical, non-executable solver-policy sidecar."""
    return copy.deepcopy(_canonical_policy_value())


def _validate_canonical_value(value, depth=0):
    if depth > MAX_CANONICAL_DEPTH:
        raise PersonaV2JointSolverPolicyError(
            "v2 joint solver policy exceeds canonical nesting depth"
        )
    if type(value) is bool:
        return
    if type(value) is int:
        if value < 0 or value > MAX_INTEGER_MAGNITUDE:
            raise PersonaV2JointSolverPolicyError(
                "v2 joint solver policy integer exceeds checked 127-bit range"
            )
        return
    if type(value) is str:
        try:
            encoded = value.encode("utf-8", "strict")
        except UnicodeEncodeError:
            raise PersonaV2JointSolverPolicyError(
                "v2 joint solver policy strings must be valid UTF-8"
            ) from None
        if len(encoded) > MAX_CANONICAL_STRING_BYTES:
            raise PersonaV2JointSolverPolicyError(
                "v2 joint solver policy string exceeds byte bound"
            )
        if unicodedata.normalize("NFC", value) != value:
            raise PersonaV2JointSolverPolicyError(
                "v2 joint solver policy strings must be NFC"
            )
        return
    if type(value) is list:
        for item in value:
            _validate_canonical_value(item, depth + 1)
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise PersonaV2JointSolverPolicyError(
                    "v2 joint solver policy object keys must be strings"
                )
            _validate_canonical_value(key, depth + 1)
            _validate_canonical_value(item, depth + 1)
        return
    raise PersonaV2JointSolverPolicyError(
        f"unsupported v2 joint solver policy value type: {type(value).__name__}"
    )


def canonical_json_bytes(value):
    """Encode strict JSON with no null, float, subclasses, or non-NFC strings."""
    _validate_canonical_value(value)
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(raw) > MAX_POLICY_BYTES:
        raise PersonaV2JointSolverPolicyError(
            "v2 joint solver policy exceeds 512 KiB canonical cap"
        )
    return raw


def validate_joint_solver_policy(value):
    """Require byte-for-byte equality with deterministic regeneration."""
    if type(value) is not dict:
        raise PersonaV2JointSolverPolicyError(
            "v2 joint solver policy must be an object"
        )
    actual = canonical_json_bytes(value)
    expected = canonical_json_bytes(_canonical_policy_value())
    if actual != expected:
        raise PersonaV2JointSolverPolicyError(
            "v2 joint solver policy differs from canonical regeneration"
        )
    return True


def joint_solver_policy_sha256(value=None):
    if value is None:
        value = build_joint_solver_policy()
    validate_joint_solver_policy(value)
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def require_joint_allocation_solution():
    raise PersonaV2JointSolverPolicyError(
        "v2 solver-policy sidecar defines only an incomplete generic aggregate "
        "core; it contains no executable objective instance, solution, or proof"
    )
