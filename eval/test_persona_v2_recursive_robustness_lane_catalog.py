"""Focused and adversarial gates for the recursive-robustness lane catalog."""

from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import os
import subprocess
import sys
import unittest
from unittest import mock

from eval import persona_v2_artifact_common as artifact_common
from eval import persona_v2_realism_profile as realism
from eval import persona_v2_recursive_robustness_lane_catalog as catalog
from eval import persona_v2_recursive_robustness_lane_catalog_validator as independent
from eval import persona_v2_topology as topology


EXPECTED_CANONICAL_BYTES = 76_099
EXPECTED_SHA256 = (
    "49d6fa26cafa902bfca4a102c5e301c27683fd6761bc456a3930cd059f67a4f2"
)


class PersonaV2RecursiveRobustnessLaneCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.topology_value = topology.build_topology_contract()
        cls.realism_value = realism.build_realism_profile()
        cls.value = catalog.build_recursive_robustness_lane_catalog()

    def _independent_validate(self, value, *, topology_value=None, realism_value=None):
        return independent.validate_recursive_robustness_lane_catalog(
            value,
            topology_value=(
                self.topology_value if topology_value is None else topology_value
            ),
            realism_profile_value=(
                self.realism_value if realism_value is None else realism_value
            ),
        )

    def _assert_independent_rejects_rehashed(self, value):
        raw = artifact_common.canonical_json_bytes(
            value,
            label="rehashed recursive robustness lane catalog",
            max_bytes=catalog.MAX_CATALOG_BYTES,
        )
        with (
            mock.patch.object(
                independent, "EXPECTED_CATALOG_CANONICAL_BYTES", len(raw)
            ),
            mock.patch.object(
                independent,
                "EXPECTED_CATALOG_SHA256",
                hashlib.sha256(raw).hexdigest(),
            ),
            self.assertRaises(
                independent.PersonaV2RecursiveRobustnessLaneCatalogValidationError
            ),
        ):
            self._independent_validate(value)

    @staticmethod
    def _all_keys(value):
        keys = set()
        if type(value) is dict:
            for key, item in value.items():
                keys.add(key)
                keys.update(
                    PersonaV2RecursiveRobustnessLaneCatalogTests._all_keys(item)
                )
        elif type(value) is list:
            for item in value:
                keys.update(
                    PersonaV2RecursiveRobustnessLaneCatalogTests._all_keys(item)
                )
        return keys

    def test_canonical_pin_and_both_validators(self):
        raw = catalog.canonical_json_bytes(self.value)
        self.assertEqual(len(raw), EXPECTED_CANONICAL_BYTES)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), EXPECTED_SHA256)
        self.assertEqual(
            catalog.recursive_robustness_lane_catalog_sha256(), EXPECTED_SHA256
        )
        self.assertTrue(
            catalog.validate_recursive_robustness_lane_catalog(self.value)
        )
        self.assertTrue(self._independent_validate(self.value))

    def test_hashseed_independent_canonical_pin(self):
        script = (
            "import hashlib; "
            "from eval import persona_v2_recursive_robustness_lane_catalog as c; "
            "raw=c.canonical_json_bytes(c.build_recursive_robustness_lane_catalog()); "
            "print(str(len(raw))+\" \"+hashlib.sha256(raw).hexdigest())"
        )
        observed = set()
        for seed in ("1", "777"):
            environment = dict(os.environ)
            environment["PYTHONHASHSEED"] = seed
            observed.add(
                subprocess.check_output(
                    [sys.executable, "-c", script],
                    cwd=os.path.dirname(os.path.dirname(__file__)),
                    env=environment,
                    text=True,
                ).strip()
            )
        self.assertEqual(
            observed, {f"{EXPECTED_CANONICAL_BYTES} {EXPECTED_SHA256}"}
        )

    def test_exact_twenty_persona_candidate_and_directory_contract(self):
        rows = self.value["personas"]
        self.assertEqual(len(rows), 20)
        self.assertEqual(
            [row["persona_id"] for row in rows], list(catalog.PERSONA_IDS)
        )
        expected_categories = [
            {"candidate_count": count, "category_id": category_id}
            for category_id, count in catalog.CATEGORY_ROWS
        ]
        for row in rows:
            self.assertEqual(row["candidate_file_count"], 256)
            self.assertEqual(row["authored_directory_count"], 128)
            self.assertEqual(row["candidate_category_counts"], expected_categories)
            self.assertEqual(
                sum(
                    entry["candidate_count"]
                    for entry in row["candidate_category_counts"]
                ),
                256,
            )
            self.assertEqual(
                sum(
                    entry["authored_directory_count"]
                    for entry in row["authored_directory_depth_histogram"]
                ),
                128,
            )
        self.assertEqual(self.value["summary"]["suite_candidate_file_count"], 5120)
        self.assertEqual(
            self.value["summary"]["suite_authored_directory_count"], 2560
        )

    def test_exact_representative_paths_and_nonduplicated_shape_vectors(self):
        by_persona = {row["persona_id"]: row for row in self.value["personas"]}
        self.assertEqual(
            by_persona["p01"]["representative_parent_relative_path"],
            "scratch/product-alpha/feature-auth/rebase-03/conflicts/files",
        )
        self.assertEqual(
            by_persona["p07"]["representative_parent_relative_path"],
            "imports/archive-alpha/box-001/folder-07/item-003/derivatives/ocr",
        )
        self.assertEqual(
            by_persona["p14"]["representative_parent_relative_path"],
            "onedrive-sync/finance/close/fy2026/q1/2026-03/review/final",
        )
        self.assertEqual(
            by_persona["p20"]["representative_parent_relative_path"],
            "source-drop/story-alpha/source-syn-017/device-export/messages/attachments/2026-07",
        )
        self.assertEqual(
            len(
                {
                    row["representative_parent_relative_path"]
                    for row in self.value["personas"]
                }
            ),
            20,
        )
        self.assertEqual(
            len({row["shape_vector_id"] for row in self.value["personas"]}), 20
        )
        self.assertEqual(
            len({row["planned_max_fan_out"] for row in self.value["personas"]}),
            20,
        )

    def test_depth_is_from_ambient_home_to_file_parent_and_covers_d6_d7_d8(self):
        for row in self.value["personas"]:
            calculated_depth = len(
                row["representative_parent_relative_path"].split("/")
            )
            self.assertEqual(row["representative_parent_depth"], calculated_depth)
            self.assertLessEqual(calculated_depth, row["planned_dmax"])
            file_histogram = {
                entry["depth"]: entry["candidate_count"]
                for entry in row["candidate_file_depth_histogram"]
            }
            self.assertEqual(sum(file_histogram.values()), 256)
            self.assertGreater(file_histogram[row["planned_dmax"]], 0)
            self.assertTrue(
                all(
                    count == 0
                    for depth, count in file_histogram.items()
                    if depth > row["planned_dmax"]
                )
            )
            directory_depths = [
                entry["depth"]
                for entry in row["authored_directory_depth_histogram"]
            ]
            self.assertEqual(directory_depths, list(range(1, row["planned_dmax"] + 1)))

        self.assertEqual(
            self.value["summary"]["persona_planned_dmax_counts"],
            [
                {"depth": 6, "persona_count": 8},
                {"depth": 7, "persona_count": 9},
                {"depth": 8, "persona_count": 3},
            ],
        )
        self.assertEqual(
            self.value["summary"]["suite_candidate_file_depth_histogram"],
            [
                {"candidate_count": 2855, "depth": 6},
                {"candidate_count": 1901, "depth": 7},
                {"candidate_count": 364, "depth": 8},
            ],
        )
        p07 = self.value["personas"][6]
        self.assertEqual(p07["representative_parent_depth"], 7)
        self.assertEqual(p07["planned_dmax"], 8)
        self.assertIs(p07["representative_parent_is_planned_dmax"], False)

    def test_candidate_and_native_realization_are_distinct_by_case_mode(self):
        by_persona = {row["persona_id"]: row for row in self.value["personas"]}

        insensitive = by_persona["p01"]["native_realization_plan"]
        self.assertEqual(by_persona["p01"]["target_case_mode"], "case-insensitive")
        self.assertEqual(
            by_persona["p01"]["target_os_execution_mode"],
            "declared-target-metadata-only-not-native-or-emulated",
        )
        self.assertEqual(insensitive["case_collision_pair_count"], 3)
        self.assertEqual(insensitive["case_collision_base_candidate_count"], 3)
        self.assertEqual(insensitive["case_collision_mate_candidate_count"], 3)
        self.assertEqual(insensitive["unicode_noncollision_candidate_count"], 7)
        self.assertEqual(
            insensitive["expected_manifest_only_failure_count_lower_bound"], 0
        )
        self.assertEqual(
            insensitive["expected_manifest_only_failure_count_upper_bound"], 3
        )
        self.assertEqual(
            insensitive["native_realizable_candidate_count_lower_bound"], 253
        )
        self.assertEqual(
            insensitive["native_realizable_candidate_count_upper_bound"], 256
        )
        self.assertEqual(
            insensitive["execution_filesystem_case_mode_binding_status"],
            "unbound-until-native-replay-receipt",
        )
        self.assertEqual(
            insensitive["conditional_execution_case_outcomes"],
            [
                {
                    "execution_filesystem_case_mode": "case-insensitive",
                    "expected_manifest_only_failure_count": 3,
                    "expected_native_realized_candidate_count": 253,
                },
                {
                    "execution_filesystem_case_mode": "case-sensitive",
                    "expected_manifest_only_failure_count": 0,
                    "expected_native_realized_candidate_count": 256,
                },
            ],
        )
        self.assertEqual(
            insensitive[
                "target_semantics_conditional_native_realizable_count_lower_bound"
            ],
            253,
        )
        self.assertEqual(
            insensitive[
                "target_semantics_conditional_native_realizable_count_upper_bound"
            ],
            253,
        )

        sensitive = by_persona["p02"]["native_realization_plan"]
        self.assertEqual(by_persona["p02"]["target_case_mode"], "case-sensitive")
        self.assertEqual(
            sensitive["expected_manifest_only_failure_count_upper_bound"], 3
        )
        self.assertEqual(
            sensitive["native_realizable_candidate_count_lower_bound"], 253
        )
        self.assertEqual(
            sensitive["native_realizable_candidate_count_upper_bound"], 256
        )
        self.assertEqual(
            sensitive[
                "target_semantics_conditional_native_realizable_count_lower_bound"
            ],
            256,
        )
        self.assertEqual(
            sensitive[
                "target_semantics_conditional_native_realizable_count_upper_bound"
            ],
            256,
        )

        unspecified = by_persona["p19"]["native_realization_plan"]
        self.assertEqual(
            by_persona["p19"]["target_case_mode"],
            "portable-snapshot-case-unspecified",
        )
        self.assertEqual(
            unspecified["expected_manifest_only_failure_count_lower_bound"], 0
        )
        self.assertEqual(
            unspecified["expected_manifest_only_failure_count_upper_bound"], 3
        )
        self.assertEqual(
            unspecified["native_realizable_candidate_count_lower_bound"], 253
        )
        self.assertEqual(
            unspecified["native_realizable_candidate_count_upper_bound"], 256
        )

        self.assertEqual(
            self.value["summary"][
                "suite_native_realizable_candidate_count_lower_bound"
            ],
            5060,
        )
        self.assertEqual(
            self.value["summary"][
                "suite_native_realizable_candidate_count_upper_bound"
            ],
            5120,
        )
        self.assertEqual(
            self.value["summary"][
                "suite_target_semantics_conditional_native_realizable_lower_bound"
            ],
            5066,
        )
        self.assertEqual(
            self.value["summary"][
                "suite_target_semantics_conditional_native_realizable_upper_bound"
            ],
            5069,
        )

    def test_lane_is_formally_disjoint_non_authorizing_and_not_materialized(self):
        self.assertEqual(set(self.value["authority"]), catalog.AUTHORITY_FIELDS)
        self.assertTrue(
            all(
                type(flag) is bool and flag is False
                for flag in self.value["authority"].values()
            )
        )
        self.assertIs(self.value["g0_contract_frozen"], False)
        lane = self.value["lane_contract"]
        self.assertIs(lane["registered_scope"], False)
        self.assertIs(lane["formal_gate_eligible"], False)
        self.assertEqual(lane["requested_chunks"], 0)
        self.assertEqual(lane["formal_chunk_denominator_membership"], "excluded")
        self.assertEqual(lane["formal_family_ratio_membership"], "excluded")
        self.assertEqual(lane["formal_recall_latency_membership"], "excluded")
        self.assertTrue(lane["separate_manifest_and_receipt_required"])
        self.assertTrue(lane["native_realization_receipt_must_match_planned_dmax"])
        self.assertEqual(
            self.value["case_collision_pair_contract"],
            {
                "candidate_manifest_required_member_fields": [
                    "candidate_id",
                    "collision_pair_id",
                    "collision_role",
                    "parent_relative_path",
                    "basename_portable_ascii",
                    "collision_key",
                ],
                "basename_difference_rule": "ascii-letter-case-only",
                "basename_nfc_required": True,
                "basename_repertoire": "portable-ascii",
                "collision_key_algorithm": "portable-ascii-lower-v1",
                "collision_key_expression": "ASCII-lower(basename)",
                "collision_key_reuse_across_pairs_allowed": False,
                "collision_roles": ["base", "mate"],
                "distinct_exact_basename_required": True,
                "distinct_exact_relative_path_required": True,
                "equal_collision_key_required": True,
                "materialization_order": ["base", "mate"],
                "members_per_pair": 2,
                "one_member_per_collision_role_required": True,
                "pair_count_per_persona": 3,
                "pair_id_unique_per_persona": True,
                "portable_ascii_basename_required": True,
                "same_parent_directory_required": True,
            },
        )
        self.assertTrue(
            self.value["receipt_contract"][
                "case_collision_candidate_outcome_reconciliation_required"
            ]
        )
        self.assertTrue(
            self.value["receipt_contract"][
                "case_collision_pair_structure_validation_required"
            ]
        )
        self.assertTrue(
            self.value["receipt_contract"][
                "collision_key_recomputation_required"
            ]
        )
        self.assertTrue(
            self.value["receipt_contract"][
                "same_parent_pair_validation_required"
            ]
        )
        self.assertTrue(
            self.value["receipt_contract"][
                "conditional_case_outcome_match_required"
            ]
        )
        self.assertTrue(
            self.value["receipt_contract"][
                "execution_filesystem_case_mode_required"
            ]
        )
        self.assertTrue(
            self.value["receipt_contract"][
                "manifest_only_expected_failure_excluded_from_native_realized_count"
            ]
        )
        self.assertIs(
            self.value["completion_claims"]["candidate_paths_materialized"], False
        )
        self.assertIs(
            self.value["completion_claims"]["native_realization_receipts_attested"],
            False,
        )
        self.assertIs(
            self.value["completion_claims"]["physical_writer_implemented"], False
        )

        topology_by_persona = {
            row["persona_id"]: row for row in self.topology_value["personas"]
        }
        for row in self.value["personas"]:
            self.assertIs(row["registered_scope"], False)
            self.assertIs(row["formal_gate_eligible"], False)
            self.assertIs(row["formal_scope_overlap"], False)
            self.assertIs(row["kcs_control_tree_allowed"], False)
            self.assertEqual(row["requested_chunks"], 0)
            self.assertEqual(row["lane_local_gate_role"], "raw_only")
            self.assertEqual(row["path_state"], "contract-only-not-materialized")
            self.assertEqual(row["manifest_status"], "planned-not-written")
            self.assertNotEqual(
                row["manifest_relative_path"], row["receipt_relative_path"]
            )
            for path_key in (
                "device_relative_ambient_root",
                "device_relative_formal_root",
                "manifest_relative_path",
                "receipt_relative_path",
                "representative_parent_relative_path",
            ):
                path = row[path_key]
                self.assertFalse(path.startswith(("/", "\\")))
                self.assertNotIn("..", path.split("/"))
                self.assertNotIn(".kcs", [part.casefold() for part in path.split("/")])
            self.assertNotEqual(
                row["device_relative_ambient_root"],
                row["device_relative_formal_root"],
            )
            self.assertEqual(
                row["formal_scope_reference_count"],
                len(topology_by_persona[row["persona_id"]]["scopes"]),
            )

        forbidden = {
            "absolute_path",
            "actual_native_realized_count",
            "actual_native_realized_dmax",
            "materialized_path",
            "observed_path",
            "scope_key",
            "source_id",
        }
        self.assertFalse(self._all_keys(self.value) & forbidden)

    def test_validator_is_builder_independent_and_builder_is_deep_detached(self):
        tree = ast.parse(inspect.getsource(independent))
        imported_modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported_modules.add(node.module or "")
        self.assertFalse(
            any(
                name.endswith("persona_v2_recursive_robustness_lane_catalog")
                for name in imported_modules
            )
        )

        changed = catalog.build_recursive_robustness_lane_catalog()
        changed["personas"][0]["candidate_category_counts"][0][
            "candidate_count"
        ] = 101
        changed["summary"]["persona_planned_dmax_counts"][0][
            "persona_count"
        ] = 7
        fresh = catalog.build_recursive_robustness_lane_catalog()
        self.assertEqual(
            fresh["personas"][0]["candidate_category_counts"][0][
                "candidate_count"
            ],
            102,
        )
        self.assertEqual(
            fresh["summary"]["persona_planned_dmax_counts"][0][
                "persona_count"
            ],
            8,
        )
        with self.assertRaises(
            catalog.PersonaV2RecursiveRobustnessLaneCatalogError
        ):
            catalog.validate_recursive_robustness_lane_catalog(changed)

    def test_rehashed_boundary_count_and_realization_tampering_is_rejected(self):
        mutations = []

        changed = copy.deepcopy(self.value)
        changed["personas"][0]["candidate_file_count"] = 255
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["personas"][0]["candidate_category_counts"][0][
            "candidate_count"
        ] = 101
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["personas"][0]["candidate_file_depth_histogram"][0][
            "candidate_count"
        ] = 255
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["personas"][0]["planned_dmax"] = 8
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["personas"][0]["native_realization_plan"][
            "native_realizable_candidate_count_lower_bound"
        ] = 256
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["personas"][0]["actual_native_realized_count"] = 253
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["case_collision_pair_contract"][
            "same_parent_directory_required"
        ] = False
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["case_collision_pair_contract"]["collision_key_expression"] = (
            "basename"
        )
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["personas"][0]["registered_scope"] = True
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["personas"][0]["formal_gate_eligible"] = True
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["authority"]["authorizes_physical_write"] = True
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["remaining_blockers"] = ["all-blockers-cleared"]
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["unexpected"] = False
        mutations.append(changed)

        for changed in mutations:
            self._assert_independent_rejects_rehashed(changed)

    def test_rehashed_traversal_absolute_kcs_overlap_and_receipt_alias_are_rejected(self):
        path_mutations = (
            "../escape",
            "/tmp/escape",
            "\\server\\share\\escape",
            "C:/temp/escape",
            ".kcs/objects/escape",
        )
        for path in path_mutations:
            changed = copy.deepcopy(self.value)
            changed["personas"][0]["representative_parent_relative_path"] = path
            self._assert_independent_rejects_rehashed(changed)

        changed = copy.deepcopy(self.value)
        changed["personas"][0]["device_relative_ambient_root"] = changed[
            "personas"
        ][0]["device_relative_formal_root"]
        self._assert_independent_rejects_rehashed(changed)

        changed = copy.deepcopy(self.value)
        changed["personas"][0]["manifest_relative_path"] = changed["personas"][
            0
        ]["receipt_relative_path"]
        self._assert_independent_rejects_rehashed(changed)

    def test_null_float_negative_bool_and_hostile_repr_are_rejected(self):
        for replacement in (None, 1.0, -1, True):
            changed = copy.deepcopy(self.value)
            changed["summary"]["persona_count"] = replacement
            with self.assertRaises(
                catalog.PersonaV2RecursiveRobustnessLaneCatalogError
            ):
                catalog.validate_recursive_robustness_lane_catalog(changed)

        class Hostile:
            def __repr__(self):
                raise AssertionError("repr must not be called")

        changed = copy.deepcopy(self.value)
        changed["summary"]["persona_count"] = Hostile()
        with self.assertRaises(
            catalog.PersonaV2RecursiveRobustnessLaneCatalogError
        ):
            catalog.validate_recursive_robustness_lane_catalog(changed)

    def test_dependency_tamper_is_rejected(self):
        topology_changed = copy.deepcopy(self.topology_value)
        topology_changed["personas"][0]["role"] = "tampered-role"
        with self.assertRaises(
            independent.PersonaV2RecursiveRobustnessLaneCatalogValidationError
        ):
            self._independent_validate(
                self.value, topology_value=topology_changed
            )

        realism_changed = copy.deepcopy(self.realism_value)
        realism_changed["personas"][0]["case_mode"] = "case-sensitive"
        with self.assertRaises(
            independent.PersonaV2RecursiveRobustnessLaneCatalogValidationError
        ):
            self._independent_validate(
                self.value, realism_value=realism_changed
            )

    def test_snapshot_and_closing_reauthentication_detect_mutation(self):
        value = catalog.build_recursive_robustness_lane_catalog()
        topology_value = topology.build_topology_contract()
        realism_value = realism.build_realism_profile()
        original = independent._validate_recursive_robustness_lane_catalog_snapshot

        def mutate_after_snapshot(
            snapshot, *, topology_value, realism_profile_value
        ):
            result = original(
                snapshot,
                topology_value=topology_value,
                realism_profile_value=realism_profile_value,
            )
            value["completion_claims"]["candidate_paths_materialized"] = True
            return result

        with (
            mock.patch.object(
                independent,
                "_validate_recursive_robustness_lane_catalog_snapshot",
                side_effect=mutate_after_snapshot,
            ),
            self.assertRaises(
                independent.PersonaV2RecursiveRobustnessLaneCatalogValidationError
            ),
        ):
            independent.validate_recursive_robustness_lane_catalog(
                value,
                topology_value=topology_value,
                realism_profile_value=realism_value,
            )


if __name__ == "__main__":
    unittest.main()
