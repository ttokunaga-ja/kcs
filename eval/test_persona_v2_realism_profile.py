import copy
import os
import subprocess
import sys
import unittest
from unittest import mock

from eval import persona_v2_contract as envelope
from eval import persona_v2_realism_profile as realism


class PersonaV2RealismProfileTests(unittest.TestCase):
    def test_identity_bindings_hash_size_and_negative_authority_are_exact(self):
        value = realism.build_realism_profile()
        self.assertEqual(value["artifact_schema"], realism.ARTIFACT_SCHEMA)
        self.assertEqual(value["artifact_kind"], realism.ARTIFACT_KIND)
        self.assertEqual(value["artifact_schema_version"], 2)
        self.assertEqual(value["fixture_id"], envelope.FIXTURE_ID)
        self.assertIs(value["g0_contract_frozen"], False)
        self.assertIs(value["profile_vectors_complete"], True)
        self.assertIs(value["overlay_marginal_targets_complete"], True)
        self.assertIs(value["overlay_membership_complete"], False)
        self.assertIs(value["overlay_scoring_and_search_semantics_complete"], False)
        self.assertIs(value["placement_integer_allocation_complete"], False)
        self.assertIs(value["eight_axis_ledger_contract_complete"], False)
        self.assertIs(value["realism_input_closure_complete"], False)
        self.assertEqual(
            set(value["authority"]),
            {
                "actual_chunks_attested",
                "authorizes_g0_freeze",
                "authorizes_history_mutation",
                "authorizes_physical_write",
                "authorizes_solver_execution",
                "authorizes_source_plan",
                "filesystem_writer_available",
                "formal_capacity_gate_satisfied",
                "history_executor_available",
                "kcs_execution_available",
                "query_instances_rendered",
                "query_spec_hashed",
                "renderer_available",
            },
        )
        for key, flag in value["authority"].items():
            self.assertIs(type(flag), bool, key)
            self.assertIs(flag, False, key)
        raw = realism.canonical_json_bytes(value)
        self.assertEqual(len(raw), 36_811)
        self.assertEqual(
            realism.realism_profile_sha256(value),
            "a32bbb0fd7c88c57205454d8555163ad97b2b1a3024e5a5d7f7234bf56766f05",
        )
        self.assertTrue(realism.validate_realism_profile(value))
        self.assertEqual(
            [(row["name"], row["canonical_bytes"]) for row in value["input_bindings"]],
            [
                ("envelope", 71_979),
                ("topology", 134_195),
                ("joint-problem", 744_137),
                ("joint-solver-policy", 83_004),
            ],
        )

    def test_twenty_persona_vectors_denominators_and_overlay_counts_are_exact(self):
        value = realism.build_realism_profile()
        self.assertEqual(
            [row["persona_id"] for row in value["personas"]],
            list(envelope.PERSONA_IDS),
        )
        permission_profiles = {
            row["permission_profile_id"]: row["weights_bp"]
            for row in value["catalogs"]["permission_profiles"]
        }
        placement_profiles = {
            row["placement_profile_id"]: row["weights_bp"]
            for row in value["catalogs"]["placement_profiles"]
        }
        for row in value["personas"]:
            persona_id = row["persona_id"]
            self.assertEqual(
                sum(item["weight_bp"] for item in row["language_weights_bp"]),
                10_000,
            )
            self.assertEqual(sum(row["retention_weights_bp"]), 10_000)
            self.assertEqual(sum(row["mtime_weights_bp"]), 10_000)
            self.assertEqual(sum(permission_profiles[row["permission_profile_id"]]), 10_000)
            self.assertEqual(sum(placement_profiles[row["placement_profile_id"]]), 10_000)
            self.assertEqual(
                row["w0_physical_denominators"],
                {
                    "full": envelope.profile_file_count(persona_id, "full"),
                    "pilot": envelope.profile_file_count(persona_id, "pilot"),
                },
            )
            for key in (
                "conflict_copy",
                "exact_duplicate",
                "near_revision",
                "standalone_attachment",
                "relation_cluster_count",
                "required_relation_endpoint_count",
            ):
                self.assertEqual(
                    row["overlay_targets"]["full"][key],
                    10 * row["overlay_targets"]["pilot"][key],
                    f"{persona_id}/{key}",
                )
            self.assertLessEqual(
                row["overlay_targets"]["attachment_exact_duplicate_overlap"][
                    "pilot_count"
                ],
                row["overlay_targets"]["pilot"]["exact_duplicate"],
            )

        headrooms = {"pilot": [], "full": []}
        for profile in headrooms:
            for row in value["personas"]:
                persona_id = row["persona_id"]
                counts = row["overlay_targets"][profile]
                overlap = row["overlay_targets"][
                    "attachment_exact_duplicate_overlap"
                ][f"{profile}_count"]
                searchable = envelope.contributor_count(persona_id, profile)
                searchable += sum(
                    variant["count"]
                    for variants in envelope.variant_counts(
                        persona_id,
                        profile,
                    ).values()
                    for variant in variants
                    if variant["gate_role"] == "incidental_searchable"
                )
                required = (
                    2 * counts["relation_cluster_count"]
                    + counts["standalone_attachment"]
                    - overlap
                )
                self.assertEqual(
                    counts["required_relation_endpoint_count"],
                    2 * counts["relation_cluster_count"],
                )
                self.assertLessEqual(
                    overlap,
                    min(counts["exact_duplicate"], counts["standalone_attachment"]),
                )
                self.assertLessEqual(required, searchable)
                headrooms[profile].append((searchable - required, persona_id))
        self.assertEqual(min(headrooms["pilot"]), (164, "p17"))
        self.assertEqual(min(headrooms["full"]), (1_640, "p17"))

        self.assertEqual(
            value["suite_overlay_targets"],
            {
                "full": {
                    "conflict_copy": 1_560,
                    "exact_duplicate": 5_080,
                    "near_revision": 13_230,
                    "relation_cluster_count": 19_870,
                    "standalone_attachment": 5_690,
                },
                "pilot": {
                    "conflict_copy": 156,
                    "exact_duplicate": 508,
                    "near_revision": 1_323,
                    "relation_cluster_count": 1_987,
                    "standalone_attachment": 569,
                },
            },
        )
        p13 = next(row for row in value["personas"] if row["persona_id"] == "p13")
        self.assertEqual(p13["retention_weights_bp"][:2], [300, 400])
        self.assertEqual(p13["w0_physical_denominators"]["pilot"] * 300 // 10_000, 21)

    def test_targets_are_not_membership_or_observed_statistics(self):
        value = realism.build_realism_profile()
        self.assertEqual(
            value["hypothesis_status"],
            "authored-benchmark-stress-design-not-observed-user-statistics",
        )
        self.assertIn("source-intent-recipe-not-bound", value["remaining_blockers"])
        self.assertIn("overlay-intent-memberships-not-present", value["remaining_blockers"])
        self.assertIs(value["policy"]["live_sync_allowed"], False)
        self.assertIs(value["policy"]["formal_lane_unreadable_files_allowed"], False)
        self.assertIs(value["policy"]["overlay_may_change_physical_totals"], False)
        self.assertEqual(
            value["policy"]["content_relation_cluster_cardinality"],
            "exactly-two-physical-materializations",
        )
        self.assertIs(
            value["policy"]["content_relation_clusters_are_physical-member-disjoint"],
            True,
        )
        self.assertNotIn("intent_key", repr(value["personas"]))
        with self.assertRaises(realism.PersonaV2RealismProfileError):
            realism.require_realism_input_closure()

    def test_tamper_strict_types_getter_and_public_detachment_fail_closed(self):
        first = realism.build_realism_profile()
        tampered = copy.deepcopy(first)
        tampered["personas"][0]["overlay_targets"]["full"]["exact_duplicate"] -= 1
        tampered["personas"][1]["overlay_targets"]["full"]["exact_duplicate"] += 1
        with self.assertRaises(realism.PersonaV2RealismProfileError):
            realism.validate_realism_profile(tampered)

        for replacement in (True, 1.0, None, "e\u0301", "\ud800"):
            with self.subTest(replacement=repr(replacement)):
                tampered = realism.build_realism_profile()
                tampered["personas"][0]["snapshot_account_counts"]["cloud_accounts"] = replacement
                with self.assertRaises(realism.PersonaV2RealismProfileError):
                    realism.validate_realism_profile(tampered)

        first["personas"][0]["role"] = "poisoned"
        self.assertEqual(realism.get_persona_realism_profile("p01")["role"], "software-engineer")
        for invalid in (True, 1, "p21"):
            with self.assertRaises(realism.PersonaV2RealismProfileError):
                realism.get_persona_realism_profile(invalid)

    def test_authored_row_schema_and_cross_field_semantics_fail_closed(self):
        cases = (
            (5, (("ja", 60), ("ja", 40))),
            (11, (10, 20, 30, 40)),
            (12, (20, 25, 25, 20, 10)),
            (13, "missing-permission-profile"),
            (20, "missing-placement-profile"),
            (10, ("S2", "S1")),
            (16, 101),
            (18, True),
            (7, -421),
            (3, "case-sensitive"),
        )
        for index, replacement in cases:
            rows = list(realism._REALISM_ROWS)
            first = list(rows[0])
            first[index] = replacement
            rows[0] = tuple(first)
            with self.subTest(index=index, replacement=repr(replacement)):
                with mock.patch.object(realism, "_REALISM_ROWS", tuple(rows)):
                    with self.assertRaises(realism.PersonaV2RealismProfileError):
                        realism.build_realism_profile()

        rows = list(realism._REALISM_ROWS)
        rows[1] = rows[0]
        with mock.patch.object(realism, "_REALISM_ROWS", tuple(rows)):
            with self.assertRaises(realism.PersonaV2RealismProfileError):
                realism.build_realism_profile()

    def test_catalog_bucket_definitions_and_authored_platform_counts_are_exact(self):
        value = realism.build_realism_profile()
        catalogs = value["catalogs"]
        self.assertEqual(len(catalogs["eight_axis_ledger_order"]), 8)
        self.assertEqual(
            [row["bucket_id"] for row in catalogs["retention_buckets"]],
            list(realism.RETENTION_BUCKET_ORDER),
        )
        self.assertEqual(
            [row["bucket_id"] for row in catalogs["mtime_buckets"]],
            list(realism.MTIME_BUCKET_ORDER),
        )
        self.assertEqual(len(catalogs["permission_profiles"]), 8)
        self.assertEqual(len(catalogs["placement_profiles"]), 5)
        for rows in (
            catalogs["permission_profiles"],
            catalogs["placement_profiles"],
        ):
            for row in rows:
                self.assertEqual(sum(row["weights_bp"]), 10_000)

        personas = value["personas"]
        self.assertEqual(
            sum(row["os_semantics_id"].startswith("windows-") for row in personas),
            12,
        )
        self.assertEqual(
            sum(row["os_semantics_id"].startswith("macos-") for row in personas),
            5,
        )
        self.assertEqual(
            sum(row["os_semantics_id"].startswith("ubuntu-") for row in personas),
            2,
        )
        self.assertEqual(
            sum(row["os_semantics_id"].startswith("chromeos-") for row in personas),
            1,
        )

        with mock.patch.object(
            realism,
            "RETENTION_BUCKET_ORDER",
            tuple(reversed(realism.RETENTION_BUCKET_ORDER)),
        ):
            with self.assertRaises(realism.PersonaV2RealismProfileError):
                realism.build_realism_profile()
        with mock.patch.object(
            realism,
            "_PERMISSION_PROFILES",
            realism._PERMISSION_PROFILES + (("P9-unused", (25, 25, 25, 25)),),
        ):
            with self.assertRaises(realism.PersonaV2RealismProfileError):
                realism.build_realism_profile()

    def test_hash_is_independent_of_hashseed_timezone_under_c_locale(self):
        script = (
            "from eval import persona_v2_realism_profile as r; "
            "v=r.build_realism_profile(); "
            "print(r.realism_profile_sha256(v),len(r.canonical_json_bytes(v)))"
        )
        expected = None
        for seed, timezone in (("0", "UTC"), ("1", "Asia/Tokyo"), ("42", "UTC")):
            environment = os.environ.copy()
            environment.update(
                {"PYTHONHASHSEED": seed, "TZ": timezone, "LC_ALL": "C"}
            )
            output = subprocess.check_output(
                [sys.executable, "-c", script],
                cwd=os.getcwd(),
                env=environment,
                text=True,
            ).strip()
            if expected is None:
                expected = output
            self.assertEqual(output, expected)


if __name__ == "__main__":
    unittest.main()
