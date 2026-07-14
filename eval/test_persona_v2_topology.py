import copy
import math
import unittest

from eval import persona_fixture_spec as v1
from eval import persona_v2_contract as envelope
from eval import persona_v2_topology as topology


EXPECTED_TOPOLOGY_SHA256 = "204c9a136438c0dfff3718549c2fcb6009e6ccbe9debdd0cfe54bfaa4290b68f"


def _independent_hamilton(total, weights):
    denominator = sum(weights)
    floors = [total * weight // denominator for weight in weights]
    missing = total - sum(floors)
    order = sorted(
        range(len(weights)),
        key=lambda index: (-(total * weights[index] % denominator), index),
    )
    for index in order[:missing]:
        floors[index] += 1
    return tuple(floors)


class PersonaV2TopologyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = topology.build_topology_contract()

    def test_identity_counts_and_negative_authority_are_exact(self):
        value = self.contract
        self.assertEqual(value["artifact_schema"], "kcs.persona.pc-topology/v2")
        self.assertEqual(value["artifact_schema_version"], 2)
        self.assertEqual(value["artifact_kind"], "persona-pc-v2-topology")
        self.assertEqual(value["fixture_id"], "kcs-persona-pc-v2")
        self.assertEqual(value["fixture_schema_version"], 2)
        self.assertEqual(value["envelope_contract_sha256"], envelope.envelope_contract_sha256())
        self.assertTrue(value["topology_complete"])
        self.assertEqual(value["completion_scope"], "exact-topology-only-not-g0-root")
        self.assertFalse(value["g0_contract_frozen"])
        expected_authority = copy.deepcopy(envelope.build_envelope_contract()["authority"])
        expected_authority["activity_unit_review_receipt_bound"] = False
        expected_authority["joint_allocation_proved"] = False
        self.assertEqual(value["authority"], expected_authority)
        self.assertEqual(len(value["personas"]), 20)
        self.assertEqual(
            tuple(persona["persona_id"] for persona in value["personas"]),
            envelope.PERSONA_IDS,
        )
        self.assertEqual(sum(len(persona["scopes"]) for persona in value["personas"]), 400)
        self.assertEqual(
            value["policy"]["load_units_status"],
            "authored-stress-design-hypothesis-not-observed-statistics",
        )
        self.assertEqual(
            value["policy"]["activity_unit_rubric"],
            {
                "bands": [
                    {"id": "low", "max": 39, "min": 1},
                    {"id": "moderate", "max": 59, "min": 40},
                    {"id": "high", "max": 79, "min": 60},
                    {"id": "very-high", "max": 100, "min": 80},
                ],
                "contributor_dimension": (
                    "relative contract-chunk demand within one persona and scope kind"
                ),
                "physical_dimension": (
                    "relative file creation-import-retention pressure within one persona and scope kind"
                ),
                "scale_max": 100,
                "scale_min": 1,
                "status": "authored-hypothesis-not-observed-or-empirically-calibrated",
                "within_band_precision": (
                    "canonical authored interpolation only, not measurement"
                ),
            },
        )
        self.assertEqual(
            value["policy"]["weight_normalization"],
            {
                "algorithm_id": "per-scope-floor-then-hamilton-residual-v1",
                "formula": (
                    "weight_i=minimum_bp+hamilton(group_bp-(minimum_bp*scope_count),activity_units)_i"
                ),
                "residual_apportionment_algorithm_id": "hamilton-largest-remainder-v1",
                "tie_break": "descending-fractional-remainder-then-input-ordinal",
            },
        )
        self.assertEqual(
            value["policy"]["profile_projection"],
            {
                "algorithm_id": "group-subtotal-hamilton-v1",
                "tie_break": "descending-fractional-remainder-then-input-ordinal",
            },
        )
        self.assertEqual(
            value["policy"]["source_bound"],
            {
                "global_cohort_lower_formula": (
                    "sum(max(required_scope_count_if_covered_else_zero,"
                    "ceil(cohort_chunks/max_chunks_per_source)))"
                ),
                "lower_formula": (
                    "max(required_cohort_count,ceil(scope_chunks/max_chunks_per_source))"
                ),
                "max_chunks_per_source": 70,
                "profile_global_cohort_source_minimum": {
                    "pilot": 211,
                    "full": 1_716,
                },
                "required_cohorts_with_positive_source_per_scope": ["P", "X", "Y", "N"],
                "required_cohort_count": 4,
                "upper_formula": "min(scope_chunks,scope_physical_files)",
            },
        )
        self.assertEqual(
            value["policy"]["source_bound"][
                "required_cohorts_with_positive_source_per_scope"
            ],
            envelope.build_envelope_contract()["history_cohort_contract"][
                "coverage_required_in_all_twenty_scopes"
            ],
        )
        self.assertEqual(
            topology.SCOPE_ROW_FIELDS,
            (
                "functional_slot",
                "relative_path",
                "physical_activity_units",
                "contributor_demand_units",
                "load_basis_id",
            ),
        )
        self.assertEqual(
            value["policy"]["canonical_limits"],
            {
                "max_component_bytes": 80,
                "max_load_basis_id_bytes": 80,
                "max_path_bytes": 240,
                "max_slot_bytes": 80,
                "max_topology_bytes": 512 * 1024,
            },
        )
        self.assertEqual(
            value["remaining_g0_blockers"],
            envelope.build_envelope_contract()["blockers"]
            + ["activity_unit_rubric_review_receipt_not_bound"],
        )
        self.assertEqual(
            value["policy"]["activity_unit_review"],
            {"receipt_bound": False, "required_for_g0_freeze": True},
        )
        self.assertEqual(
            value["policy"]["within_persona_path_safety"],
            {
                "ancestor_relationships_forbidden": True,
                "casefold_unique_paths": True,
            },
        )
        self.assertEqual(
            value["policy"]["cross_persona_diversity"]["purpose"],
            "anti-template synthetic diversity across independent roots",
        )

    def test_scope_order_paths_representatives_and_dmax_are_exact(self):
        all_paths = []
        all_scope_keys = []
        secondary_paths = []
        for persona in self.contract["personas"]:
            persona_id = persona["persona_id"]
            metadata = envelope.get_persona(persona_id)
            scopes = persona["scopes"]
            self.assertEqual(len(scopes), 20)
            self.assertEqual(tuple(row["ordinal"] for row in scopes), tuple(range(1, 21)))
            self.assertEqual(tuple(row["kind"] for row in scopes[:12]), ("primary",) * 12)
            self.assertEqual(tuple(row["kind"] for row in scopes[12:]), ("secondary",) * 8)
            self.assertEqual(
                tuple(row["functional_slot"] for row in scopes[12:]),
                topology.SECONDARY_FUNCTIONAL_SLOTS,
            )
            self.assertEqual(
                tuple(row["scope_key"] for row in scopes),
                tuple(f"{persona_id}-scope-{ordinal:02d}" for ordinal in range(1, 21)),
            )
            self.assertEqual(
                len({row["functional_slot"] for row in scopes}),
                topology.SCOPES_PER_PERSONA,
            )
            primary_paths = {row["relative_path"] for row in scopes[:12]}
            secondary_scope_paths = {row["relative_path"] for row in scopes[12:]}
            self.assertIn(metadata["representative_primary_scope"], primary_paths)
            self.assertIn(metadata["representative_secondary_scope"], secondary_scope_paths)
            self.assertEqual(persona["formal_dmax"], metadata["formal_dmax"])
            self.assertEqual(persona["realized_dmax"], metadata["formal_dmax"])
            self.assertTrue(
                any(len(row["relative_path"].split("/")) == metadata["formal_dmax"] for row in scopes)
            )
            all_paths.extend(row["relative_path"] for row in scopes)
            all_scope_keys.extend(row["scope_key"] for row in scopes)
            secondary_paths.extend(row["relative_path"] for row in scopes[12:])
        self.assertEqual(len(all_paths), len({path.casefold() for path in all_paths}))
        self.assertEqual(len(all_scope_keys), len(set(all_scope_keys)))
        self.assertEqual(len(secondary_paths), 160)
        self.assertEqual(len(secondary_paths), len({path.casefold() for path in secondary_paths}))
        path_parts = [tuple(path.split("/")) for path in all_paths]
        for index, left in enumerate(path_parts):
            for right in path_parts[index + 1:]:
                self.assertFalse(
                    (len(left) < len(right) and right[:len(left)] == left)
                    or (len(right) < len(left) and left[:len(right)] == right)
                )

    def test_authored_load_vectors_are_separate_exact_and_not_clones(self):
        physical_vectors = []
        contributor_vectors = []
        for persona in self.contract["personas"]:
            scopes = persona["scopes"]
            physical = tuple(row["physical_file_weight_bp"] for row in scopes)
            contributor = tuple(row["contributor_chunk_weight_bp"] for row in scopes)
            physical_vectors.append(physical)
            contributor_vectors.append(contributor)
            self.assertEqual(sum(physical), 10_000)
            self.assertEqual(sum(contributor), 10_000)
            self.assertEqual(sum(physical[:12]), persona["primary_share_bp"])
            self.assertEqual(sum(contributor[:12]), persona["primary_share_bp"])
            self.assertTrue(all(value >= topology.PHYSICAL_MINIMUM_BP for value in physical))
            self.assertTrue(all(value >= topology.CONTRIBUTOR_MINIMUM_BP for value in contributor))
            self.assertNotEqual(physical, contributor)
            self.assertTrue(
                all(
                    topology.ACTIVITY_UNIT_MINIMUM
                    <= row["physical_activity_units"]
                    <= topology.ACTIVITY_UNIT_MAXIMUM
                    for row in scopes
                )
            )
            self.assertTrue(
                all(
                    topology.ACTIVITY_UNIT_MINIMUM
                    <= row["contributor_demand_units"]
                    <= topology.ACTIVITY_UNIT_MAXIMUM
                    for row in scopes
                )
            )
        self.assertEqual(len(physical_vectors), len(set(physical_vectors)))
        self.assertEqual(len(contributor_vectors), len(set(contributor_vectors)))
        self.assertEqual(
            len(physical_vectors),
            len({tuple(sorted(vector)) for vector in physical_vectors}),
        )
        self.assertEqual(
            len(contributor_vectors),
            len({tuple(sorted(vector)) for vector in contributor_vectors}),
        )

    def test_profile_projections_and_source_bounds_are_exact(self):
        for persona_id in envelope.PERSONA_IDS:
            persona = topology.get_persona_topology(persona_id)
            for profile in ("tiny-smoke", "pilot", "full"):
                physical = topology.project_physical_files(persona_id, profile)
                expected_total = envelope.profile_file_count(persona_id, profile)
                expected_primary_total = (
                    expected_total * persona["primary_share_bp"] // 10_000
                )
                expected_physical = (
                    _independent_hamilton(
                        expected_primary_total,
                        tuple(
                            row["physical_file_weight_bp"]
                            for row in persona["scopes"][:12]
                        ),
                    )
                    + _independent_hamilton(
                        expected_total - expected_primary_total,
                        tuple(
                            row["physical_file_weight_bp"]
                            for row in persona["scopes"][12:]
                        ),
                    )
                )
                self.assertEqual(physical, expected_physical)
                self.assertEqual(sum(physical), expected_total)
                self.assertEqual(
                    sum(physical[:12]) * 10_000,
                    expected_total * persona["primary_share_bp"],
                )
                self.assertTrue(all(value >= 1 for value in physical))
                if profile == "pilot":
                    self.assertTrue(all(value >= 4 for value in physical))
                    full = topology.project_physical_files(persona_id, "full")
                    self.assertTrue(all(left <= right for left, right in zip(physical, full)))

            profile_targets = envelope.build_envelope_contract()["profiles"]
            for profile in ("pilot", "full"):
                expected_total = profile_targets[profile]["target_chunks_per_person"]
                chunks = topology.project_contributor_chunks(persona_id, profile)
                expected_primary_total = (
                    expected_total * persona["primary_share_bp"] // 10_000
                )
                expected_chunks = (
                    _independent_hamilton(
                        expected_primary_total,
                        tuple(
                            row["contributor_chunk_weight_bp"]
                            for row in persona["scopes"][:12]
                        ),
                    )
                    + _independent_hamilton(
                        expected_total - expected_primary_total,
                        tuple(
                            row["contributor_chunk_weight_bp"]
                            for row in persona["scopes"][12:]
                        ),
                    )
                )
                self.assertEqual(chunks, expected_chunks)
                self.assertEqual(sum(chunks), expected_total)
                self.assertEqual(
                    sum(chunks[:12]) * 10_000,
                    expected_total * persona["primary_share_bp"],
                )
                self.assertTrue(all(value >= 4 for value in chunks))
                bounds = topology.contributor_source_feasibility(persona_id, profile)
                expected_lower = tuple(
                    max(4, math.ceil(value / 70)) for value in chunks
                )
                profile_physical = topology.project_physical_files(persona_id, profile)
                expected_upper = tuple(
                    min(chunk_count, file_count)
                    for chunk_count, file_count in zip(chunks, profile_physical)
                )
                self.assertEqual(bounds["lower_by_scope"], expected_lower)
                self.assertEqual(bounds["upper_by_scope"], expected_upper)
                expected_source_count = envelope.contributor_count(persona_id, profile)
                self.assertEqual(bounds["source_count"], expected_source_count)
                self.assertEqual(
                    bounds["lower_headroom"],
                    expected_source_count - sum(expected_lower),
                )
                self.assertEqual(
                    bounds["upper_headroom"],
                    sum(expected_upper) - expected_source_count,
                )
                self.assertEqual(
                    bounds["minimum_scope_span"],
                    min(
                        upper - lower
                        for lower, upper in zip(expected_lower, expected_upper)
                    ),
                )
                self.assertTrue(bounds["feasible_necessary_bounds"], f"{persona_id}/{profile}")
                self.assertTrue(
                    all(
                        value >= topology.MIN_CONTRIBUTOR_SOURCES_PER_SCOPE
                        for value in bounds["lower_by_scope"]
                    )
                )
                self.assertTrue(
                    sum(bounds["lower_by_scope"])
                    <= bounds["source_count"]
                    <= sum(bounds["upper_by_scope"])
                )
                self.assertGreaterEqual(bounds["lower_headroom"], 0)
                self.assertGreaterEqual(bounds["upper_headroom"], 0)
                self.assertGreaterEqual(bounds["minimum_scope_span"], 0)
                if profile == "pilot":
                    full_chunks = topology.project_contributor_chunks(persona_id, "full")
                    self.assertTrue(
                        all(left <= right for left, right in zip(chunks, full_chunks))
                    )
        self.assertEqual(
            sum(sum(topology.project_contributor_chunks(persona_id, "pilot")) for persona_id in envelope.PERSONA_IDS),
            240_000,
        )
        self.assertEqual(
            sum(sum(topology.project_contributor_chunks(persona_id, "full")) for persona_id in envelope.PERSONA_IDS),
            2_400_000,
        )
        self.assertEqual(
            topology.contributor_source_feasibility("p17", "pilot")["lower_headroom"],
            76,
        )
        self.assertEqual(
            topology.contributor_source_feasibility("p17", "pilot")["minimum_scope_span"],
            3,
        )
        self.assertEqual(
            topology.contributor_source_feasibility("p07", "pilot")["upper_headroom"],
            388,
        )
        with self.assertRaisesRegex(topology.PersonaV2TopologyError, "pilot/full"):
            topology.project_contributor_chunks("p01", "tiny-smoke")

    def test_canonical_hash_size_and_tamper_rejection(self):
        first = topology.build_topology_contract()
        second = topology.build_topology_contract()
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        self.assertTrue(topology.validate_topology_contract(first))
        self.assertLessEqual(len(topology.canonical_json_bytes(first)), topology.MAX_TOPOLOGY_BYTES)
        self.assertEqual(topology.topology_contract_sha256(first), EXPECTED_TOPOLOGY_SHA256)

        for mutate in (
            lambda value: value.__setitem__("g0_contract_frozen", True),
            lambda value: value["authority"].__setitem__("authorizes_physical_write", True),
            lambda value: value["authority"].__setitem__("authorizes_physical_write", 0),
            lambda value: value["personas"][0]["scopes"][0].__setitem__("physical_file_weight_bp", 1),
            lambda value: value["personas"][0]["scopes"][0].__setitem__("ordinal", True),
            lambda value: value["personas"][0]["scopes"][0].__setitem__("relative_path", "../escape"),
            lambda value: value.__setitem__("unknown", False),
        ):
            with self.subTest(mutate=mutate):
                changed = copy.deepcopy(first)
                mutate(changed)
                with self.assertRaises(topology.PersonaV2TopologyError):
                    topology.validate_topology_contract(changed)

        with self.assertRaisesRegex(topology.PersonaV2TopologyError, "ASCII"):
            topology._validate_relative_path("documents/日本語")
        with self.assertRaisesRegex(topology.PersonaV2TopologyError, "normalizes"):
            topology._validate_relative_path(".")
        with self.assertRaisesRegex(topology.PersonaV2TopologyError, "unsupported"):
            topology.canonical_json_bytes({"unsupported": object()})

    def test_public_views_are_deeply_detached(self):
        baseline_hash = topology.topology_contract_sha256()
        baseline_projection = topology.project_physical_files("p01", "full")

        contract = topology.build_topology_contract()
        contract["personas"][0]["scopes"][0]["relative_path"] = "mutated/path"
        persona = topology.get_persona_topology("p01")
        persona["scopes"][0]["relative_path"] = "another/mutation"

        self.assertNotEqual(
            topology.build_topology_contract()["personas"][0]["scopes"][0][
                "relative_path"
            ],
            "mutated/path",
        )
        self.assertNotEqual(
            topology.get_persona_topology("p01")["scopes"][0]["relative_path"],
            "another/mutation",
        )
        self.assertEqual(topology.topology_contract_sha256(), baseline_hash)
        self.assertEqual(
            topology.project_physical_files("p01", "full"),
            baseline_projection,
        )

    def test_v1_identity_and_cardinality_remain_frozen(self):
        self.assertEqual(v1.SCHEMA_VERSION, 1)
        self.assertEqual(v1.FIXTURE_ID, "kcs-persona-pc-v1")
        self.assertEqual(sum(persona["full_raw_files"] for persona in v1.PERSONAS), 195_000)


if __name__ == "__main__":
    unittest.main()
