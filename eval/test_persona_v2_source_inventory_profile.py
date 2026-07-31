import copy
import os
import subprocess
import sys
import unittest

from eval import persona_v2_source_inventory_profile as profiles
from eval import persona_v2_source_profile_catalog as feasibility
from eval import persona_v2_variant_catalog as variants


EXPECTED_CANONICAL_BYTES = 87_391
EXPECTED_SHA256 = "9b0de3defbc106f0bfa8b96ca2134886acd6766ac69196e3498b6b6f7edf43c0"


class PersonaV2SourceInventoryProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = profiles.build_source_inventory_profile_catalog()
        cls.variant_value = variants.build_variant_catalog()
        cls.feasibility_value = feasibility.build_source_profile_catalog()

    def test_exact_pin_identity_completion_scope_and_negative_authority(self):
        value = self.value
        self.assertEqual(len(profiles.canonical_json_bytes(value)), EXPECTED_CANONICAL_BYTES)
        self.assertEqual(profiles.source_inventory_profile_catalog_sha256(value), EXPECTED_SHA256)
        self.assertTrue(profiles.validate_source_inventory_profile_catalog(value))
        self.assertIs(value["g0_contract_frozen"], False)
        self.assertTrue(value["authority"])
        self.assertTrue(all(flag is False for flag in value["authority"].values()))
        claims = value["completion_claims"]
        for key in (
            "all_variant_inventory_profiles_present",
            "exact_variant_metadata_projection_complete",
            "inventory_profile_catalog_complete",
            "profile_reference_namespace_unique",
        ):
            self.assertIs(claims[key], True, key)
        for key in (
            "formal_source_recipe_profiles_bound",
            "physical_source_materialization_complete",
            "renderer_validator_implementation_complete",
            "source_level_feasibility_complete",
        ):
            self.assertIs(claims[key], False, key)
        with self.assertRaises(profiles.PersonaV2SourceInventoryProfileError):
            profiles.require_formal_source_recipe_profiles()

    def test_all_71_unique_profiles_exactly_project_variant_metadata(self):
        rows = self.value["source_profile_rows"]
        upstream = self.variant_value["variant_rows"]
        self.assertEqual(len(rows), 71)
        self.assertEqual(
            [row["variant_id"] for row in rows],
            [row["variant_id"] for row in upstream],
        )
        self.assertEqual(len({row["source_profile_id"] for row in rows}), 71)
        self.assertEqual(
            len({row["source_recipe"]["slot_id"] for row in rows}),
            71,
        )
        fields = (
            "compound_suffix_parts",
            "content_media_type",
            "expected_kio_path_media_type",
            "expected_offline_disposition",
            "family",
            "filename_extension",
            "gate_role",
            "safety_profile_id",
        )
        for row, variant_row in zip(rows, upstream):
            with self.subTest(variant_id=row["variant_id"]):
                self.assertEqual(
                    {field: row[field] for field in fields},
                    {field: variant_row[field] for field in fields},
                )
                self.assertEqual(
                    row["feasibility_rule_id"],
                    variant_row["complexity_contract"]["feasibility_rule_id"],
                )
                self.assertEqual(
                    row["upstream_planned_renderer"]["renderer_id"],
                    variant_row["renderer"]["renderer_id"],
                )
                self.assertEqual(
                    row["upstream_planned_validator"]["validator_id"],
                    variant_row["validator"]["validator_id"],
                )
                self.assertEqual(
                    row["source_profile_id"],
                    profiles.inventory_profile_id(row["variant_id"]),
                )
                self.assertEqual(
                    row["source_recipe"]["slot_id"],
                    profiles.source_recipe_slot_id(row["variant_id"]),
                )

    def test_ready_ten_and_missing_sixty_one_never_escalate_recipe_or_execution(self):
        rows = self.value["source_profile_rows"]
        feasibility_by_id = {
            row["variant_id"]: row
            for row in self.feasibility_value["source_profile_rows"]
        }
        ready = []
        missing = []
        for row in rows:
            expected = feasibility_by_id[row["variant_id"]]["bounded_feasibility"][
                "vertical_slice_ready"
            ]
            self.assertIs(
                row["bounded_feasibility"]["local_vertical_slice_ready"],
                expected,
            )
            (ready if expected else missing).append(row["variant_id"])
            self.assertEqual(row["source_recipe"]["binding_status"], "reserved-unbound")
            self.assertEqual(row["source_recipe"]["profile_id"], "not-bound")
            self.assertIs(row["source_recipe"]["parameters_complete"], False)
            self.assertEqual(row["execution_eligibility_status"], "blocked")
        self.assertEqual(len(ready), 10)
        self.assertEqual(len(missing), 61)
        self.assertEqual(
            self.value["coverage"]["local_ready_source_counts"],
            {"full": 69_236, "full-residual": 62_311, "pilot": 6_925},
        )

    def test_tamper_and_public_mutation_fail_closed(self):
        cases = []
        changed_variant = copy.deepcopy(self.value)
        changed_variant["source_profile_rows"][0]["variant_id"] = "txt"
        cases.append(changed_variant)
        completed_recipe = copy.deepcopy(self.value)
        completed_recipe["source_profile_rows"][0]["source_recipe"][
            "binding_status"
        ] = "bound-complete"
        cases.append(completed_recipe)
        executable = copy.deepcopy(self.value)
        executable["source_profile_rows"][0]["execution_eligibility_status"] = "ready"
        cases.append(executable)
        authority = copy.deepcopy(self.value)
        authority["authority"]["authorizes_physical_write"] = True
        cases.append(authority)
        for candidate in cases:
            with self.subTest(candidate=candidate["source_profile_rows"][0]["variant_id"]):
                with self.assertRaises(profiles.PersonaV2SourceInventoryProfileError):
                    profiles.validate_source_inventory_profile_catalog(candidate)

        detached = profiles.build_source_inventory_profile_catalog()
        detached["source_profile_rows"][0]["variant_id"] = "tampered"
        self.assertEqual(
            profiles.build_source_inventory_profile_catalog(),
            self.value,
        )

    def test_hash_is_independent_of_hashseed_timezone_and_locale(self):
        script = (
            "from eval import persona_v2_source_inventory_profile as p;"
            "x=p.build_source_inventory_profile_catalog();"
            "print(len(p.canonical_json_bytes(x)),p.source_inventory_profile_catalog_sha256(x))"
        )
        observations = set()
        for seed, timezone, locale_name in (
            ("0", "UTC", "C"),
            ("1", "Asia/Tokyo", "C"),
            ("42", "UTC", "C.UTF-8"),
        ):
            environment = dict(os.environ)
            environment.update(
                {
                    "PYTHONHASHSEED": seed,
                    "TZ": timezone,
                    "LC_ALL": locale_name,
                    "LANG": locale_name,
                }
            )
            output = subprocess.check_output(
                [sys.executable, "-c", script],
                cwd=os.path.dirname(os.path.dirname(__file__)),
                env=environment,
                text=True,
                timeout=30,
            ).strip()
            observations.add(output)
        self.assertEqual(
            observations,
            {f"{EXPECTED_CANONICAL_BYTES} {EXPECTED_SHA256}"},
        )


if __name__ == "__main__":
    unittest.main()
