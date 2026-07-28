import copy
import json
import os
import subprocess
import sys
import unittest

from eval import persona_fixture_spec as v1
from eval import persona_v2_contract as envelope
from eval import persona_v2_joint_problem as problem
from eval import persona_v2_topology as topology


EXPECTED_ENVELOPE_SHA256 = "12a5f175cbcd9b1ea9886c8a8e3b673b857f6b314ba48c9b71e6b279150244a7"
EXPECTED_TOPOLOGY_SHA256 = "02e0e68d37378a1123743673aad826757d17480de77a5a7313f09932c5759c4a"
EXPECTED_PROBLEM_SHA256 = "f76a2b8ae5557a45af2c4e758b1f2b7663809ef80d7f33987abe3f5e9fc17207"
EXPECTED_PROBLEM_BYTES = 744_137


def _profile(persona, profile):
    return next(row for row in persona["profiles"] if row["profile"] == profile)


def _by_key(rows, key):
    return {row[key]: row for row in rows}


class PersonaV2JointProblemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = problem.build_joint_problem()

    def test_identity_bindings_and_negative_authority_are_exact(self):
        value = self.value
        self.assertEqual(value["artifact_schema"], "kio.persona.pc-joint-problem/v2")
        self.assertEqual(value["artifact_schema_version"], 2)
        self.assertEqual(
            value["artifact_kind"],
            "persona-pc-v2-joint-allocation-problem",
        )
        self.assertEqual(value["fixture_id"], "kio-persona-pc-v2")
        self.assertEqual(value["fixture_schema_version"], 2)
        self.assertEqual(value["envelope_contract_sha256"], EXPECTED_ENVELOPE_SHA256)
        self.assertEqual(value["topology_contract_sha256"], EXPECTED_TOPOLOGY_SHA256)
        self.assertEqual(value["envelope_contract_sha256"], envelope.envelope_contract_sha256())
        self.assertEqual(value["topology_contract_sha256"], topology.topology_contract_sha256())
        self.assertEqual(value["completion_scope"], problem.COMPLETION_SCOPE)
        self.assertFalse(value["g0_contract_frozen"])
        self.assertFalse(value["joint_allocation_proved"])
        self.assertTrue(value["necessary_feasibility_all_pass"])
        self.assertTrue(value["suite_index"]["necessary_feasibility_all_pass"])
        self.assertTrue(value["authority"])
        self.assertTrue(
            all(type(claim) is bool and claim is False for claim in value["authority"].values())
        )
        self.assertEqual(
            value["proof_status"],
            {
                "incidental_wave_budget_proved": False,
                "joint_allocation_geometry_proved": False,
                "joint_allocation_proved_for_g0": False,
                "necessary_marginal_inputs_bound": True,
                "solver_policy_bound": False,
                "source_recipe_bound": False,
            },
        )
        self.assertIn(
            "joint_scope_variant_density_quota_solver_missing",
            value["remaining_g0_blockers"],
        )
        self.assertIn(
            "persona_fidelity_realism_profile_and_overlay_missing",
            value["remaining_g0_blockers"],
        )
        self.assertEqual(
            value["policy"]["canonical_limits"]["max_joint_problem_bytes"],
            4 * 2**20,
        )
        self.assertEqual(
            value["policy"]["pilot_embedding_status"],
            "coordinatewise-nonnegative-residual-only-not-source-subset-proof",
        )
        with self.assertRaisesRegex(problem.PersonaV2JointProblemError, "no exact allocation"):
            problem.require_joint_allocation_solution()

    def test_all_twenty_persona_profile_marginals_are_exact(self):
        self.assertEqual(
            tuple(row["persona_id"] for row in self.value["personas"]),
            envelope.PERSONA_IDS,
        )
        self.assertEqual(self.value["suite_index"]["persona_order"], list(envelope.PERSONA_IDS))
        self.assertEqual(
            self.value["suite_index"]["profile_order"],
            ["pilot", "full", "full-minus-pilot"],
        )
        for persona in self.value["personas"]:
            persona_id = persona["persona_id"]
            self.assertEqual(tuple(row["profile"] for row in persona["profiles"]), ("pilot", "full"))
            self.assertEqual(persona["role"], envelope.get_persona(persona_id)["role"])
            for profile_name in ("pilot", "full"):
                with self.subTest(persona=persona_id, profile=profile_name):
                    row = _profile(persona, profile_name)
                    self.assertTrue(row["necessary_feasibility"]["all_checks_pass"])
                    self.assertEqual(row["necessary_feasibility"]["failed_check_ids"], [])
                    self.assertEqual(
                        row["physical_file_count"],
                        envelope.profile_file_count(persona_id, profile_name),
                    )
                    self.assertEqual(
                        row["contributor_source_count"],
                        envelope.contributor_count(persona_id, profile_name),
                    )
                    expected_chunks = 12_000 if profile_name == "pilot" else 120_000
                    self.assertEqual(row["target_contract_contributor_chunks"], expected_chunks)
                    self.assertEqual(len(row["scope_marginals"]), 20)
                    self.assertEqual(
                        tuple(scope["scope_key"] for scope in row["scope_marginals"]),
                        tuple(
                            scope["scope_key"]
                            for scope in topology.get_persona_topology(persona_id)["scopes"]
                        ),
                    )
                    self.assertEqual(
                        tuple(scope["physical_file_count"] for scope in row["scope_marginals"]),
                        topology.project_physical_files(persona_id, profile_name),
                    )
                    self.assertEqual(
                        tuple(scope["contributor_chunk_count"] for scope in row["scope_marginals"]),
                        topology.project_contributor_chunks(persona_id, profile_name),
                    )
                    expected_variants = envelope.variant_counts(persona_id, profile_name)
                    self.assertEqual(
                        tuple(family["family"] for family in row["family_variant_marginals"]),
                        envelope.FORMAT_KEYS,
                    )
                    for family in row["family_variant_marginals"]:
                        self.assertEqual(
                            [
                                (variant["variant_id"], variant["file_count"], variant["gate_role"])
                                for variant in family["variants"]
                            ],
                            [
                                (variant["variant_id"], variant["count"], variant["gate_role"])
                                for variant in expected_variants[family["family"]]
                            ],
                        )
                    self.assertEqual(
                        tuple(
                            density["contributor_source_count"]
                            for density in row["density_bucket_marginals"]
                        ),
                        tuple(envelope.density_bucket_counts(persona_id, profile_name).values()),
                    )
                    self.assertEqual(
                        {
                            cohort["cohort_id"]: cohort["contract_contributor_chunks"]
                            for cohort in row["history_cohort_chunk_marginals"]
                        },
                        envelope.history_cohort_chunk_counts(profile_name),
                    )

        expected_dense_office = {
            "p08": {
                "pilot_sources": 267,
                "full_sources": 2_672,
                "pilot_density": (3, 11, 53, 200),
                "full_density": (27, 107, 534, 2_004),
            },
            "p11": {
                "pilot_sources": 268,
                "full_sources": 2_680,
                "pilot_density": (3, 11, 53, 201),
                "full_density": (27, 107, 536, 2_010),
            },
            "p15": {
                "pilot_sources": 268,
                "full_sources": 2_680,
                "pilot_density": (3, 11, 53, 201),
                "full_density": (27, 107, 536, 2_010),
            },
            "p17": {
                "pilot_sources": 267,
                "full_sources": 2_672,
                "pilot_density": (3, 11, 53, 200),
                "full_density": (27, 107, 534, 2_004),
            },
        }
        for persona_id, expected in expected_dense_office.items():
            persona = problem.get_persona_problem(persona_id)
            self.assertEqual(
                _profile(persona, "pilot")["contributor_source_count"],
                expected["pilot_sources"],
            )
            self.assertEqual(
                _profile(persona, "full")["contributor_source_count"],
                expected["full_sources"],
            )
            self.assertEqual(
                tuple(
                    row["contributor_source_count"]
                    for row in _profile(persona, "pilot")["density_bucket_marginals"]
                ),
                expected["pilot_density"],
            )
            self.assertEqual(
                tuple(
                    row["contributor_source_count"]
                    for row in _profile(persona, "full")["density_bucket_marginals"]
                ),
                expected["full_density"],
            )
        self.assertEqual(envelope.get_persona("p08")["format_percentages"]["md"], 14)
        self.assertEqual(
            envelope.get_persona("p08")["format_percentages"]["domain_binary"], 1
        )
        self.assertEqual(envelope.get_persona("p17")["format_percentages"]["md"], 7)
        self.assertEqual(
            envelope.get_persona("p17")["format_percentages"]["domain_binary"], 12
        )

    def test_necessary_checks_reject_projection_conservation_drift(self):
        profile = _profile(problem.get_persona_problem("p01"), "pilot")
        common = {
            "physical_file_count": profile["physical_file_count"],
            "contributor_source_count": profile["contributor_source_count"],
            "target_chunks": profile["target_contract_contributor_chunks"],
            "gate_role_rows": profile["gate_role_counts"],
            "density_rows": profile["density_bucket_marginals"],
            "history_rows": profile["history_cohort_chunk_marginals"],
            "required_scope_coverage": True,
        }

        bad_scopes = copy.deepcopy(profile["scope_marginals"])
        bad_scopes[0]["physical_file_count"] += 1
        scope_result = problem._necessary_feasibility(
            variant_rows=profile["family_variant_marginals"],
            scope_rows=bad_scopes,
            **common,
        )
        scope_checks = _by_key(scope_result["checks"], "check_id")
        self.assertFalse(scope_result["all_checks_pass"])
        self.assertFalse(
            scope_checks[
                "scope-physical-file-count-sums-to-profile-physical-total"
            ]["passed"]
        )

        bad_variants = copy.deepcopy(profile["family_variant_marginals"])
        bad_variants[0]["variants"][0]["file_count"] += 1
        variant_result = problem._necessary_feasibility(
            variant_rows=bad_variants,
            scope_rows=profile["scope_marginals"],
            **common,
        )
        variant_checks = _by_key(variant_result["checks"], "check_id")
        self.assertFalse(variant_result["all_checks_pass"])
        self.assertFalse(
            variant_checks[
                "nested-variant-file-counts-match-family-marginals"
            ]["passed"]
        )

    def test_whole_source_cohort_lower_is_independent_and_regressed(self):
        expected = {
            "pilot": {"P": 20, "X": 20, "Y": 20, "N": 20, "U": 131},
            "full": {"P": 69, "X": 172, "Y": 103, "N": 69, "U": 1_303},
        }
        minimum_headroom = {}
        for profile_name in ("pilot", "full"):
            chunks = envelope.history_cohort_chunk_counts(profile_name)
            independently_derived = {
                cohort: max(
                    20 if cohort in ("P", "X", "Y", "N") else 0,
                    (chunks[cohort] + 69) // 70,
                )
                for cohort in ("P", "X", "Y", "N", "U")
            }
            self.assertEqual(independently_derived, expected[profile_name])
            for persona_id in envelope.PERSONA_IDS:
                count = envelope.contributor_count(persona_id, profile_name)
                self.assertGreaterEqual(count, sum(independently_derived.values()))
                headroom = count - sum(independently_derived.values())
                minimum_headroom[profile_name] = min(
                    minimum_headroom.get(profile_name, headroom), headroom
                )
                feasibility = _profile(
                    problem.get_persona_problem(persona_id), profile_name
                )["necessary_feasibility"]["cohort_source_interval"]
                self.assertEqual(feasibility["lower_bound"], sum(independently_derived.values()))
                self.assertEqual(feasibility["lower_headroom"], headroom)
                self.assertEqual(
                    {
                        row["cohort_id"]: row["necessary_source_lower_bound"]
                        for row in feasibility["per_cohort"]
                    },
                    independently_derived,
                )
        self.assertEqual(minimum_headroom, {"pilot": 27, "full": 664})
        self.assertLess(203, sum(expected["pilot"].values()))
        expected_dense_office_headrooms = {
            "p08": (56, 956),
            "p11": (57, 964),
            "p15": (57, 964),
            "p17": (56, 956),
        }
        for persona_id, (pilot_headroom, full_headroom) in (
            expected_dense_office_headrooms.items()
        ):
            pilot_feasibility = _profile(
                problem.get_persona_problem(persona_id), "pilot"
            )["necessary_feasibility"]["cohort_source_interval"]
            self.assertEqual(pilot_feasibility["lower_bound"], 211)
            self.assertEqual(pilot_feasibility["lower_headroom"], pilot_headroom)
            full_feasibility = _profile(
                problem.get_persona_problem(persona_id), "full"
            )["necessary_feasibility"]["cohort_source_interval"]
            self.assertEqual(full_feasibility["lower_bound"], 1_716)
            self.assertEqual(full_feasibility["lower_headroom"], full_headroom)

    def test_full_minus_pilot_residual_is_exact_and_nonnegative(self):
        expected_cohort_residual = {
            "P": 4_320,
            "X": 10_800,
            "Y": 6_480,
            "N": 4_320,
            "U": 82_080,
        }
        for persona in self.value["personas"]:
            pilot = _profile(persona, "pilot")
            full = _profile(persona, "full")
            residual = persona["full_minus_pilot_residual"]
            self.assertEqual(residual["profile"], "full-minus-pilot")
            self.assertTrue(residual["necessary_feasibility"]["all_checks_pass"])
            self.assertTrue(persona["cross_profile_necessary_checks"]["all_checks_pass"])
            self.assertEqual(residual["physical_file_count"], full["physical_file_count"] - pilot["physical_file_count"])
            self.assertEqual(residual["contributor_source_count"], full["contributor_source_count"] - pilot["contributor_source_count"])
            self.assertEqual(residual["target_contract_contributor_chunks"], 108_000)
            self.assertEqual(
                {
                    row["cohort_id"]: row["contract_contributor_chunks"]
                    for row in residual["history_cohort_chunk_marginals"]
                },
                expected_cohort_residual,
            )
            for full_family, pilot_family, residual_family in zip(
                full["family_variant_marginals"],
                pilot["family_variant_marginals"],
                residual["family_variant_marginals"],
            ):
                self.assertEqual(
                    residual_family["file_count"],
                    full_family["file_count"] - pilot_family["file_count"],
                )
                for full_variant, pilot_variant, residual_variant in zip(
                    full_family["variants"],
                    pilot_family["variants"],
                    residual_family["variants"],
                ):
                    self.assertEqual(
                        residual_variant["file_count"],
                        full_variant["file_count"] - pilot_variant["file_count"],
                    )
                    self.assertGreaterEqual(residual_variant["file_count"], 0)
            for key, count_field in (
                ("gate_role", "file_count"),
                ("bucket_id", "contributor_source_count"),
                ("cohort_id", "contract_contributor_chunks"),
            ):
                full_rows = _by_key(
                    full[
                        {
                            "gate_role": "gate_role_counts",
                            "bucket_id": "density_bucket_marginals",
                            "cohort_id": "history_cohort_chunk_marginals",
                        }[key]
                    ],
                    key,
                )
                pilot_rows = _by_key(
                    pilot[
                        {
                            "gate_role": "gate_role_counts",
                            "bucket_id": "density_bucket_marginals",
                            "cohort_id": "history_cohort_chunk_marginals",
                        }[key]
                    ],
                    key,
                )
                residual_rows = _by_key(
                    residual[
                        {
                            "gate_role": "gate_role_counts",
                            "bucket_id": "density_bucket_marginals",
                            "cohort_id": "history_cohort_chunk_marginals",
                        }[key]
                    ],
                    key,
                )
                self.assertEqual(tuple(full_rows), tuple(pilot_rows))
                self.assertEqual(tuple(full_rows), tuple(residual_rows))
                for row_key in full_rows:
                    self.assertEqual(
                        residual_rows[row_key][count_field],
                        full_rows[row_key][count_field]
                        - pilot_rows[row_key][count_field],
                    )
                    self.assertGreaterEqual(residual_rows[row_key][count_field], 0)
            for full_scope, pilot_scope, residual_scope in zip(
                full["scope_marginals"],
                pilot["scope_marginals"],
                residual["scope_marginals"],
            ):
                self.assertEqual(
                    residual_scope["physical_file_count"],
                    full_scope["physical_file_count"]
                    - pilot_scope["physical_file_count"],
                )
                self.assertEqual(
                    residual_scope["contributor_chunk_count"],
                    full_scope["contributor_chunk_count"]
                    - pilot_scope["contributor_chunk_count"],
                )
                self.assertGreaterEqual(residual_scope["physical_file_count"], 0)
                self.assertGreaterEqual(residual_scope["contributor_chunk_count"], 0)

        suite = {row["profile"]: row for row in self.value["suite_index"]["profiles"]}
        self.assertEqual(suite["pilot"]["physical_files"], 20_300)
        self.assertEqual(suite["full"]["physical_files"], 203_000)
        self.assertEqual(suite["full-minus-pilot"]["physical_files"], 182_700)
        self.assertEqual(suite["pilot"]["contract_contributor_sources"], 6_925)
        self.assertEqual(suite["full"]["contract_contributor_sources"], 69_236)
        self.assertEqual(suite["full-minus-pilot"]["contract_contributor_sources"], 62_311)
        self.assertEqual(
            suite["pilot"]["density_bucket_source_counts"],
            {"1-4": 731, "5-20": 1_707, "21-50": 2_498, "51-70": 1_989},
        )
        self.assertEqual(
            suite["full"]["density_bucket_source_counts"],
            {"1-4": 7_300, "5-20": 17_042, "21-50": 24_995, "51-70": 19_899},
        )
        self.assertEqual(
            suite["full-minus-pilot"]["density_bucket_source_counts"],
            {"1-4": 6_569, "5-20": 15_335, "21-50": 22_497, "51-70": 17_910},
        )
        self.assertEqual(
            suite["pilot"]["gate_role_file_counts"],
            {"contract_contributor": 6_925, "incidental_searchable": 6_040, "raw_only": 7_335},
        )
        self.assertEqual(
            suite["full"]["gate_role_file_counts"],
            {"contract_contributor": 69_236, "incidental_searchable": 60_414, "raw_only": 73_350},
        )
        self.assertEqual(
            suite["full-minus-pilot"]["gate_role_file_counts"],
            {"contract_contributor": 62_311, "incidental_searchable": 54_374, "raw_only": 66_015},
        )
        self.assertEqual(
            suite["full-minus-pilot"]["contract_contributor_chunks"], 2_160_000
        )

    def test_canonical_rebuild_hash_size_and_balanced_tamper_rejection(self):
        first = problem.build_joint_problem()
        second = problem.build_joint_problem()
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        raw = problem.canonical_json_bytes(first)
        self.assertEqual(len(raw), EXPECTED_PROBLEM_BYTES)
        self.assertEqual(problem.joint_problem_sha256(first), EXPECTED_PROBLEM_SHA256)
        self.assertEqual(json.loads(raw), first)
        self.assertTrue(problem.validate_joint_problem(first))

        mutations = []

        def balanced_scope(value):
            rows = value["personas"][0]["profiles"][0]["scope_marginals"]
            rows[0]["physical_file_count"] += 1
            rows[1]["physical_file_count"] -= 1

        mutations.extend(
            (
                balanced_scope,
                lambda value: value["personas"].reverse(),
                lambda value: value.__setitem__("envelope_contract_sha256", "0" * 64),
                lambda value: value["authority"].__setitem__("authorizes_physical_write", True),
                lambda value: value["authority"].__setitem__("authorizes_physical_write", 0),
                lambda value: value["personas"][0]["profiles"][0].__setitem__("physical_file_count", True),
                lambda value: value.__setitem__("unknown", False),
            )
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                changed = copy.deepcopy(first)
                mutate(changed)
                with self.assertRaises(problem.PersonaV2JointProblemError):
                    problem.validate_joint_problem(changed)
                with self.assertRaises(problem.PersonaV2JointProblemError):
                    problem.joint_problem_sha256(changed)

    def test_strict_canonical_limits_and_public_detachment(self):
        for value in (
            1.0,
            {"x": 1.0},
            {"x": b"bytes"},
            {"x": {1: "non-string-key"}},
            {"x": (1, 2)},
        ):
            with self.subTest(value=value):
                with self.assertRaises(problem.PersonaV2JointProblemError):
                    problem.canonical_json_bytes(value)
        with self.assertRaises(problem.PersonaV2JointProblemError):
            problem.canonical_json_bytes({"x": "e\u0301"})
        with self.assertRaises(problem.PersonaV2JointProblemError):
            problem.canonical_json_bytes({"x": "x" * 4_097})
        deep = 0
        for _ in range(66):
            deep = [deep]
        with self.assertRaises(problem.PersonaV2JointProblemError):
            problem.canonical_json_bytes(deep)
        with self.assertRaises(problem.PersonaV2JointProblemError):
            problem.canonical_json_bytes(["x" * 4_096] * 1_025)
        for persona_id in (True, 1, "p21", None):
            with self.subTest(persona_id=persona_id):
                with self.assertRaises(problem.PersonaV2JointProblemError):
                    problem.get_persona_problem(persona_id)

        detached = problem.build_joint_problem()
        detached["personas"][0]["profiles"][0]["scope_marginals"][0]["scope_key"] = "changed"
        self.assertNotEqual(
            problem.build_joint_problem()["personas"][0]["profiles"][0]["scope_marginals"][0]["scope_key"],
            "changed",
        )
        persona = problem.get_persona_problem("p01")
        persona["profiles"][0]["scope_marginals"][0]["scope_key"] = "changed"
        self.assertNotEqual(
            problem.get_persona_problem("p01")["profiles"][0]["scope_marginals"][0]["scope_key"],
            "changed",
        )

    def test_hash_is_independent_of_hashseed_timezone_and_locale(self):
        code = (
            "from eval import persona_v2_joint_problem as p; "
            "x=p.build_joint_problem(); "
            "print(p.joint_problem_sha256(x),len(p.canonical_json_bytes(x)))"
        )
        expected = f"{EXPECTED_PROBLEM_SHA256} {EXPECTED_PROBLEM_BYTES}"
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

    def test_v1_identity_and_cardinality_remain_frozen(self):
        self.assertEqual(v1.SCHEMA_VERSION, 1)
        self.assertEqual(v1.FIXTURE_ID, "kio-persona-pc-v1")
        self.assertEqual(sum(row["full_raw_files"] for row in v1.PERSONAS), 195_000)


if __name__ == "__main__":
    unittest.main()
