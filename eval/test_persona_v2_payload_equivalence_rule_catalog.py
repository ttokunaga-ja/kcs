"""Focused contract tests for the global payload-equivalence rule catalog."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

try:
    from . import persona_v2_payload_equivalence_rule_catalog as catalog
    from . import persona_v2_payload_equivalence_rule_catalog_validator as validator
except ImportError:  # pragma: no cover - direct discovery compatibility
    import persona_v2_payload_equivalence_rule_catalog as catalog
    import persona_v2_payload_equivalence_rule_catalog_validator as validator


CATALOG_GOLDEN = (
    8_649,
    "00dc78f6dd54a06e2669ffaeea08afdb56d2fe6bd978d342ca10cc3ed5919128",
)
PROJECTION_GOLDEN = (
    4_288,
    "05f8124cd1bd09652701d38ffd702824f3cff8d40a161815969071cd678e14e1",
)
FRAGMENT_GOLDEN = (
    4_056,
    "91486a1d8b1190c187b8ca906cd16ace17d739896aaa77de3fd999bd847e2828",
)
UPSTREAM_GOLDENS = (
    (
        "persona-v2-overlay-contract",
        71_179,
        "e9154297f6dd5cf30ccbcc819d725cb08c533ec84a7b2df359937ddfb6517c23",
    ),
    (
        "persona-v2-source-semantic-membership-suite",
        49_837,
        "62394dd2a3544f7d6c332652e6799b7a60353e8e3aa6a87f80e0ff21590a2e28",
    ),
    (
        "persona-v2-concrete-overlay-membership-suite",
        51_133,
        "129eb05bd2331996742d69489f270f1012855d16cf8e47d5bd991a1b67305737",
    ),
    (
        "persona-v2-source-parameter-assignment-suite",
        72_535,
        "ed95d7875cb961d4fa054f6fa8a8a281cf6906724bc5f2524d9d046b2c3e8f1a",
    ),
)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _walk_keys(value):
    if type(value) is dict:
        for key, item in value.items():
            yield key
            yield from _walk_keys(item)
    elif type(value) is list:
        for item in value:
            yield from _walk_keys(item)


class PayloadEquivalenceRuleCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog_value = catalog.build_payload_equivalence_rule_catalog()
        cls.catalog_raw = catalog.canonical_json_bytes(cls.catalog_value)
        cls.projection_value = catalog.build_payload_equivalence_rules_projection()
        cls.projection_raw = catalog.canonical_json_bytes(cls.projection_value)
        cls.fragment_raw = bytes(catalog._rule_fragment_raw())
        cls.material = next(catalog.iter_payload_equivalence_projection_materials())

    def test_first_measurement_goldens_are_literal_and_frozen(self):
        self.assertEqual((len(self.catalog_raw), _sha(self.catalog_raw)), CATALOG_GOLDEN)
        self.assertEqual(
            (len(self.projection_raw), _sha(self.projection_raw)),
            PROJECTION_GOLDEN,
        )
        self.assertEqual(
            (len(self.fragment_raw), _sha(self.fragment_raw)),
            FRAGMENT_GOLDEN,
        )
        self.assertEqual(
            (validator.EXPECTED_CATALOG_BYTES, validator.EXPECTED_CATALOG_SHA256),
            CATALOG_GOLDEN,
        )
        self.assertEqual(
            (
                validator.EXPECTED_PROJECTION_BYTES,
                validator.EXPECTED_PROJECTION_SHA256,
            ),
            PROJECTION_GOLDEN,
        )
        self.assertEqual(
            (validator.EXPECTED_FRAGMENT_BYTES, validator.EXPECTED_FRAGMENT_SHA256),
            FRAGMENT_GOLDEN,
        )

    def test_catalog_and_projection_validate_independently(self):
        self.assertIs(
            validator.validate_payload_equivalence_rule_catalog(
                copy.deepcopy(self.catalog_value)
            ),
            True,
        )
        self.assertIs(
            validator.validate_payload_equivalence_rules_projection(
                copy.deepcopy(self.projection_value)
            ),
            True,
        )
        self.assertIs(
            validator.validate_projection_body(
                catalog.PROJECTION_CLASS_ID,
                {},
                bytes(self.projection_raw),
            ),
            True,
        )
        self.assertIs(validator.reauthenticate_all_projection_owners(), True)

    def test_complete_inventory_material_api_is_exact(self):
        materials = list(catalog.iter_payload_equivalence_projection_materials())
        self.assertEqual(len(materials), 1)
        material = materials[0]
        self.assertEqual(set(material), catalog.MATERIAL_FIELDS)
        self.assertEqual(material["projection_class_id"], "payload-equivalence-rules")
        self.assertEqual(material["coordinates"], {})
        self.assertEqual(material["body_framing"], "canonical-json")
        self.assertEqual(material["body"], self.projection_raw)
        self.assertEqual(
            catalog.projection_body_bytes("payload-equivalence-rules", {}),
            self.projection_raw,
        )
        independent = list(
            validator.iter_expected_payload_equivalence_projection_materials()
        )
        self.assertEqual(independent, materials)
        self.assertEqual(catalog.build_payload_equivalence_projection_materials(), materials)

    def test_full_owner_and_direct_fragment_chain_is_exact(self):
        owners = self.material["full_owner_pins"]
        self.assertEqual(len(owners), 5)
        principal = owners[0]
        self.assertEqual(principal["artifact_schema"], catalog.ARTIFACT_SCHEMA)
        self.assertEqual(principal["canonical_bytes"], CATALOG_GOLDEN[0])
        self.assertEqual(principal["sha256"], CATALOG_GOLDEN[1])
        self.assertTrue(all(set(row) == catalog.FULL_OWNER_PIN_FIELDS for row in owners))
        actual_upstream = tuple(
            (row["owner_id"], row["canonical_bytes"], row["sha256"])
            for row in owners[1:]
        )
        self.assertEqual(actual_upstream, UPSTREAM_GOLDENS)
        direct = self.material["direct_body_pins"]
        self.assertEqual(len(direct), 1)
        self.assertEqual(set(direct[0]), catalog.DIRECT_PIN_FIELDS)
        self.assertEqual(
            (direct[0]["canonical_bytes"], direct[0]["sha256"]),
            FRAGMENT_GOLDEN,
        )
        bindings = self.catalog_value["input_bindings"]
        self.assertEqual(
            tuple((row["name"], row["canonical_bytes"], row["sha256"]) for row in bindings),
            UPSTREAM_GOLDENS,
        )

    def test_five_rules_and_precedence_close_the_intended_semantics(self):
        projection = self.projection_value
        self.assertEqual(projection["rule_order"], list(catalog.RULE_ORDER))
        rules = {row["rule_id"]: row for row in projection["rules"]}
        self.assertEqual(list(rules), list(catalog.RULE_ORDER))
        self.assertEqual(
            rules["default"]["payload_equivalence_key_relation"],
            "equals-that-intent-deterministic-payload-seed",
        )
        self.assertEqual(
            rules["exact-duplicate"]["parameter_cell_relation"],
            "same-non-eml-parameter-cell-for-both-endpoints",
        )
        self.assertEqual(
            rules["exact-duplicate"]["raw_payload_relation"],
            "same-raw-sha256",
        )
        self.assertEqual(
            rules["near-revision"]["semantic_version_relation"],
            "anchor-v1-and-derivative-v2",
        )
        self.assertIn(
            "distinct-unordered-branches",
            rules["conflict-copy"]["logical_identity_relation"],
        )
        self.assertEqual(
            rules["decoded-attachment"]["decoded_payload_relation"],
            "embedded-decoded-member-exactly-equals-standalone-member",
        )
        self.assertIn(
            "exact-derivative-at-member-ordinal-one",
            rules["decoded-attachment"]["attachment_relation"],
        )
        self.assertTrue(
            projection["precedence_contract"][
                "attachment_rule_is_orthogonal_postcondition"
            ]
        )
        self.assertTrue(
            projection["precedence_contract"][
                "exact_attachment_overlap_is_transitive_not-a-sixth-rule"
            ]
        )

    def test_cross_owner_algebra_is_full_owner_only(self):
        summary = self.catalog_value["summary"]
        expected = {
            "attachment_exact_overlap_count": 1_390,
            "attachment_membership_count": 5_690,
            "attachment_only_source_count": 7_100,
            "conflict_endpoint_count": 3_120,
            "default_source_count": 156_160,
            "exact_endpoint_count": 10_160,
            "exact_equivalence_group_count": 5_080,
            "near_endpoint_count": 26_460,
            "relation_endpoint_count": 39_740,
            "source_intent_count": 203_000,
            "unique_overlay_source_count": 46_840,
            "unique_source_payload_equivalence_key_count": 197_920,
        }
        for key, value in expected.items():
            self.assertEqual(summary[key], value)
            self.assertNotIn(key, self.projection_value)
        self.assertEqual(
            summary["relation_endpoint_count"] + summary["attachment_only_source_count"],
            summary["unique_overlay_source_count"],
        )
        self.assertEqual(
            summary["source_intent_count"] - summary["exact_equivalence_group_count"],
            summary["unique_source_payload_equivalence_key_count"],
        )

    def test_authority_is_exact_false_and_projection_is_content_only(self):
        authority = self.catalog_value["authority"]
        self.assertEqual(set(authority), catalog.AUTHORITY_FIELDS)
        self.assertTrue(all(type(flag) is bool and flag is False for flag in authority.values()))
        self.assertIs(self.catalog_value["g0_contract_frozen"], False)
        forbidden = validator.FORBIDDEN_PROJECTION_KEY_TOKENS
        for key in _walk_keys(self.projection_value):
            tokens = set(key.lower().replace("-", "_").split("_"))
            self.assertFalse(tokens & forbidden, key)
        for absent in (
            "authority",
            "completion_claims",
            "input_bindings",
            "remaining_blockers",
            "summary",
        ):
            self.assertNotIn(absent, self.projection_value)

    def test_builder_and_material_results_are_detached(self):
        first = catalog.build_payload_equivalence_rule_catalog()
        first["rule_catalog"]["rules"][0]["rule_id"] = "poisoned"
        second = catalog.build_payload_equivalence_rule_catalog()
        self.assertEqual(second, self.catalog_value)
        first_material = next(catalog.iter_payload_equivalence_projection_materials())
        first_material["full_owner_pins"][0]["sha256"] = "0" * 64
        second_material = next(catalog.iter_payload_equivalence_projection_materials())
        self.assertEqual(second_material, self.material)
        self.assertIs(type(catalog._catalog_raw()), bytes)
        self.assertIs(type(catalog._rule_fragment_raw()), bytes)
        self.assertIs(type(catalog._projection_raw()), bytes)

    def test_rehashed_rule_and_catalog_mutations_fail_closed(self):
        mutations = []
        changed = copy.deepcopy(self.projection_value)
        changed["rules"][1]["raw_payload_relation"] = "different-raw-sha256"
        mutations.append(changed)
        reordered = copy.deepcopy(self.projection_value)
        reordered["rules"] = list(reversed(reordered["rules"]))
        mutations.append(reordered)
        extra = copy.deepcopy(self.projection_value)
        extra["unexpected"] = True
        mutations.append(extra)
        boolean_alias = copy.deepcopy(self.projection_value)
        boolean_alias["rules"][0]["precedence_ordinal"] = True
        mutations.append(boolean_alias)
        null_value = copy.deepcopy(self.projection_value)
        null_value["rules"][0]["attachment_relation"] = None
        mutations.append(null_value)
        float_value = copy.deepcopy(self.projection_value)
        float_value["rules"][0]["precedence_ordinal"] = 1.0
        mutations.append(float_value)
        for mutation in mutations:
            with self.subTest(mutation=mutation.get("unexpected", "rule")):
                with self.assertRaises(Exception):
                    validator.validate_payload_equivalence_rules_projection(mutation)
        forged = copy.deepcopy(self.catalog_value)
        forged["input_bindings"][0]["sha256"] = "0" * 64
        with self.assertRaises(Exception):
            validator.validate_payload_equivalence_rule_catalog(forged)

    def test_invalid_dispatch_metadata_invokes_no_owner_callback(self):
        with mock.patch.object(
            validator,
            "_fresh_owner_records",
            side_effect=AssertionError("must not be invoked"),
        ) as provider:
            bad_calls = (
                ("unknown", {}, self.projection_raw),
                (catalog.PROJECTION_CLASS_ID, {"origin": "pilot"}, self.projection_raw),
                (catalog.PROJECTION_CLASS_ID, {}, bytearray(self.projection_raw)),
                (catalog.PROJECTION_CLASS_ID, {}, b"x" * (catalog.MAX_PROJECTION_BYTES + 1)),
            )
            for args in bad_calls:
                with self.subTest(args=args[:2]):
                    with self.assertRaises(Exception):
                        validator.validate_projection_body(*args)
            provider.assert_not_called()

    def test_full_owner_and_direct_pin_mutation_are_rejected(self):
        with mock.patch.object(validator, "SEMANTIC_OWNER_SHA256", "0" * 64):
            with self.assertRaises(Exception):
                validator.validate_projection_body(
                    catalog.PROJECTION_CLASS_ID, {}, self.projection_raw
                )
        with mock.patch.object(validator, "EXPECTED_FRAGMENT_SHA256", "0" * 64):
            with self.assertRaises(Exception):
                validator.validate_projection_body(
                    catalog.PROJECTION_CLASS_ID, {}, self.projection_raw
                )

    def test_owner_postflight_rejects_nondeterminism(self):
        original = validator.semantic.build_source_semantic_membership_suite_descriptor
        good = original()
        bad = copy.deepcopy(good)
        bad["summary"]["source_count"] += 1
        with mock.patch.object(
            validator.semantic,
            "build_source_semantic_membership_suite_descriptor",
            side_effect=[good, bad],
        ):
            with self.assertRaises(Exception):
                validator.validate_projection_body(
                    catalog.PROJECTION_CLASS_ID, {}, self.projection_raw
                )

    def test_sha_hashes_opening_image_and_reauthenticates_live_target(self):
        target = catalog.build_payload_equivalence_rule_catalog()

        def mutate_catalog(_snapshot):
            target["summary"]["rule_count"] = 6
            return True

        with mock.patch.object(
            catalog,
            "validate_payload_equivalence_rule_catalog",
            side_effect=mutate_catalog,
        ):
            with self.assertRaises(catalog.PersonaV2PayloadEquivalenceRuleCatalogError):
                catalog.payload_equivalence_rule_catalog_sha256(target)

        projection = catalog.build_payload_equivalence_rules_projection()

        def mutate_projection(_snapshot):
            projection["rule_order"].reverse()
            return True

        with mock.patch.object(
            catalog,
            "validate_payload_equivalence_rules_projection",
            side_effect=mutate_projection,
        ):
            with self.assertRaises(catalog.PersonaV2PayloadEquivalenceRuleCatalogError):
                catalog.payload_equivalence_rules_projection_sha256(projection)

    def test_independent_validator_has_no_sibling_producer_import(self):
        path = Path(validator.__file__)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        self.assertNotIn("persona_v2_payload_equivalence_rule_catalog", imported)

    @unittest.skipUnless(
        os.environ.get("KIO_RUN_COLD_HASH_SEED_TESTS") == "1",
        "set KIO_RUN_COLD_HASH_SEED_TESTS=1 for the two cold golden reproductions",
    )
    def test_two_cold_hash_seeds_reproduce_all_goldens(self):
        eval_dir = Path(__file__).resolve().parent
        script = (
            "import hashlib,json;"
            "import persona_v2_payload_equivalence_rule_catalog as m;"
            "c=m.canonical_json_bytes(m.build_payload_equivalence_rule_catalog());"
            "p=m.canonical_json_bytes(m.build_payload_equivalence_rules_projection());"
            "f=m._rule_fragment_raw();"
            "print(json.dumps([[len(c),hashlib.sha256(c).hexdigest()],"
            "[len(p),hashlib.sha256(p).hexdigest()],"
            "[len(f),hashlib.sha256(f).hexdigest()]]))"
        )
        expected = [list(CATALOG_GOLDEN), list(PROJECTION_GOLDEN), list(FRAGMENT_GOLDEN)]
        for seed in ("1", "777"):
            environment = os.environ.copy()
            environment["PYTHONHASHSEED"] = seed
            environment["PYTHONPATH"] = str(eval_dir)
            completed = subprocess.run(
                [sys.executable, "-c", script],
                cwd=eval_dir.parent,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
                timeout=600,
            )
            self.assertEqual(json.loads(completed.stdout), expected)


if __name__ == "__main__":
    unittest.main()
