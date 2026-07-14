import copy
import os
import subprocess
import sys
import unittest

from eval import persona_v2_contract as envelope
from eval import persona_v2_joint_solver_policy as solver_policy
from eval import persona_v2_route_affinity as route
from eval.persona_v2_route_affinity_data import CANDIDATE_ROUTE_SCORE_ROWS


class PersonaV2RouteAffinityTests(unittest.TestCase):
    def setUp(self):
        self.value = route.build_route_affinity()

    def test_identity_shape_hash_size_and_negative_authority_are_exact(self):
        self.assertEqual(
            set(self.value),
            {
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
            },
        )
        self.assertEqual(
            (
                self.value["artifact_schema"],
                self.value["artifact_schema_version"],
                self.value["artifact_kind"],
            ),
            (
                "kcs.persona.pc-route-affinity/v2",
                2,
                "persona-pc-v2-route-affinity-matrix",
            ),
        )
        self.assertEqual(self.value["fixture_id"], envelope.FIXTURE_ID)
        self.assertEqual(
            self.value["fixture_schema_version"], envelope.FIXTURE_SCHEMA_VERSION
        )
        self.assertIs(self.value["g0_contract_frozen"], False)
        self.assertIs(self.value["route_matrix_complete"], True)
        self.assertIn("not-reviewed", self.value["completion_scope"])
        self.assertEqual(
            set(self.value["authority"]),
            {
                "authorizes_g0_freeze",
                "authorizes_solver_execution",
                "authorizes_source_plan",
                "authorizes_write_or_history",
            },
        )
        for name, flag in self.value["authority"].items():
            self.assertIs(type(flag), bool, name)
            self.assertIs(flag, False, name)
        self.assertEqual(
            self.value["envelope_contract_sha256"],
            "6b5c7145881f2ab1e8c84fe033f667757dccf478b704e0731d543bfddfcddbac",
        )
        self.assertEqual(
            self.value["topology_contract_sha256"],
            "fc079fc8e0aaee0ae03a22fee349e0af8f2dfe18e1fed6d8bb05304643e4a958",
        )
        self.assertEqual(
            self.value["joint_problem_sha256"],
            "384c95f550355b63443d7f5ca94dad2ed008ab7b24d6b8148a9504f613c29227",
        )
        self.assertEqual(
            self.value["joint_solver_policy_sha256"],
            "29046b5b5d60d25db51a670e597617bec07b7c4513bded39196bb1053ee52f41",
        )
        raw = route.canonical_json_bytes(self.value)
        self.assertEqual(len(raw), 70_626)
        self.assertLess(len(raw), route.MAX_ROUTE_AFFINITY_BYTES)
        self.assertEqual(
            route.route_affinity_sha256(self.value),
            "ddec88f59165a7b54ce71d87047a8ed4b521e1e1e240bbb08e42bdfc75a2be60",
        )
        self.assertTrue(route.validate_route_affinity(self.value))

    def test_existing_policy_artifact_contract_is_implemented_exactly(self):
        policy = solver_policy.build_joint_solver_policy()
        future = policy["policy"]["route_affinity_future_input"]
        contract = future["artifact_contract"]
        self.assertEqual(contract["artifact_schema"], route.ARTIFACT_SCHEMA)
        self.assertEqual(contract["artifact_kind"], route.ARTIFACT_KIND)
        self.assertEqual(contract["artifact_schema_version"], 2)
        self.assertEqual(
            contract["canonical_limits"]["max_route_affinity_bytes"],
            route.MAX_ROUTE_AFFINITY_BYTES,
        )
        self.assertEqual(set(contract["top_level_fields"]), route.TOP_LEVEL_FIELDS)
        self.assertEqual(set(contract["row_fields"]), route.ROW_FIELDS)
        self.assertEqual(
            set(contract["authority_exact_false_fields"]), route.AUTHORITY_FIELDS
        )
        self.assertEqual(contract["rows_container"], "rows-exact-list-of-541")
        self.assertEqual(future["shape"]["cell_count"], 10_820)
        self.assertEqual(future["shape"]["full_active_persona_variant_rows"], 541)
        self.assertEqual(future["shape"]["scopes_per_row"], 20)
        self.assertEqual(future["cell_domain"], "exact-integer-0-through-4")
        self.assertFalse(future["required_review_receipt_present"])

    def test_validated_policy_axis_mismatch_fails_closed(self):
        policy_value = solver_policy.build_joint_solver_policy()
        policy_rows = route._validated_policy_axis(policy_value)
        envelope_rows = route._envelope_declared_rows()
        self.assertEqual(len(policy_rows), 566)
        route._require_policy_axis_match(envelope_rows, policy_rows)

        mismatched_rows = copy.deepcopy(policy_rows)
        mismatched_rows[0]["family"] = "code"
        with self.assertRaisesRegex(
            route.PersonaV2RouteAffinityError, "differs from the envelope"
        ):
            route._require_policy_axis_match(envelope_rows, mismatched_rows)

        invalid_policy = copy.deepcopy(policy_value)
        invalid_policy["policy"]["axes"]["persona_variant_axes"][0][
            "variant_axis"
        ][0]["family"] = "code"
        with self.assertRaisesRegex(
            route.PersonaV2RouteAffinityError, "bound solver policy is invalid"
        ):
            route._validated_policy_axis(invalid_policy)

    def test_active_projection_order_hard_zeros_and_out_of_domain_are_exact(self):
        declared = []
        for persona_id in envelope.PERSONA_IDS:
            counts = envelope.variant_counts(persona_id, "full")
            for family in envelope.FORMAT_KEYS:
                for item in sorted(
                    counts[family], key=lambda row: row["variant_id"].encode("ascii")
                ):
                    declared.append(
                        (persona_id, family, item["variant_id"], item["count"])
                    )
        active = [row for row in declared if row[3] > 0]
        hard_zero = [row for row in declared if row[3] == 0]
        self.assertEqual(len(declared), 566)
        self.assertEqual(len(active), 541)
        self.assertEqual(len(hard_zero), 25)
        self.assertEqual(20 * 71 - len(declared), 854)
        self.assertEqual(
            [
                (row["persona_id"], row["family"], row["variant_id"])
                for row in self.value["rows"]
            ],
            [(persona_id, family, variant_id) for persona_id, family, variant_id, _ in active],
        )
        self.assertTrue(
            all(
                set(row)
                == {"persona_id", "family", "variant_id", "scores_by_scope_ordinal"}
                for row in self.value["rows"]
            )
        )
        hard_zero_ids = {(persona_id, variant_id) for persona_id, _, variant_id, _ in hard_zero}
        route_ids = {
            (row["persona_id"], row["variant_id"]) for row in self.value["rows"]
        }
        self.assertTrue(hard_zero_ids.isdisjoint(route_ids))
        expected_hard_zero_ids = {("p02", "pdf-scan")}
        expected_hard_zero_ids.update(
            (persona_id, "ipynb")
            for persona_id in (
                "p02", "p03", "p07", "p08", "p09", "p10", "p11", "p12",
                "p13", "p14", "p15", "p17", "p18", "p19", "p20",
            )
        )
        expected_hard_zero_ids.update(
            (persona_id, "mid")
            for persona_id in (
                "p07", "p08", "p09", "p11", "p12", "p15", "p16", "p17", "p20",
            )
        )
        self.assertEqual(hard_zero_ids, expected_hard_zero_ids)

    def test_scores_maxima_clone_secondary_and_scope_coverage_checks_are_exact(self):
        rows = self.value["rows"]
        self.assertEqual(len(rows), 541)
        self.assertEqual(
            sum(len(row["scores_by_scope_ordinal"]) for row in rows), 10_820
        )
        for row in rows:
            scores = row["scores_by_scope_ordinal"]
            self.assertEqual(len(scores), 20)
            self.assertTrue(all(type(score) is int for score in scores))
            self.assertTrue(all(0 <= score <= 4 for score in scores))
            self.assertEqual(max(scores), 4)
            self.assertLessEqual(sum(score == 4 for score in scores), 8)
            self.assertGreaterEqual(sum(score == 4 for score in scores), 1)
        diagnostics = route.candidate_review_diagnostics()
        self.assertEqual(
            diagnostics["score_histogram"],
            {"0": 5_033, "1": 3_099, "2": 1_007, "3": 726, "4": 955},
        )
        self.assertEqual(
            diagnostics["score_zero_semantics"],
            "soft-no-specific-affinity-never-hard-eligibility-ban",
        )
        self.assertFalse(diagnostics["row_maximum_not_four"])
        self.assertFalse(diagnostics["maximum_scope_count_out_of_bounds"])
        self.assertFalse(diagnostics["secondary_only_maximum_rows"])
        self.assertFalse(diagnostics["cross_person_same_variant_vector_clones"])
        self.assertFalse(diagnostics["uncovered_persona_scopes_below_score_two"])
        self.assertEqual(
            diagnostics["persona_scope_minimums"],
            [
                {"minimum_of_scope_maxima": 2, "persona_id": persona_id}
                for persona_id in envelope.PERSONA_IDS
            ],
        )
        self.assertIs(diagnostics["review_receipt_present"], False)
        self.assertIs(diagnostics["independent_review_complete"], False)

    def test_semantic_primary_format_anchors_are_preserved(self):
        by_identity = {
            (row["persona_id"], row["variant_id"]): row[
                "scores_by_scope_ordinal"
            ]
            for row in self.value["rows"]
        }
        expected_maximum_scopes = {
            ("p08", "docx"): (1, 4),
            ("p12", "markdown"): (2, 7, 9),
            ("p12", "md"): (2, 7, 9),
            ("p15", "docx"): (2, 4),
            ("p18", "xlsx"): (1, 4),
        }
        for identity, scope_ordinals in expected_maximum_scopes.items():
            with self.subTest(identity=identity):
                scores = by_identity[identity]
                self.assertTrue(
                    all(scores[ordinal - 1] == 4 for ordinal in scope_ordinals)
                )

    def test_literal_data_is_complete_compact_and_builds_detached_values(self):
        self.assertIs(type(CANDIDATE_ROUTE_SCORE_ROWS), tuple)
        self.assertEqual(tuple(row[0] for row in CANDIDATE_ROUTE_SCORE_ROWS), envelope.PERSONA_IDS)
        literal_rows = [
            (persona_id, variant_id, scores)
            for persona_id, variants in CANDIDATE_ROUTE_SCORE_ROWS
            for variant_id, scores in variants
        ]
        self.assertEqual(len(literal_rows), 541)
        for persona_id, variant_id, scores in literal_rows:
            self.assertIs(type(persona_id), str)
            self.assertIs(type(variant_id), str)
            self.assertIs(type(scores), str)
            self.assertEqual(len(scores), 20)
            self.assertTrue(set(scores) <= set("01234"))

        first = route.build_route_affinity()
        first["rows"][0]["scores_by_scope_ordinal"][0] = 0
        first["authority"]["authorizes_g0_freeze"] = True
        second = route.build_route_affinity()
        self.assertNotEqual(first, second)
        self.assertIs(second["authority"]["authorizes_g0_freeze"], False)
        self.assertEqual(second, self.value)

    def test_exact_regeneration_rejects_mutation_type_alias_and_extra_fields(self):
        mutations = []

        changed_score = copy.deepcopy(self.value)
        changed_score["rows"][0]["scores_by_scope_ordinal"][0] = 3
        mutations.append(changed_score)

        bool_score = copy.deepcopy(self.value)
        bool_score["rows"][0]["scores_by_scope_ordinal"][0] = True
        mutations.append(bool_score)

        missing_row = copy.deepcopy(self.value)
        missing_row["rows"].pop()
        mutations.append(missing_row)

        reordered = copy.deepcopy(self.value)
        reordered["rows"][0], reordered["rows"][1] = (
            reordered["rows"][1],
            reordered["rows"][0],
        )
        mutations.append(reordered)

        authorizing = copy.deepcopy(self.value)
        authorizing["authority"]["authorizes_solver_execution"] = True
        mutations.append(authorizing)

        reviewed = copy.deepcopy(self.value)
        reviewed["review_receipt_present"] = True
        mutations.append(reviewed)

        downstream_hash = copy.deepcopy(self.value)
        downstream_hash["source_plan_sha256"] = "0" * 64
        mutations.append(downstream_hash)

        for candidate in mutations:
            with self.subTest(candidate=set(candidate) - set(self.value)):
                with self.assertRaises(route.PersonaV2RouteAffinityError):
                    route.validate_route_affinity(candidate)

    def test_review_and_execution_boundary_fails_closed(self):
        with self.assertRaisesRegex(
            route.PersonaV2RouteAffinityError, "independent human-review receipt"
        ):
            route.require_independently_reviewed_route_affinity()

    def test_hash_is_stable_across_python_hash_seeds(self):
        code = (
            "from eval.persona_v2_route_affinity import route_affinity_sha256; "
            "print(route_affinity_sha256())"
        )
        outputs = []
        for seed in ("1", "777"):
            env = os.environ.copy()
            env["PYTHONHASHSEED"] = seed
            outputs.append(
                subprocess.check_output(
                    [sys.executable, "-c", code],
                    cwd=os.path.dirname(os.path.dirname(__file__)),
                    env=env,
                    text=True,
                ).strip()
            )
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[0], route.route_affinity_sha256())


if __name__ == "__main__":
    unittest.main()
