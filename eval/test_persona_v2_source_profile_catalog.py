import copy
import hashlib
import inspect
import os
import subprocess
import sys
import unittest

from eval import persona_v2_contract as envelope
from eval import persona_v2_input_bindings as input_bindings
from eval import persona_v2_source_profile_catalog as catalog
from eval import persona_v2_text_renderer as renderer
from eval import persona_v2_text_validator as validator
from eval import persona_v2_variant_catalog as variants


EXPECTED_CANONICAL_BYTES = 71_418
EXPECTED_CANONICAL_SHA256 = (
    "470be8c2c485a5ddbc70a0a11701e5cb789db7fde10d9e08995bb7a0ee085049"
)


class PersonaV2SourceProfileCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = catalog.build_source_profile_catalog()
        cls.upstream = variants.build_variant_catalog()

    def test_all_71_rows_and_exact_nine_ready_variants_are_explicit(self):
        value = self.value
        rows = value["source_profile_rows"]
        by_id = {row["variant_id"]: row for row in rows}
        ready = {
            row["variant_id"]
            for row in rows
            if row["bounded_feasibility"]["vertical_slice_ready"]
        }
        self.assertEqual(len(rows), 71)
        self.assertEqual(len(by_id), 71)
        self.assertEqual(set(by_id), set(envelope.VARIANT_CATALOG))
        self.assertEqual(ready, set(renderer.READY_VARIANTS))
        self.assertEqual(len(ready), 9)
        self.assertEqual(set(value["remaining_variant_ids"]), set(by_id) - ready)
        self.assertEqual(len(value["remaining_variant_ids"]), 62)
        self.assertEqual(
            [row["variant_id"] for row in rows],
            [
                row["variant_id"]
                for row in self.upstream["variant_rows"]
            ],
        )

        for variant_id, row in by_id.items():
            expected = variant_id in ready
            feasibility = row["bounded_feasibility"]
            self.assertIs(feasibility["vertical_slice_ready"], expected)
            self.assertIs(feasibility["renderer_implemented"], expected)
            self.assertIs(
                feasibility["independent_validator_implemented"], expected
            )
            self.assertIs(
                feasibility["byte_and_complexity_parameters_complete"],
                expected,
            )
            if expected:
                self.assertNotEqual(
                    row["bounded_feasibility_profile_id"], "not-bound"
                )
                self.assertEqual(row["source_recipe_profile_id"], "not-bound")
                self.assertIs(row["byte_formula"]["parameters_complete"], True)
                self.assertIs(
                    row["complexity_contract"]["parameters_complete"], True
                )
                self.assertEqual(
                    row["implementation_bindings"]["renderer_id"],
                    renderer.RENDERER_ID,
                )
                self.assertEqual(
                    row["implementation_bindings"]["validator_id"],
                    validator.VALIDATOR_ID,
                )
            else:
                self.assertEqual(
                    row["bounded_feasibility_profile_id"], "not-bound"
                )
                self.assertEqual(row["source_recipe_profile_id"], "not-bound")
                self.assertEqual(
                    row["byte_formula"], {"parameters_complete": False}
                )
                self.assertEqual(
                    row["complexity_contract"], {"parameters_complete": False}
                )
                self.assertEqual(
                    row["implementation_bindings"],
                    {
                        "renderer_id": "not-bound",
                        "validator_id": "not-bound",
                        "validator_profile_id": "not-bound",
                    },
                )

    def test_metadata_is_an_exact_projection_of_the_bound_variant_catalog(self):
        value = self.value
        upstream = self.upstream
        upstream_by_id = {
            row["variant_id"]: row for row in upstream["variant_rows"]
        }
        fields = (
            "family",
            "filename_extension",
            "content_media_type",
            "expected_kcs_path_media_type",
            "expected_offline_disposition",
            "gate_role",
        )
        for row in value["source_profile_rows"]:
            upstream_row = upstream_by_id[row["variant_id"]]
            self.assertEqual(
                {field: row[field] for field in fields},
                {field: upstream_row[field] for field in fields},
            )
            self.assertEqual(
                row["upstream_planned_renderer_id"],
                upstream_row["renderer"]["renderer_id"],
            )
            self.assertEqual(
                row["upstream_planned_validator_id"],
                upstream_row["validator"]["validator_id"],
            )

    def test_coverage_arithmetic_is_exact_after_ratio_correction(self):
        value = self.value
        self.assertEqual(
            value["coverage"],
            {
                "all_variant_count": 71,
                "not_ready_variant_count": 62,
                "ready_active_persona_variant_rows": 96,
                "ready_persona_variant_rows": 96,
                "ready_source_counts": {
                    "tiny_smoke_count": 730,
                    "pilot_count": 3_957,
                    "full_count": 39_556,
                    "full_minus_pilot_count": 35_599,
                },
                "ready_variant_count": 9,
            },
        )

    def test_bindings_are_one_way_exact_and_non_authorizing(self):
        value = self.value
        bindings = value["input_bindings"]
        self.assertEqual(
            bindings["planning_chain"], input_bindings.build_upstream_bindings()
        )
        upstream = self.upstream
        self.assertEqual(
            bindings["variant_catalog"]["sha256"],
            variants.variant_catalog_sha256(upstream),
        )
        self.assertEqual(
            bindings["variant_catalog"]["canonical_bytes"],
            len(variants.canonical_json_bytes(upstream)),
        )
        self.assertEqual(
            bindings["id_free_text_renderer"]["sha256"],
            renderer.renderer_contract_sha256(),
        )
        self.assertEqual(
            bindings["id_free_text_validator"]["sha256"],
            validator.validator_contract_sha256(),
        )
        for name, flag in value["authority"].items():
            self.assertIs(type(flag), bool, name)
            self.assertIs(flag, False, name)
        self.assertIs(value["g0_contract_frozen"], False)
        self.assertIs(value["source_profile_catalog_complete"], False)
        self.assertIs(
            value["bounded_feasibility_vertical_slice_complete"], True
        )
        self.assertIs(value["source_profile_vertical_slice_complete"], False)
        with self.assertRaises(catalog.PersonaV2SourceProfileCatalogError):
            catalog.require_complete_source_profile_catalog()

        sidecar_name = "persona_v2_source_profile_catalog"
        self.assertNotIn(sidecar_name, inspect.getsource(renderer))
        self.assertNotIn(sidecar_name, inspect.getsource(validator))
        self.assertNotIn(sidecar_name, inspect.getsource(variants))

    def test_canonical_cap_independent_hash_tamper_and_detachment(self):
        value = copy.deepcopy(self.value)
        raw = catalog.canonical_json_bytes(value)
        self.assertEqual(len(raw), EXPECTED_CANONICAL_BYTES)
        self.assertLessEqual(len(raw), catalog.MAX_CATALOG_BYTES)
        self.assertEqual(
            catalog.source_profile_catalog_sha256(value),
            EXPECTED_CANONICAL_SHA256,
        )
        self.assertEqual(hashlib.sha256(raw).hexdigest(), EXPECTED_CANONICAL_SHA256)
        self.assertTrue(catalog.validate_source_profile_catalog(value))

        forged = copy.deepcopy(value)
        forged["source_profile_rows"][0]["bounded_feasibility"][
            "vertical_slice_ready"
        ] = not forged["source_profile_rows"][0]["bounded_feasibility"][
            "vertical_slice_ready"
        ]
        with self.assertRaises(catalog.PersonaV2SourceProfileCatalogError):
            catalog.validate_source_profile_catalog(forged)

        strict = copy.deepcopy(value)
        strict["coverage"]["ready_variant_count"] = True
        with self.assertRaises(catalog.PersonaV2SourceProfileCatalogError):
            catalog.validate_source_profile_catalog(strict)

        value["source_profile_rows"][0]["variant_id"] = "poisoned"
        self.assertNotEqual(
            catalog.build_source_profile_catalog()["source_profile_rows"][0][
                "variant_id"
            ],
            "poisoned",
        )

    def test_hashseed_timezone_and_locale_do_not_change_the_sidecar(self):
        script = (
            "from eval import persona_v2_source_profile_catalog as c; "
            "v=c.build_source_profile_catalog(); "
            "print(c.source_profile_catalog_sha256(v),len(c.canonical_json_bytes(v)))"
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
