import copy
import json
import os
import subprocess
import sys
import unittest
from decimal import Decimal

from eval import persona_fixture_spec as v1
from eval import persona_v2_contract as envelope
from eval import persona_v2_joint_problem as problem
from eval import persona_v2_joint_solver_policy as policy
from eval import persona_v2_topology as topology


EXPECTED_ENVELOPE_SHA256 = (
    "12a5f175cbcd9b1ea9886c8a8e3b673b857f6b314ba48c9b71e6b279150244a7"
)
EXPECTED_TOPOLOGY_SHA256 = (
    "02e0e68d37378a1123743673aad826757d17480de77a5a7313f09932c5759c4a"
)
EXPECTED_PROBLEM_SHA256 = (
    "f76a2b8ae5557a45af2c4e758b1f2b7663809ef80d7f33987abe3f5e9fc17207"
)
EXPECTED_POLICY_SHA256 = (
    "47266ca9ea01bce9462e349ab0d4348975f98a9efbab12252e0f8be3c4263712"
)
EXPECTED_POLICY_BYTES = 83_004


def _reference_components(*, source_rows, scope_chunks, cohort_chunks):
    """Independent evaluator for the five integer canonicality components."""
    scopes = tuple(scope_chunks)
    cohorts = tuple(cohort_chunks)
    quotas = tuple(range(1, 5))
    n = {scope: 0 for scope in scopes}
    d = {scope: 0 for scope in scopes}
    cohort_sources = {(cohort, scope): 0 for cohort in cohorts for scope in scopes}
    cohort_scope_chunks = {
        (cohort, scope): 0 for cohort in cohorts for scope in scopes
    }
    quota_sources = {(scope, quota): 0 for scope in scopes for quota in quotas}
    for scope, cohort, quota in source_rows:
        n[scope] += 1
        d[scope] += 1
        cohort_sources[cohort, scope] += 1
        cohort_scope_chunks[cohort, scope] += quota
        quota_sources[scope, quota] += 1

    source_total = len(source_rows)
    chunk_total = sum(scope_chunks.values())
    bucket_source_total = source_total
    width = 4
    width_lcm = 240
    l_scope = sum(
        abs(chunk_total * n[scope] - source_total * scope_chunks[scope])
        for scope in scopes
    )
    l_density = sum(
        abs(source_total * d[scope] - bucket_source_total * n[scope])
        for scope in scopes
    )
    l_cohort_sources = sum(
        abs(
            chunk_total * cohort_sources[cohort, scope]
            - cohort_chunks[cohort] * n[scope]
        )
        for cohort in cohorts
        for scope in scopes
    )
    l_cohort_chunks = sum(
        abs(
            chunk_total * cohort_scope_chunks[cohort, scope]
            - cohort_chunks[cohort] * scope_chunks[scope]
        )
        for cohort in cohorts
        for scope in scopes
    )
    l_quota = sum(
        (width_lcm // width)
        * abs(width * quota_sources[scope, quota] - d[scope])
        for scope in scopes
        for quota in quotas
    )
    return (
        l_scope,
        l_density,
        l_cohort_sources,
        l_cohort_chunks,
        l_quota,
    )


class PersonaV2JointSolverPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = policy.build_joint_solver_policy()

    def test_identity_and_one_way_input_bindings_are_exact(self):
        value = self.value
        self.assertEqual(value["artifact_schema"], policy.ARTIFACT_SCHEMA)
        self.assertEqual(value["artifact_schema_version"], 2)
        self.assertEqual(value["artifact_kind"], policy.ARTIFACT_KIND)
        self.assertEqual(value["fixture_id"], "kio-persona-pc-v2")
        self.assertEqual(value["fixture_schema_version"], 2)
        self.assertEqual(value["completion_scope"], policy.COMPLETION_SCOPE)
        self.assertEqual(
            value["binding_graph"],
            {
                "direction": "envelope-to-topology-to-joint-problem-to-policy",
                "policy_self_hash_embedded": False,
                "upstream_forward_policy_hash_allowed": False,
            },
        )
        self.assertEqual(
            value["input_bindings"],
            {
                "envelope": {
                    "artifact_kind": envelope.ARTIFACT_KIND,
                    "artifact_schema": envelope.ARTIFACT_SCHEMA,
                    "artifact_schema_version": 2,
                    "canonical_bytes": 71_979,
                    "sha256": EXPECTED_ENVELOPE_SHA256,
                },
                "joint_problem": {
                    "artifact_kind": problem.ARTIFACT_KIND,
                    "artifact_schema": problem.ARTIFACT_SCHEMA,
                    "artifact_schema_version": 2,
                    "canonical_bytes": 744_137,
                    "sha256": EXPECTED_PROBLEM_SHA256,
                },
                "topology": {
                    "artifact_kind": topology.ARTIFACT_KIND,
                    "artifact_schema": topology.ARTIFACT_SCHEMA,
                    "artifact_schema_version": 2,
                    "canonical_bytes": 134_195,
                    "sha256": EXPECTED_TOPOLOGY_SHA256,
                },
            },
        )
        self.assertTrue(value["bound_input_hashes_validated"])
        self.assertTrue(value["policy_sidecar_bound_to_joint_problem"])
        self.assertFalse(
            problem.build_joint_problem()["proof_status"]["solver_policy_bound"]
        )

    def test_incomplete_non_authorizing_truth_table_is_exact(self):
        value = self.value
        self.assertTrue(value["generic_aggregate_core_semantics_defined"])
        for key in (
            "exact_objective_evaluable",
            "exact_solver_executable",
            "g0_contract_frozen",
            "policy_definition_complete_for_bound_problem",
            "policy_ready_for_execution",
            "solver_policy_complete",
            "resource_limits_empirically_calibrated",
        ):
            with self.subTest(key=key):
                self.assertIs(value[key], False)
        self.assertTrue(value["authority"])
        self.assertTrue(
            all(
                type(flag) is bool and flag is False
                for flag in value["authority"].values()
            )
        )
        expected_true_proofs = {"necessary_marginal_inputs_bound"}
        self.assertEqual(
            {key for key, flag in value["proof_status"].items() if flag is True},
            expected_true_proofs,
        )
        self.assertTrue(
            all(type(flag) is bool for flag in value["proof_status"].values())
        )
        with self.assertRaisesRegex(
            policy.PersonaV2JointSolverPolicyError,
            "no executable objective instance, solution, or proof",
        ):
            policy.require_joint_allocation_solution()

    def test_declared_dense_axes_and_active_route_projection_are_exact(self):
        shape = self.value["policy"]["shape"]
        self.assertEqual(
            shape,
            {
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
            },
        )
        axes = self.value["policy"]["axes"]["persona_variant_axes"]
        self.assertEqual(
            tuple(row["declared_variant_count"] for row in axes),
            (28, 28, 28, 28, 28, 28, 28, 31, 28, 25, 28, 31, 25, 28, 28, 31, 28, 28, 28, 31),
        )
        self.assertEqual(
            tuple(row["full_active_variant_count"] for row in axes),
            (28, 26, 27, 28, 28, 28, 26, 29, 26, 24, 26, 29, 24, 27, 26, 30, 26, 27, 27, 29),
        )
        contributor_counts = tuple(
            sum(
                variant["gate_role"] == "contract_contributor"
                for variant in row["variant_axis"]
            )
            for row in axes
        )
        self.assertEqual(
            contributor_counts,
            (7, 7, 7, 7, 7, 7, 4, 7, 4, 4, 4, 7, 4, 7, 4, 7, 4, 7, 4, 7),
        )
        self.assertEqual(
            self.value["policy"]["route_affinity_future_input"]["shape"],
            {
                "cell_count": 10_820,
                "full_active_persona_variant_rows": 541,
                "scopes_per_row": 20,
            },
        )

    def test_canonical_axis_order_uses_identity_not_authored_position(self):
        axes = self.value["policy"]["axes"]
        self.assertEqual(tuple(axes["family_order"]), envelope.FORMAT_KEYS)
        self.assertEqual(tuple(axes["bucket_order"]), envelope.DENSITY_BUCKET_ORDER)
        self.assertEqual(tuple(axes["history_cohort_order"]), ("P", "X", "Y", "N", "U"))
        self.assertEqual(tuple(axes["scope_ordinals"]), tuple(range(1, 21)))
        self.assertEqual(tuple(axes["source_origin_order"]), ("pilot", "full-minus-pilot"))
        p01 = axes["persona_variant_axes"][0]
        self.assertEqual(p01["persona_id"], "p01")
        self.assertEqual(
            [
                row["variant_id"]
                for row in p01["variant_axis"]
                if row["family"] == "md"
            ],
            ["markdown", "md"],
        )
        self.assertIn("never positional-zip", axes["variant_mapping"])

    def test_primal_hard_constraints_and_phase_views_are_explicit(self):
        hard = self.value["policy"]["hard_constraints"]
        constraints = hard["constraints"]
        ids = [row["constraint_id"] for row in constraints]
        self.assertEqual(
            ids,
            [
                "nonnegative-integral-A-cells",
                "nonnegative-integral-C-cells",
                "exact-variant-physical-marginals",
                "exact-scope-physical-marginals",
                "contributor-refinement",
                "exact-density-source-marginals",
                "exact-scope-chunk-marginals",
                "exact-whole-source-cohort-chunk-marginals",
                "exact-contributor-source-total",
                "exact-physical-total-identities",
                "exact-density-total-identity",
                "exact-chunk-total-identities",
                "required-cohort-scope-coverage",
                "quota-membership",
                "coordinatewise-pilot-lock",
                "exact-full-aggregate-bound-marginals",
                "pilot-full-extension",
            ],
        )
        by_id = {row["constraint_id"]: row for row in constraints}
        self.assertEqual(
            by_id["required-cohort-scope-coverage"]["quantified_axes"]["phi"],
            "coverage_profile_context",
        )
        self.assertEqual(
            hard["index_sets"]["coverage_profile_context"], ["pilot", "full"]
        )
        self.assertNotIn("full-minus-pilot", hard["index_sets"]["coverage_profile_context"])
        self.assertFalse(hard["full_hard_constraint_set_complete_for_fixture"])
        self.assertFalse(hard["evaluator_implementation_present"])
        projection = self.value["policy"]["bound_problem_projection"]
        self.assertEqual(
            projection["source_origin_views"],
            {
                "full-minus-pilot": {
                    "bound_row_selector": "full_minus_pilot_residual",
                    "required_profile_value": "full-minus-pilot",
                },
                "pilot": {
                    "bound_row_selector": "profiles[row.profile=pilot]",
                    "required_profile_value": "pilot",
                },
            },
        )
        self.assertEqual(
            projection["evaluation_profile_views"],
            {
                "full": {
                    "bound_profile_selector": "profiles[row.profile=full]",
                    "decision_view": "pilot-plus-full-minus-pilot",
                },
                "pilot": {
                    "bound_profile_selector": "profiles[row.profile=pilot]",
                    "decision_view": "pilot",
                },
            },
        )
        self.assertEqual(
            projection["field_projection"],
            {
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
        )
        variables = self.value["policy"]["variable_model"]
        self.assertEqual(
            variables["A_phi_evaluation_view"]["full"],
            "A[i,pilot,v,s]+A[i,full-minus-pilot,v,s]",
        )
        self.assertEqual(
            variables["C_phi_evaluation_view"]["full"],
            "C[i,pilot,v,s,b,h,q]+C[i,full-minus-pilot,v,s,b,h,q]",
        )

    def test_exact_objective_formulas_and_strict_order_are_frozen(self):
        objective = self.value["policy"]["objective"]
        self.assertEqual(
            objective["component_order"],
            [
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
            ],
        )
        self.assertEqual(objective["quota_width_lcm_W"], 240)
        self.assertEqual(
            objective["component_rules"]["L_scope"]["reduce_axes"], ["scope"]
        )
        self.assertEqual(
            objective["component_rules"]["L_density"]["reduce_axes"],
            ["density_bucket", "scope"],
        )
        self.assertEqual(
            objective["component_rules"]["L_quota"]["exact_outer_multiplier"],
            {"denominator": "w[b]", "numerator": "W"},
        )
        route = objective["component_rules"]["route_loss"]
        self.assertEqual(
            route["variant_set"], "full-active-variant_id-projection-for-persona-i"
        )
        self.assertIn("M[phi,v]*max_s", route["ideal"])
        self.assertIn("A_phi", route["achieved"])
        self.assertEqual(
            objective["excluded_terms"],
            ["variant-by-scope-proportional-L1", "hash-spread-as-aggregate-tie-break"],
        )
        self.assertEqual(
            objective["term_classification"],
            {
                "L_cohort_sources": "benchmark-canonicality-regularizer-not-observed-statistic",
                "L_quota": "benchmark-canonicality-regularizer-not-observed-statistic",
            },
        )

    def test_reference_objective_arithmetic_matches_structured_contract(self):
        observed = _reference_components(
            source_rows=(
                ("s1", "h1", 1),
                ("s1", "h2", 3),
                ("s2", "h1", 2),
                ("s2", "h2", 4),
            ),
            scope_chunks={"s1": 4, "s2": 6},
            cohort_chunks={"h1": 3, "h2": 7},
        )
        self.assertEqual(observed, (8, 0, 16, 8, 960))
        rules = self.value["policy"]["objective"]["component_rules"]
        self.assertEqual(
            set(rules),
            {"L_scope", "L_density", "L_cohort_sources", "L_cohort_chunks", "L_quota", "route_loss"},
        )
        for component in (
            "L_scope",
            "L_density",
            "L_cohort_sources",
            "L_cohort_chunks",
            "L_quota",
        ):
            self.assertIn("absolute_cross_products", rules[component])

    def test_pilot_extension_route_and_identity_boundaries_fail_closed(self):
        search = self.value["policy"]["search_semantics"]
        self.assertIn("projection", search["pilot_domain"])
        self.assertIn("exact extension witness", search["pilot_extension_oracle"])
        self.assertFalse(search["accept_heuristic_incumbent"])
        self.assertFalse(search["cap_exhaustion_may_claim_infeasible"])
        self.assertFalse(search["cap_exhaustion_may_claim_optimal"])
        route = self.value["policy"]["route_affinity_future_input"]
        self.assertTrue(route["route_affinity_input_schema_defined"])
        self.assertFalse(route["actual_matrix_present"])
        self.assertFalse(route["required_review_receipt_present"])
        self.assertEqual(
            route["matrix_notation"], "R[persona_id,variant_id,scope_ordinal]"
        )
        self.assertIn("physical A only", route["score_semantics"])
        route_contract = route["artifact_contract"]
        self.assertEqual(
            (
                route_contract["artifact_schema"],
                route_contract["artifact_schema_version"],
                route_contract["artifact_kind"],
            ),
            (
                "kio.persona.pc-route-affinity/v2",
                2,
                "persona-pc-v2-route-affinity-matrix",
            ),
        )
        self.assertEqual(
            route_contract["canonical_limits"]["max_route_affinity_bytes"],
            128 * 2**10,
        )
        self.assertEqual(
            route_contract["canonical_transport"],
            {
                "body_encoding": "sorted-key-compact-UTF-8-JSON",
                "duplicate_object_keys_allowed": False,
                "framed_byte_cap_before_body_required": True,
                "self_hash_embedded": False,
                "trailing_bytes_allowed": False,
            },
        )
        self.assertEqual(
            route_contract["row_fields"],
            ["persona_id", "family", "variant_id", "scores_by_scope_ordinal"],
        )
        self.assertEqual(
            set(route_contract["exact_back_binding_rules"]),
            {
                "envelope_contract_sha256",
                "topology_contract_sha256",
                "joint_problem_sha256",
                "joint_solver_policy_sha256",
            },
        )
        self.assertEqual(route_contract["rows_container"], "rows-exact-list-of-541")
        self.assertFalse(route_contract["missing_or_unknown_fields_allowed"])
        self.assertEqual(
            route_contract["top_level_required_values"],
            {"g0_contract_frozen": False, "route_matrix_complete": True},
        )
        self.assertEqual(len(route_contract["top_level_fields"]), 14)
        self.assertEqual(
            route_contract["authority_exact_false_fields"],
            [
                "authorizes_g0_freeze",
                "authorizes_solver_execution",
                "authorizes_source_plan",
                "authorizes_write_or_history",
            ],
        )
        self.assertIn("missing, duplicate, inactive", route_contract["row_identity_set"])
        self.assertFalse(route["review_receipt_artifact_schema_defined"])
        boundary = self.value["policy"]["intent_and_identity_boundary"]
        self.assertEqual(boundary["pre_solve_key"], "immutable-intent_key-required")
        self.assertEqual(
            boundary["pre_solve_prohibited_fields"],
            ["source_id", "materialization_id"],
        )
        self.assertEqual(
            set(
                key
                for key, flag in self.value["proof_status"].items()
                if key.startswith("pilot_") and flag is False
            ),
            {
                "pilot_aggregate_cell_subset_proved",
                "pilot_byte_subset_proved",
                "pilot_materialization_subset_proved",
                "pilot_source_id_subset_proved",
            },
        )

    def test_resource_caps_checked_arithmetic_and_boundaries_are_exact(self):
        resources = self.value["policy"]["resource_limits"]
        self.assertEqual(resources["max_exact_expanded_nodes_per_persona_pair"], 2_000_000)
        self.assertEqual(resources["max_exact_flow_augmentations_per_persona_pair"], 2_000_000)
        self.assertEqual(resources["max_retained_or_transposition_states_per_persona_pair"], 262_144)
        self.assertEqual(resources["future_max_solution_or_execution_receipt_bytes_per_persona"], 8 * 2**20)
        self.assertEqual(resources["future_max_source_plan_bytes_per_persona"], 16 * 2**20)
        self.assertEqual(resources["cap_exhaustion_outcome"], "resource_exhausted-unknown")
        self.assertIn("equal to its cap is allowed", resources["cap_boundary_rule"])
        self.assertFalse(resources["resource_limits_empirically_calibrated"])
        arithmetic = self.value["policy"]["arithmetic"]
        self.assertEqual(arithmetic["max_integer_bits"], 127)
        self.assertEqual(arithmetic["max_integer_magnitude"], 2**127 - 1)
        self.assertTrue(arithmetic["no-INT_MIN-absolute-value-path"])
        self.assertEqual(
            [row["width"] for row in self.value["policy"]["axes"]["quota_bounds"]],
            [4, 16, 30, 20],
        )
        # Independent worst-case bounds for the currently authored envelope.
        self.assertEqual(2 * 120_000 * 16_000, 3_840_000_000)
        self.assertEqual(2 * 16_000**2, 512_000_000)
        self.assertEqual(2 * 120_000**2, 28_800_000_000)
        self.assertEqual(2 * 240 * 16_000, 7_680_000)
        self.assertLess(28_800_000_000, 2**127 - 1)

    def test_canonical_hash_size_roundtrip_tamper_and_detachment(self):
        first = policy.build_joint_solver_policy()
        second = policy.build_joint_solver_policy()
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        raw = policy.canonical_json_bytes(first)
        self.assertEqual(len(raw), EXPECTED_POLICY_BYTES)
        self.assertEqual(policy.joint_solver_policy_sha256(first), EXPECTED_POLICY_SHA256)
        self.assertEqual(json.loads(raw), first)
        self.assertTrue(policy.validate_joint_solver_policy(first))

        mutations = (
            lambda value: value.__setitem__("joint_problem_sha256", "0" * 64),
            lambda value: value.__setitem__("exact_solver_executable", True),
            lambda value: value.__setitem__("exact_solver_executable", 0),
            lambda value: value["policy"]["objective"]["component_order"].reverse(),
            lambda value: value["policy"]["shape"].__setitem__("route_matrix_cells", 10_819),
            lambda value: value.__setitem__("route_affinity_matrix", [[4]]),
            lambda value: value.__setitem__("solution", []),
            lambda value: value.__setitem__("source_rows", []),
            lambda value: value.__setitem__("certificate", {}),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                changed = copy.deepcopy(first)
                mutate(changed)
                with self.assertRaises(policy.PersonaV2JointSolverPolicyError):
                    policy.validate_joint_solver_policy(changed)
                with self.assertRaises(policy.PersonaV2JointSolverPolicyError):
                    policy.joint_solver_policy_sha256(changed)

        first["policy"]["shape"]["route_matrix_cells"] = 0
        self.assertEqual(
            policy.build_joint_solver_policy()["policy"]["shape"]["route_matrix_cells"],
            10_820,
        )
        internal = policy._canonical_policy_value()
        internal["exact_solver_executable"] = True
        self.assertIs(policy._canonical_policy_value()["exact_solver_executable"], False)
        with self.assertRaises(policy.PersonaV2JointSolverPolicyError):
            policy.validate_joint_solver_policy(internal)

    def test_strict_plain_types_unicode_depth_integer_and_size_caps(self):
        class DictSubclass(dict):
            pass

        class ListSubclass(list):
            pass

        invalid_values = (
            None,
            1.0,
            Decimal("1"),
            {"x": 1.0},
            {"x": b"bytes"},
            {"x": (1, 2)},
            {"x": {1, 2}},
            {1: "non-string-key"},
            DictSubclass(x=1),
            ListSubclass([1]),
            {"x": -1},
            {"x": 2**127},
            {"x": "e\u0301"},
            {"e\u0301": "x"},
            {"x": "\ud800"},
            {"\ud800": "x"},
            {"x": "x" * 4_097},
            {"x" * 4_097: "value"},
        )
        for value in invalid_values:
            with self.subTest(value=repr(value)[:80]):
                with self.assertRaises(policy.PersonaV2JointSolverPolicyError):
                    policy.canonical_json_bytes(value)
        self.assertTrue(
            policy.canonical_json_bytes({"x": 2**127 - 1}).startswith(b'{"x":')
        )
        deep = 0
        for _ in range(66):
            deep = [deep]
        with self.assertRaises(policy.PersonaV2JointSolverPolicyError):
            policy.canonical_json_bytes(deep)
        with self.assertRaises(policy.PersonaV2JointSolverPolicyError):
            policy.canonical_json_bytes({"x": ["a" * 4_096] * 129})
        for value in (None, [], True, 1):
            with self.subTest(value=value):
                with self.assertRaises(policy.PersonaV2JointSolverPolicyError):
                    policy.validate_joint_solver_policy(value)

    def test_hash_is_independent_of_hashseed_timezone_and_locale(self):
        code = (
            "from eval import persona_v2_joint_solver_policy as p; "
            "x=p.build_joint_solver_policy(); "
            "print(p.joint_solver_policy_sha256(x),len(p.canonical_json_bytes(x)))"
        )
        expected = f"{EXPECTED_POLICY_SHA256} {EXPECTED_POLICY_BYTES}"
        cases = (
            {"PYTHONHASHSEED": "0", "TZ": "UTC", "LC_ALL": "C"},
            {"PYTHONHASHSEED": "1", "TZ": "Asia/Tokyo", "LC_ALL": "C.UTF-8"},
            {"PYTHONHASHSEED": "42", "TZ": "UTC", "LC_ALL": "C"},
            {"PYTHONHASHSEED": "random", "TZ": "Asia/Tokyo", "LC_ALL": "C.UTF-8"},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                env = os.environ.copy()
                env.update(overrides)
                observed = subprocess.check_output(
                    [sys.executable, "-c", code],
                    cwd=os.path.dirname(os.path.dirname(__file__)),
                    env=env,
                    text=True,
                ).strip()
                self.assertEqual(observed, expected)

    def test_v1_and_bound_v2_artifacts_remain_frozen(self):
        self.assertEqual(v1.SCHEMA_VERSION, 1)
        self.assertEqual(v1.FIXTURE_ID, "kio-persona-pc-v1")
        self.assertEqual(sum(row["full_raw_files"] for row in v1.PERSONAS), 195_000)
        self.assertEqual(envelope.envelope_contract_sha256(), EXPECTED_ENVELOPE_SHA256)
        self.assertEqual(topology.topology_contract_sha256(), EXPECTED_TOPOLOGY_SHA256)
        self.assertEqual(problem.joint_problem_sha256(), EXPECTED_PROBLEM_SHA256)


if __name__ == "__main__":
    unittest.main()
