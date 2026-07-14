"""One-way bindings from the frozen v2 planning chain into later inputs.

This module does not define an artifact of its own.  It rebuilds and validates
the envelope, topology, necessary joint problem, and generic solver policy on
every call, then returns compact identity/length/hash references.  Keeping the
function uncached prevents callers from poisoning later builds through a
mutable shared value.
"""

from __future__ import annotations

import hashlib
from types import MappingProxyType

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_contract as envelope
    from . import persona_v2_joint_problem as joint_problem
    from . import persona_v2_joint_solver_policy as solver_policy
    from . import persona_v2_topology as topology
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_contract as envelope
    import persona_v2_joint_problem as joint_problem
    import persona_v2_joint_solver_policy as solver_policy
    import persona_v2_topology as topology


UPSTREAM_ORDER = (
    "envelope",
    "topology",
    "joint-problem",
    "joint-solver-policy",
)

_MUST_REMAIN_FALSE_KEYS = frozenset(
    (
        "actual_matrix_present",
        "canonical_joint_allocation_solution_present",
        "canonical_solution_present",
        "exact_optimality_proved",
        "exact_objective_evaluable",
        "exact_solver_executable",
        "g0_contract_frozen",
        "incidental_wave_budget_proved",
        "joint_allocation_geometry_proved",
        "joint_allocation_proved",
        "joint_allocation_proved_for_g0",
        "pilot_aggregate_cell_subset_proved",
        "pilot_byte_subset_proved",
        "pilot_materialization_subset_proved",
        "pilot_source_id_subset_proved",
        "policy_authorizes_solver_execution",
        "policy_authorizes_source_plan",
        "policy_definition_complete_for_bound_problem",
        "policy_ready_for_execution",
        "required_review_receipt_present",
        "resource_limits_empirically_calibrated",
        "route_affinity_matrix_bound",
        "route_affinity_matrix_review_receipt_bound",
        "solver_execution_attested",
        "solver_policy_bound",
        "solver_policy_bound_by_g0_root",
        "solver_policy_complete",
        "source_intent_refinement_policy_bound",
        "source_recipe_bound",
    )
)

EXPECTED_UPSTREAM_BINDINGS = MappingProxyType({
    "envelope": MappingProxyType({
        "artifact_kind": "persona-pc-v2-envelope",
        "artifact_schema": "kcs.persona.pc-envelope/v2",
        "artifact_schema_version": 2,
        "canonical_bytes": 71_979,
        "fixture_id": "kcs-persona-pc-v2",
        "fixture_schema_version": 2,
        "name": "envelope",
        "sha256": "1d49e79049b409ee5bd82d0b307db5055c2a58544df81858b77552ea82bff370",
    }),
    "topology": MappingProxyType({
        "artifact_kind": "persona-pc-v2-topology",
        "artifact_schema": "kcs.persona.pc-topology/v2",
        "artifact_schema_version": 2,
        "canonical_bytes": 134_195,
        "fixture_id": "kcs-persona-pc-v2",
        "fixture_schema_version": 2,
        "name": "topology",
        "sha256": "204c9a136438c0dfff3718549c2fcb6009e6ccbe9debdd0cfe54bfaa4290b68f",
    }),
    "joint-problem": MappingProxyType({
        "artifact_kind": "persona-pc-v2-joint-allocation-problem",
        "artifact_schema": "kcs.persona.pc-joint-problem/v2",
        "artifact_schema_version": 2,
        "canonical_bytes": 744_137,
        "fixture_id": "kcs-persona-pc-v2",
        "fixture_schema_version": 2,
        "name": "joint-problem",
        "sha256": "8551472e4993f21ff71f886b3f80b9b02410c409476d0be91d773db335907074",
    }),
    "joint-solver-policy": MappingProxyType({
        "artifact_kind": "persona-pc-v2-joint-solver-policy",
        "artifact_schema": "kcs.persona.pc-joint-solver-policy/v2",
        "artifact_schema_version": 2,
        "canonical_bytes": 83_004,
        "fixture_id": "kcs-persona-pc-v2",
        "fixture_schema_version": 2,
        "name": "joint-solver-policy",
        "sha256": "2a6c169a5cd02b01e330abf0f3a828d0d947a2f66b18f19e97a682d2edd50857",
    }),
})

_ALLOWED_SHA256_PATHS = MappingProxyType({
    "envelope": frozenset(),
    "topology": frozenset((("envelope_contract_sha256",),)),
    "joint-problem": frozenset(
        (("envelope_contract_sha256",), ("topology_contract_sha256",))
    ),
    "joint-solver-policy": frozenset(
        (
            ("envelope_contract_sha256",),
            ("input_bindings", "envelope", "sha256"),
            ("input_bindings", "joint_problem", "sha256"),
            ("input_bindings", "topology", "sha256"),
            ("joint_problem_sha256",),
            (
                "policy", "route_affinity_future_input", "artifact_contract",
                "exact_back_binding_rules", "envelope_contract_sha256",
            ),
            (
                "policy", "route_affinity_future_input", "artifact_contract",
                "exact_back_binding_rules", "joint_problem_sha256",
            ),
            (
                "policy", "route_affinity_future_input", "artifact_contract",
                "exact_back_binding_rules", "joint_solver_policy_sha256",
            ),
            (
                "policy", "route_affinity_future_input", "artifact_contract",
                "exact_back_binding_rules", "topology_contract_sha256",
            ),
            (
                "policy", "route_affinity_future_input", "review_rubric",
                "future_receipt_must_bind_exact_route_matrix_sha256",
            ),
            ("topology_contract_sha256",),
        )
    ),
})


class PersonaV2InputBindingError(ValueError):
    """Raised when a supposedly frozen upstream is invalid or authorizing."""


def _require_negative_authority(name, value):
    found_top_level_authority = False

    def visit(node, path):
        nonlocal found_top_level_authority
        if type(node) is list:
            for index, item in enumerate(node):
                visit(item, f"{path}[{index}]")
            return
        if type(node) is not dict:
            return
        for key, item in node.items():
            child_path = f"{path}.{key}"
            if key == "authority":
                if path == name:
                    found_top_level_authority = True
                if type(item) is not dict or not item:
                    raise PersonaV2InputBindingError(
                        f"{child_path} must be a non-empty exact object"
                    )
                for flag_name, flag in item.items():
                    if (
                        type(flag_name) is not str
                        or type(flag) is not bool
                        or flag is not False
                    ):
                        raise PersonaV2InputBindingError(
                            f"{child_path}.{flag_name!r} must be exact false"
                        )
            if key in _MUST_REMAIN_FALSE_KEYS and (
                type(item) is not bool or item is not False
            ):
                raise PersonaV2InputBindingError(
                    f"{child_path} must remain exact false"
                )
            visit(item, child_path)

    visit(value, name)
    if not found_top_level_authority:
        raise PersonaV2InputBindingError(
            f"{name} must contain top-level negative authority"
        )


def _sha256_paths(value):
    result = set()

    def visit(node, path):
        if type(node) is list:
            for item in node:
                visit(item, path + ("[]",))
            return
        if type(node) is not dict:
            return
        for key, item in node.items():
            child_path = path + (key,)
            if key == "sha256" or key.endswith("_sha256"):
                result.add(child_path)
            visit(item, child_path)

    visit(value, ())
    return frozenset(result)


def _binding(name, value, *, validate, canonical, digest):
    validate(value)
    if value.get("fixture_id") != envelope.FIXTURE_ID:
        raise PersonaV2InputBindingError(f"{name} fixture identity drifted")
    if value.get("fixture_schema_version") != envelope.FIXTURE_SCHEMA_VERSION:
        raise PersonaV2InputBindingError(f"{name} fixture schema version drifted")
    if value.get("g0_contract_frozen") is not False:
        raise PersonaV2InputBindingError(f"{name} must remain non-G0")
    _require_negative_authority(name, value)
    if _sha256_paths(value) != _ALLOWED_SHA256_PATHS[name]:
        raise PersonaV2InputBindingError(
            f"{name} contains a missing, unexpected, or downstream SHA binding"
        )
    raw = canonical(value)
    actual_digest = digest(value)
    if (
        type(actual_digest) is not str
        or len(actual_digest) != 64
        or any(character not in "0123456789abcdef" for character in actual_digest)
    ):
        raise PersonaV2InputBindingError(f"{name} returned an invalid SHA-256")
    independent_digest = hashlib.sha256(raw).hexdigest()
    if actual_digest != independent_digest:
        raise PersonaV2InputBindingError(
            f"{name} digest does not match its canonical body"
        )
    binding = {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "fixture_id": value["fixture_id"],
        "fixture_schema_version": value["fixture_schema_version"],
        "name": name,
        "sha256": actual_digest,
    }
    if binding != EXPECTED_UPSTREAM_BINDINGS[name]:
        raise PersonaV2InputBindingError(
            f"{name} differs from the pinned upstream identity/size/digest"
        )
    return binding


def build_upstream_bindings():
    """Return freshly rebuilt compact references in the required DAG order."""

    envelope_value = envelope.build_envelope_contract()
    topology_value = topology.build_topology_contract()
    problem_value = joint_problem.build_joint_problem()
    policy_value = solver_policy.build_joint_solver_policy()

    if topology_value.get("envelope_contract_sha256") != envelope.envelope_contract_sha256(
        envelope_value
    ):
        raise PersonaV2InputBindingError("topology does not bind the rebuilt envelope")
    if problem_value.get("envelope_contract_sha256") != envelope.envelope_contract_sha256(
        envelope_value
    ):
        raise PersonaV2InputBindingError("joint problem does not bind the rebuilt envelope")
    if problem_value.get("topology_contract_sha256") != topology.topology_contract_sha256(
        topology_value
    ):
        raise PersonaV2InputBindingError("joint problem does not bind the rebuilt topology")
    if policy_value.get("joint_problem_sha256") != joint_problem.joint_problem_sha256(
        problem_value
    ):
        raise PersonaV2InputBindingError("solver policy does not bind the rebuilt problem")
    if policy_value.get("topology_contract_sha256") != topology.topology_contract_sha256(
        topology_value
    ):
        raise PersonaV2InputBindingError("solver policy does not bind the rebuilt topology")
    if policy_value.get("envelope_contract_sha256") != envelope.envelope_contract_sha256(
        envelope_value
    ):
        raise PersonaV2InputBindingError("solver policy does not bind the rebuilt envelope")
    if policy_value.get("policy_ready_for_execution") is not False:
        raise PersonaV2InputBindingError("generic solver policy must remain non-executable")

    rows = [
        _binding(
            "envelope",
            envelope_value,
            validate=envelope.validate_envelope_contract,
            canonical=envelope.canonical_json_bytes,
            digest=envelope.envelope_contract_sha256,
        ),
        _binding(
            "topology",
            topology_value,
            validate=topology.validate_topology_contract,
            canonical=topology.canonical_json_bytes,
            digest=topology.topology_contract_sha256,
        ),
        _binding(
            "joint-problem",
            problem_value,
            validate=joint_problem.validate_joint_problem,
            canonical=joint_problem.canonical_json_bytes,
            digest=joint_problem.joint_problem_sha256,
        ),
        _binding(
            "joint-solver-policy",
            policy_value,
            validate=solver_policy.validate_joint_solver_policy,
            canonical=solver_policy.canonical_json_bytes,
            digest=solver_policy.joint_solver_policy_sha256,
        ),
    ]
    if tuple(row["name"] for row in rows) != UPSTREAM_ORDER:
        raise PersonaV2InputBindingError("upstream binding order drifted")
    return rows


def get_upstream_binding(name):
    """Return one detached binding by exact string identity."""

    if type(name) is not str or name not in UPSTREAM_ORDER:
        raise PersonaV2InputBindingError(f"unknown upstream binding: {name!r}")
    return next(row for row in build_upstream_bindings() if row["name"] == name)
