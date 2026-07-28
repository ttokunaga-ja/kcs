"""Focused tests for the twenty-two corpus-content projection bodies."""

from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

from eval import persona_v2_artifact_common as artifact_common
from eval import persona_v2_contract as envelope
from eval import persona_v2_semantic_projection_corpus_content as package
from eval import persona_v2_semantic_projection_corpus_content_validator as independent


EXPECTED_PRIMARY_PIN = (
    6_790,
    "31481eb3e11bd3038abc034b639ca064ba5942f1bb278d311af2fc62f3d35117",
)
EXPECTED_RECIPE_PIN = (
    250_388,
    "81a9fd5a44ac1cdda977ee4ed36fffdd6c0f9944bc41efb2cb4ef07d30819e7b",
)
EXPECTED_FACT_PINS = (
    ("p01", 22_997, "11890827739a1fb21ef77655df3d89bc6f12b13f94e6204d6cca9c979e20ebb1"),
    ("p02", 22_944, "15f9d67a362085242da120b1c5bd0d339ebfaabc912fc46e4cc4e649bc84b87c"),
    ("p03", 23_070, "19657da3b76598e4d3cd2fb5568d156c8b29f01c1f5973fee583f933cea2deb7"),
    ("p04", 23_165, "3283399ee1492c91d4ccac8622929f44691dfd997bf311a1d29d4c15eb8d1b8e"),
    ("p05", 23_132, "5c234f3aa5410b0167fa7711835c1e2434314a35b90a8465346d52c7dd27fd3c"),
    ("p06", 23_115, "b56421520368c2ba8a093441900b9c12907e85a81e3a781fafe509f819f86812"),
    ("p07", 23_252, "3469b7396b71f5a22055298890f0aa0c69b11a32d3240db7219874f1f8de8469"),
    ("p08", 23_102, "01e71a3bbdc317e099aa13f6b357f19054e7c217e133e2e2b877246299bef183"),
    ("p09", 23_142, "4688db1d2441d57d5eaae553c0ed40e277481a2d1a82ccee564f77af762b0e50"),
    ("p10", 23_092, "a2f936b0dd0abed5c1a9634518b22115bd03e77e0778c9cd382f6464e7dfa3eb"),
    ("p11", 23_022, "0bfb9745b0230c330502ccf6e1ce0de14203aebf2b712d5ae5fea7b98eff2ba6"),
    ("p12", 23_109, "f48de2395bb77e0ee83c48f2d831862ced4e2b38bc268e2325e39af13017bee0"),
    ("p13", 23_073, "928e10abed40189e6312c997cea2e99d5d1989a882f7fc8de6f70580e3888722"),
    ("p14", 23_019, "f47e1becb42fbcdd99d04f3e726610e87b55afe90b7e89e0da74261b330ae73e"),
    ("p15", 23_126, "4b4a1f613e879da5a2aeef5aafe7ed40aaa458b7e43e84a45f5ceb24ae26d161"),
    ("p16", 23_169, "71800547371c872309ce17329cc41a4d1627562ecd13f266e5ec926dd76e0de2"),
    ("p17", 23_066, "1c3239ac44a1670fbaa21b52fe562b48d2d200c2fbd16d4e079551abc53133e0"),
    ("p18", 23_066, "5179d39d6c72ecf5a7bdf07ee94071501d014a19459303f4cece9f660df4e5dc"),
    ("p19", 23_022, "b70ceeeee03af60afdf89e458a8884a777f7ddd15f02b7448c24688781e89a55"),
    ("p20", 23_133, "e225136c7db6b896d602e324ded9dfca385c389d37d31881df4b51349ad8f0f7"),
)
EXPECTED_BODY_AGGREGATE = (
    718_994,
    "8a0ad749f0dbe62afa052043005b57836829d7382b6a9bae836ba385a8ebd255",
)
EXPECTED_MATERIAL_SUMMARY = (
    95_720,
    "900f826d49494f1a7662ae805b942ae2976e0febb731c538f1edb8c82eb9b34a",
)

PRIMARY_TOP_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "fixture_id",
        "fixture_schema_version",
        "primary_use_case_rows",
    }
)
RECIPE_TOP_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "fixture_id",
        "fixture_schema_version",
        "policy_catalogs",
        "recipe_profile_rows",
    }
)
FACT_TOP_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "fixture_id",
        "fixture_schema_version",
        "graphs",
        "logical_time_contract",
        "persona_id",
        "predicate_catalog",
    }
)
PRIMARY_ROW_FIELDS = frozenset(
    {
        "desired_outcome",
        "persona_id",
        "primary_use_case_id",
        "required_families",
        "required_lifecycle_capabilities",
        "required_scope_role",
        "trigger",
    }
)
RECIPE_ROW_FIELDS = frozenset(
    {
        "chunk_policy_id",
        "complexity_byte_policy",
        "content_media_type",
        "content_policy",
        "expected_kio_path_media_type",
        "expected_offline_disposition",
        "family",
        "filename_policy",
        "format_feasibility_render_template_id",
        "gate_role",
        "recipe_profile_id",
        "renderer_policy",
        "safety_profile_id",
        "semantic_profile_id",
        "source_inventory_profile_id",
        "source_recipe_slot_id",
        "variant_id",
    }
)
FORBIDDEN_KEY_TOKENS = frozenset(
    {
        "answer",
        "authority",
        "blocker",
        "completion",
        "distractor",
        "latency",
        "oracle",
        "query",
        "receipt",
        "review",
        "sha256",
        "solution",
    }
)


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _walk_key_paths(value, path=()):
    if type(value) is dict:
        for key, item in value.items():
            current = path + (key,)
            yield current
            yield from _walk_key_paths(item, current)
    elif type(value) is list:
        for index, item in enumerate(value):
            yield from _walk_key_paths(item, path + (str(index),))


def _material_summary(materials):
    rows = []
    for material in materials:
        row = {
            key: copy.deepcopy(material[key])
            for key in (
                "artifact_kind",
                "artifact_schema",
                "artifact_schema_version",
                "class_id",
                "coordinates",
                "direct_body_pins",
                "framing",
                "full_owner_pins",
            )
        }
        row["canonical_bytes"] = len(material["bytes"])
        row["sha256"] = _sha256(material["bytes"])
        rows.append(row)
    return artifact_common.canonical_json_bytes(
        rows,
        label="corpus projection material test summary",
        max_bytes=128 * 2**10,
    )


class PersonaV2SemanticProjectionCorpusContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.primary = package.build_primary_use_case_corpus_content_projection()
        cls.recipe = package.build_recipe_content_filename_policy_content_projection()
        cls.facts = {
            persona_id: package.build_fact_graph_content_projection(persona_id)
            for persona_id in envelope.PERSONA_IDS
        }
        cls.materials = list(package.iter_corpus_content_projection_materials())
        cls.expected_materials = list(
            independent.iter_expected_corpus_content_projection_materials()
        )

    def test_exact_schemas_allowlists_and_test_owned_body_goldens(self):
        self.assertEqual(set(self.primary), PRIMARY_TOP_FIELDS)
        self.assertEqual(self.primary["artifact_schema"], package.PRIMARY_SCHEMA)
        self.assertEqual(self.primary["artifact_kind"], package.PRIMARY_KIND)
        self.assertEqual(len(self.primary["primary_use_case_rows"]), 20)
        self.assertEqual(
            [row["persona_id"] for row in self.primary["primary_use_case_rows"]],
            list(envelope.PERSONA_IDS),
        )
        self.assertTrue(
            all(set(row) == PRIMARY_ROW_FIELDS for row in self.primary["primary_use_case_rows"])
        )
        primary_raw = package.canonical_json_bytes(self.primary)
        self.assertEqual((len(primary_raw), _sha256(primary_raw)), EXPECTED_PRIMARY_PIN)
        self.assertLessEqual(len(primary_raw), package.TARGET_PRIMARY_BYTES)

        self.assertEqual(set(self.recipe), RECIPE_TOP_FIELDS)
        self.assertEqual(self.recipe["artifact_schema"], package.RECIPE_SCHEMA)
        self.assertEqual(self.recipe["artifact_kind"], package.RECIPE_KIND)
        self.assertEqual(len(self.recipe["recipe_profile_rows"]), 71)
        self.assertTrue(
            all(set(row) == RECIPE_ROW_FIELDS for row in self.recipe["recipe_profile_rows"])
        )
        self.assertEqual(
            set(self.recipe["policy_catalogs"]),
            {
                "dynamic_incidental_wave_cap_policy",
                "filename_core_policy",
                "gate_role_chunk_policies",
                "lane_contracts",
            },
        )
        recipe_raw = package.canonical_json_bytes(self.recipe)
        self.assertEqual((len(recipe_raw), _sha256(recipe_raw)), EXPECTED_RECIPE_PIN)
        self.assertLessEqual(len(recipe_raw), package.TARGET_RECIPE_BYTES)

        actual_fact_pins = []
        all_raws = [primary_raw, recipe_raw]
        for persona_id, expected_bytes, expected_sha256 in EXPECTED_FACT_PINS:
            value = self.facts[persona_id]
            self.assertEqual(set(value), FACT_TOP_FIELDS)
            self.assertEqual(value["artifact_schema"], package.FACT_SCHEMA)
            self.assertEqual(value["artifact_kind"], package.FACT_KIND)
            self.assertEqual(value["persona_id"], persona_id)
            self.assertEqual(len(value["graphs"]), 4)
            self.assertEqual(len(value["predicate_catalog"]), 7)
            raw = package.canonical_json_bytes(value)
            actual_fact_pins.append((persona_id, len(raw), _sha256(raw)))
            self.assertEqual((len(raw), _sha256(raw)), (expected_bytes, expected_sha256))
            self.assertLessEqual(len(raw), package.TARGET_FACT_BYTES)
            all_raws.append(raw)
        self.assertEqual(tuple(actual_fact_pins), EXPECTED_FACT_PINS)
        self.assertEqual(
            (sum(map(len, all_raws)), _sha256(b"".join(all_raws))),
            EXPECTED_BODY_AGGREGATE,
        )

        for class_id, value in (
            (package.PRIMARY_CLASS_ID, self.primary),
            (package.RECIPE_CLASS_ID, self.recipe),
            *((package.FACT_CLASS_ID, value) for value in self.facts.values()),
        ):
            for path in _walk_key_paths(value):
                key = path[-1]
                tokens = set(key.replace("_", "-").lower().split("-"))
                self.assertTrue(
                    tokens.isdisjoint(FORBIDDEN_KEY_TOKENS),
                    (class_id, ".".join(path)),
                )

    def test_exact_material_order_fields_pins_and_independent_reconstruction(self):
        self.assertEqual(len(self.materials), package.EXPECTED_MATERIAL_COUNT)
        self.assertEqual(self.materials, self.expected_materials)
        self.assertEqual(
            [row["class_id"] for row in self.materials],
            [package.PRIMARY_CLASS_ID, package.RECIPE_CLASS_ID]
            + [package.FACT_CLASS_ID] * 20,
        )
        self.assertEqual(
            [row["coordinates"] for row in self.materials],
            [package.PRIMARY_COORDINATES, package.RECIPE_COORDINATES]
            + [{"persona_id": persona_id} for persona_id in envelope.PERSONA_IDS],
        )
        expected_pin_counts = [(3, 3), (5, 6)] + [(6, 8)] * 20
        for material, pin_counts in zip(
            self.materials, expected_pin_counts, strict=True
        ):
            self.assertEqual(set(material), package.MATERIAL_FIELDS)
            self.assertEqual(material["framing"], package.BODY_FRAMING)
            self.assertEqual(
                (len(material["full_owner_pins"]), len(material["direct_body_pins"])),
                pin_counts,
            )
            self.assertTrue(
                all(set(pin) == package.FULL_OWNER_PIN_FIELDS for pin in material["full_owner_pins"])
            )
            self.assertTrue(
                all(set(pin) == package.DIRECT_PIN_FIELDS for pin in material["direct_body_pins"])
            )
            self.assertEqual(
                material["bytes"],
                package.projection_body_bytes(
                    material["class_id"], material["coordinates"]
                ),
            )
        summary_raw = _material_summary(self.materials)
        self.assertEqual(
            (len(summary_raw), _sha256(summary_raw)), EXPECTED_MATERIAL_SUMMARY
        )

        mutated = list(package.iter_corpus_content_projection_materials())
        mutated[0]["full_owner_pins"][0]["sha256"] = "0" * 64
        mutated[1]["coordinates"]["scope"] = "poisoned"
        self.assertEqual(
            list(package.iter_corpus_content_projection_materials()),
            self.expected_materials,
        )

    def test_dispatch_builds_only_the_selected_body_and_rejects_coordinates(self):
        with mock.patch.object(
            package, "_recipe_projection_raw", side_effect=AssertionError
        ) as recipe_builder, mock.patch.object(
            package, "_fact_projection_raw", side_effect=AssertionError
        ) as fact_builder:
            self.assertEqual(
                package.projection_body_bytes(
                    package.PRIMARY_CLASS_ID, {"scope": "suite"}
                ),
                package.canonical_json_bytes(self.primary),
            )
            recipe_builder.assert_not_called()
            fact_builder.assert_not_called()

        package._fact_owner_raw.cache_clear()
        package._fact_projection_raw.cache_clear()
        with mock.patch.object(
            package.fact_graph,
            "build_fact_graph_suite",
            side_effect=AssertionError("suite builder must not run"),
        ), mock.patch.object(
            package.fact_graph,
            "build_fact_graph",
            wraps=package.fact_graph.build_fact_graph,
        ) as one_builder:
            raw = package.projection_body_bytes(
                package.FACT_CLASS_ID, {"persona_id": "p03"}
            )
            self.assertEqual(raw, package.canonical_json_bytes(self.facts["p03"]))
            one_builder.assert_called_once_with("p03")

        builders = (
            mock.patch.object(package, "_primary_projection_raw", side_effect=AssertionError),
            mock.patch.object(package, "_recipe_projection_raw", side_effect=AssertionError),
            mock.patch.object(package, "_fact_projection_raw", side_effect=AssertionError),
        )
        with builders[0] as primary_builder, builders[1] as recipe_builder, builders[2] as fact_builder:
            with self.assertRaises(package.PersonaV2SemanticProjectionCorpusContentError):
                package.projection_body_bytes(package.FACT_CLASS_ID, {"persona_id": "p21"})
            with self.assertRaises(package.PersonaV2SemanticProjectionCorpusContentError):
                package.projection_body_bytes(package.RECIPE_CLASS_ID, {})
            with self.assertRaises(package.PersonaV2SemanticProjectionCorpusContentError):
                package.projection_body_bytes("unknown", {})
            primary_builder.assert_not_called()
            recipe_builder.assert_not_called()
            fact_builder.assert_not_called()

    def test_builders_are_detached_from_immutable_byte_caches(self):
        primary = package.build_primary_use_case_corpus_content_projection()
        primary["primary_use_case_rows"][0]["desired_outcome"] = "poisoned"
        self.assertEqual(
            package.build_primary_use_case_corpus_content_projection(), self.primary
        )

        recipe = package.build_recipe_content_filename_policy_content_projection()
        recipe["recipe_profile_rows"][0]["content_policy"].clear()
        self.assertEqual(
            package.build_recipe_content_filename_policy_content_projection(),
            self.recipe,
        )

        fact = package.build_fact_graph_content_projection("p01")
        fact["graphs"][0]["facts"].clear()
        self.assertEqual(package.build_fact_graph_content_projection("p01"), self.facts["p01"])

    def test_validator_import_boundary_and_fact_reconstruction_are_independent(self):
        tree = ast.parse(inspect.getsource(independent))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        self.assertFalse(
            any(
                name.endswith("persona_v2_semantic_projection_corpus_content")
                for name in imported
            ),
            imported,
        )
        self.assertFalse(
            any(name.endswith("persona_v2_fact_graph") for name in imported),
            imported,
        )

        shared = independent._fact_shared_state()
        with mock.patch.object(
            independent.envelope,
            "get_persona",
            side_effect=AssertionError("live envelope reread forbidden"),
        ):
            for index in (0, 9, 19):
                persona_id = envelope.PERSONA_IDS[index]
                self.assertEqual(
                    independent._fact_material(persona_id, shared),
                    self.materials[index + 2],
                )

    def test_public_and_independent_body_validation_fail_closed(self):
        cases = (
            (
                package.validate_primary_use_case_corpus_content_projection,
                independent.validate_primary_use_case_corpus_content_projection,
                self.primary,
            ),
            (
                package.validate_recipe_content_filename_policy_content_projection,
                independent.validate_recipe_content_filename_policy_content_projection,
                self.recipe,
            ),
        )
        for public_validator, independent_validator, value in cases:
            with self.subTest(schema=value["artifact_schema"]):
                self.assertIs(public_validator(copy.deepcopy(value)), True)
                self.assertIs(independent_validator(copy.deepcopy(value)), True)
        self.assertIs(
            package.validate_fact_graph_content_projection(
                "p01", copy.deepcopy(self.facts["p01"])
            ),
            True,
        )
        self.assertIs(
            independent.validate_fact_graph_content_projection(
                "p20", copy.deepcopy(self.facts["p20"])
            ),
            True,
        )

        primary_tamper = copy.deepcopy(self.primary)
        primary_tamper["primary_use_case_rows"][0]["desired_outcome"] = "poisoned"
        recipe_tamper = copy.deepcopy(self.recipe)
        del recipe_tamper["recipe_profile_rows"][0]["content_policy"]
        fact_tamper = copy.deepcopy(self.facts["p01"])
        fact_tamper["persona_id"] = "p02"
        for class_id, coordinates, value in (
            (package.PRIMARY_CLASS_ID, {"scope": "suite"}, primary_tamper),
            (package.RECIPE_CLASS_ID, {"scope": "suite"}, recipe_tamper),
            (package.FACT_CLASS_ID, {"persona_id": "p01"}, fact_tamper),
        ):
            raw = package.canonical_json_bytes(value)
            with self.subTest(class_id=class_id):
                with self.assertRaises(
                    independent.PersonaV2SemanticProjectionCorpusContentValidationError
                ):
                    independent.validate_projection_body(class_id, coordinates, raw)

        primary_raw = package.canonical_json_bytes(self.primary)
        for candidate in (bytearray(primary_raw), primary_raw + b" "):
            with self.assertRaises(
                independent.PersonaV2SemanticProjectionCorpusContentValidationError
            ):
                independent.validate_projection_body(
                    package.PRIMARY_CLASS_ID, {"scope": "suite"}, candidate
                )
        with self.assertRaises(
            independent.PersonaV2SemanticProjectionCorpusContentValidationError
        ):
            independent.validate_projection_body(
                package.PRIMARY_CLASS_ID, {}, primary_raw
            )

    def test_one_body_validation_reauthenticates_live_owner_and_direct_fragments(self):
        raw = package.projection_body_bytes(
            package.PRIMARY_CLASS_ID, {"scope": "suite"}
        )
        with mock.patch.object(
            independent, "_primary_material", wraps=independent._primary_material
        ) as rebuild:
            self.assertIs(
                independent.validate_projection_body(
                    package.PRIMARY_CLASS_ID, {"scope": "suite"}, raw
                ),
                True,
            )
            self.assertEqual(rebuild.call_count, 2)

        original = independent.use_case_catalog.build_primary_use_case_catalog
        owner_calls = 0

        def drifting_owner():
            nonlocal owner_calls
            value = original()
            if owner_calls:
                value["primary_use_cases"][0]["trigger"] = "poisoned"
            owner_calls += 1
            return value

        with mock.patch.object(
            independent.use_case_catalog,
            "build_primary_use_case_catalog",
            drifting_owner,
        ):
            with self.assertRaisesRegex(
                independent.PersonaV2SemanticProjectionCorpusContentValidationError,
                "owner rebuild failed",
            ):
                independent.validate_projection_body(
                    package.PRIMARY_CLASS_ID, {"scope": "suite"}, raw
                )
        self.assertEqual(owner_calls, 2)

    def test_snapshot_callbacks_cannot_mutate_detached_opening_images(self):
        value = {"identity": "opening"}

        def canonical(candidate):
            return artifact_common.canonical_json_bytes(
                candidate,
                label="snapshot mutation regression",
                max_bytes=1024,
            )

        def mutating_validator(candidate):
            candidate["identity"] = "mutated"
            return True

        with self.assertRaisesRegex(
            package.PersonaV2SemanticProjectionCorpusContentError,
            "detached opening body",
        ):
            package._validated_raw(
                value,
                validate=mutating_validator,
                canonical=canonical,
                label="producer snapshot",
            )
        with self.assertRaisesRegex(
            independent.PersonaV2SemanticProjectionCorpusContentValidationError,
            "detached opening body",
        ):
            independent._validated_value_raw(
                value,
                validate=mutating_validator,
                canonical=canonical,
                label="validator snapshot",
            )

        package._fact_shared_owner_raws.cache_clear()
        original_realism_builder = package.realism.build_realism_profile
        validator_patcher = None

        def mutating_envelope_validator(candidate):
            candidate["fixture_id"] = "poisoned"
            return True

        def realism_then_install_mutating_validator():
            nonlocal validator_patcher
            value = original_realism_builder()
            validator_patcher = mock.patch.object(
                package.envelope,
                "validate_envelope_contract",
                mutating_envelope_validator,
            )
            validator_patcher.start()
            return value

        try:
            with mock.patch.object(
                package.realism,
                "build_realism_profile",
                realism_then_install_mutating_validator,
            ):
                with self.assertRaisesRegex(
                    package.PersonaV2SemanticProjectionCorpusContentError,
                    "detached opening body",
                ):
                    package._fact_shared_owner_raws()
        finally:
            if validator_patcher is not None:
                validator_patcher.stop()

    def test_fact_data_semantic_drift_fails_before_projection_acceptance(self):
        raw = package.projection_body_bytes(
            package.FACT_CLASS_ID, {"persona_id": "p01"}
        )
        theme_rows = list(independent.fact_data.GRAPH_THEME_ROWS)
        themes = list(theme_rows[0][1])
        themes[0] = (themes[0][0], "invalid-kind")
        theme_rows[0] = (theme_rows[0][0], tuple(themes))
        with mock.patch.object(
            independent.fact_data, "GRAPH_THEME_ROWS", tuple(theme_rows)
        ):
            with self.assertRaisesRegex(
                independent.PersonaV2SemanticProjectionCorpusContentValidationError,
                "graph kind",
            ):
                independent.validate_projection_body(
                    package.FACT_CLASS_ID, {"persona_id": "p01"}, raw
                )

        checkpoints = list(independent.fact_data.CHECKPOINT_ROWS)
        checkpoints[1] = (checkpoints[1][0], checkpoints[0][1])
        with mock.patch.object(
            independent.fact_data, "CHECKPOINT_ROWS", tuple(checkpoints)
        ):
            with self.assertRaisesRegex(
                independent.PersonaV2SemanticProjectionCorpusContentValidationError,
                "strictly increasing",
            ):
                independent.validate_projection_body(
                    package.FACT_CLASS_ID, {"persona_id": "p01"}, raw
                )

        original_guard = independent._validate_fact_data_contract
        original_theme_rows = independent.fact_data.GRAPH_THEME_ROWS
        drifted_theme_rows = tuple(theme_rows)

        def snapshot_then_rebind_global():
            snapshot = original_guard()
            independent.fact_data.GRAPH_THEME_ROWS = drifted_theme_rows
            return snapshot

        with mock.patch.object(
            independent.fact_data, "GRAPH_THEME_ROWS", original_theme_rows
        ), mock.patch.object(
            independent,
            "_validate_fact_data_contract",
            snapshot_then_rebind_global,
        ):
            shared = independent._fact_shared_state()
            self.assertIs(
                independent.fact_data.GRAPH_THEME_ROWS, drifted_theme_rows
            )
            self.assertEqual(
                independent._fact_material("p01", shared), self.materials[2]
            )

        predicates = list(independent.fact_data.PREDICATE_ROWS)
        predicates[0] = (predicates[0][0], "invalid-kind")
        with mock.patch.object(
            independent.fact_data, "PREDICATE_ROWS", tuple(predicates)
        ):
            with self.assertRaisesRegex(
                independent.PersonaV2SemanticProjectionCorpusContentValidationError,
                "value kind",
            ):
                independent.validate_projection_body(
                    package.FACT_CLASS_ID, {"persona_id": "p01"}, raw
                )

        predicates = list(independent.fact_data.PREDICATE_ROWS)
        first_kind = predicates[0][1]
        second_kind = predicates[1][1]
        predicates[0] = (predicates[0][0], second_kind)
        predicates[1] = (predicates[1][0], first_kind)
        with mock.patch.object(
            independent.fact_data, "PREDICATE_ROWS", tuple(predicates)
        ):
            with self.assertRaisesRegex(
                independent.PersonaV2SemanticProjectionCorpusContentValidationError,
                "exact and unique",
            ):
                independent.validate_projection_body(
                    package.FACT_CLASS_ID, {"persona_id": "p01"}, raw
                )

        checkpoints = list(independent.fact_data.CHECKPOINT_ROWS)
        checkpoints[0] = ("renamed-W0", checkpoints[0][1])
        with mock.patch.object(
            independent.fact_data, "CHECKPOINT_ROWS", tuple(checkpoints)
        ):
            with self.assertRaisesRegex(
                independent.PersonaV2SemanticProjectionCorpusContentValidationError,
                "names/order",
            ):
                independent.validate_projection_body(
                    package.FACT_CLASS_ID, {"persona_id": "p01"}, raw
                )

    def test_material_body_cap_and_exact_coordinate_types_precede_detach(self):
        oversized = copy.deepcopy(self.materials[0])
        oversized["bytes"] = b"x" * (independent.MAX_PRIMARY_BYTES + 1)
        with mock.patch.object(
            independent,
            "_strict_loads",
            side_effect=AssertionError("detachment must not run"),
        ) as detach:
            with self.assertRaisesRegex(
                independent.PersonaV2SemanticProjectionCorpusContentValidationError,
                "class byte cap",
            ):
                independent._snapshot_material(oversized)
            detach.assert_not_called()

        class StringSubclass(str):
            pass

        raw = package.projection_body_bytes(
            package.PRIMARY_CLASS_ID, {"scope": "suite"}
        )
        for coordinates in (
            {"scope": StringSubclass("suite")},
            {StringSubclass("scope"): "suite"},
        ):
            with self.subTest(coordinates=coordinates):
                with self.assertRaises(
                    package.PersonaV2SemanticProjectionCorpusContentError
                ):
                    package.projection_body_bytes(
                        package.PRIMARY_CLASS_ID, coordinates
                    )
                with self.assertRaises(
                    independent.PersonaV2SemanticProjectionCorpusContentValidationError
                ):
                    independent.validate_projection_body(
                        package.PRIMARY_CLASS_ID, coordinates, raw
                    )

    def test_material_provider_replays_twice_and_detects_boundary_failures(self):
        calls = []

        def provider():
            calls.append(len(calls))
            return copy.deepcopy(self.materials)

        self.assertIs(
            independent.validate_corpus_content_projection_materials(provider), True
        )
        self.assertEqual(calls, [0, 1])

        expected_patch = mock.patch.object(
            independent,
            "iter_expected_corpus_content_projection_materials",
            side_effect=lambda: iter(copy.deepcopy(self.expected_materials)),
        )
        reauth_patch = mock.patch.object(
            independent, "_reauthenticate_against", return_value=True
        )
        with expected_patch, reauth_patch:
            replay_calls = []

            def nondeterministic():
                rows = copy.deepcopy(self.materials)
                if replay_calls:
                    rows[0], rows[1] = rows[1], rows[0]
                replay_calls.append(True)
                return rows

            with self.assertRaises(
                independent.PersonaV2SemanticProjectionCorpusContentValidationError
            ):
                independent.validate_corpus_content_projection_materials(
                    nondeterministic
                )
            self.assertEqual(len(replay_calls), 2)

        for result in (
            self.materials[:-1],
            self.materials + [copy.deepcopy(self.materials[-1])],
            {"not": "an iterable of materials"},
        ):
            with self.subTest(provider_result=type(result).__name__), mock.patch.object(
                independent,
                "iter_expected_corpus_content_projection_materials",
                side_effect=lambda: iter(copy.deepcopy(self.expected_materials)),
            ), mock.patch.object(
                independent, "_reauthenticate_against", return_value=True
            ):
                with self.assertRaises(
                    independent.PersonaV2SemanticProjectionCorpusContentValidationError
                ):
                    independent.validate_corpus_content_projection_materials(
                        lambda result=result: result
                    )

        with mock.patch.object(
            independent,
            "iter_expected_corpus_content_projection_materials",
            side_effect=lambda: iter(copy.deepcopy(self.expected_materials)),
        ), mock.patch.object(
            independent, "_reauthenticate_against", return_value=True
        ):
            with self.assertRaises(
                independent.PersonaV2SemanticProjectionCorpusContentValidationError
            ):
                independent.validate_corpus_content_projection_materials(
                    lambda: (_ for _ in ()).throw(RuntimeError("boom"))
                )

        def raises_during_iteration():
            yield copy.deepcopy(self.materials[0])
            raise RuntimeError("iteration boom")

        with mock.patch.object(
            independent,
            "iter_expected_corpus_content_projection_materials",
            side_effect=lambda: iter(copy.deepcopy(self.expected_materials)),
        ), mock.patch.object(
            independent, "_reauthenticate_against", return_value=True
        ):
            with self.assertRaisesRegex(
                independent.PersonaV2SemanticProjectionCorpusContentValidationError,
                "during iteration",
            ):
                independent.validate_corpus_content_projection_materials(
                    raises_during_iteration
                )

    def test_package_postflight_binds_live_owners_to_the_opening_image(self):
        original = independent.use_case_catalog.build_primary_use_case_catalog
        patcher = None
        provider_calls = 0

        def poisoned_owner():
            value = original()
            value["primary_use_cases"][0]["trigger"] = "poisoned"
            return value

        def provider():
            nonlocal patcher, provider_calls
            provider_calls += 1
            if patcher is None:
                patcher = mock.patch.object(
                    independent.use_case_catalog,
                    "build_primary_use_case_catalog",
                    poisoned_owner,
                )
                patcher.start()
            return copy.deepcopy(self.materials)

        try:
            with self.assertRaisesRegex(
                independent.PersonaV2SemanticProjectionCorpusContentValidationError,
                "owner rebuild failed",
            ):
                independent.validate_corpus_content_projection_materials(provider)
        finally:
            if patcher is not None:
                patcher.stop()
        self.assertEqual(provider_calls, 1)

    def test_material_metadata_tamper_and_toctou_fail_closed(self):
        tampered_cases = []
        wrong_pin = copy.deepcopy(self.materials)
        wrong_pin[0]["direct_body_pins"][0]["sha256"] = "0" * 64
        tampered_cases.append(wrong_pin)
        wrong_order = copy.deepcopy(self.materials)
        wrong_order[0], wrong_order[1] = wrong_order[1], wrong_order[0]
        tampered_cases.append(wrong_order)
        wrong_coordinate = copy.deepcopy(self.materials)
        wrong_coordinate[2]["coordinates"] = {"persona_id": "p20"}
        tampered_cases.append(wrong_coordinate)
        extra_owner = copy.deepcopy(self.materials)
        extra_owner[0]["full_owner_pins"].append(
            copy.deepcopy(extra_owner[0]["full_owner_pins"][0])
        )
        tampered_cases.append(extra_owner)

        for candidate in tampered_cases:
            with self.subTest(class_id=candidate[0]["class_id"]), mock.patch.object(
                independent,
                "iter_expected_corpus_content_projection_materials",
                side_effect=lambda: iter(copy.deepcopy(self.expected_materials)),
            ), mock.patch.object(
                independent, "_reauthenticate_against", return_value=True
            ):
                with self.assertRaises(
                    independent.PersonaV2SemanticProjectionCorpusContentValidationError
                ):
                    independent.validate_corpus_content_projection_materials(
                        lambda candidate=candidate: candidate
                    )

        mutable_rows = copy.deepcopy(self.materials)

        def mutating_provider():
            def rows():
                yield from mutable_rows
                mutable_rows[0]["coordinates"]["scope"] = "poisoned"

            return rows()

        with mock.patch.object(
            independent,
            "iter_expected_corpus_content_projection_materials",
            side_effect=lambda: iter(copy.deepcopy(self.expected_materials)),
        ), mock.patch.object(
            independent, "_reauthenticate_against", return_value=True
        ):
            with self.assertRaisesRegex(
                independent.PersonaV2SemanticProjectionCorpusContentValidationError,
                "mutated",
            ):
                independent.validate_corpus_content_projection_materials(
                    mutating_provider
                )

    def test_hashes_are_stable_across_hash_seed_and_timezone(self):
        script = """
import hashlib, json
from eval import persona_v2_contract as envelope
from eval import persona_v2_semantic_projection_corpus_content as package
coordinates = [
    (package.PRIMARY_CLASS_ID, {"scope": "suite"}),
    (package.RECIPE_CLASS_ID, {"scope": "suite"}),
] + [(package.FACT_CLASS_ID, {"persona_id": value}) for value in envelope.PERSONA_IDS]
rows = []
for class_id, coordinate in coordinates:
    raw = package.projection_body_bytes(class_id, coordinate)
    rows.append((class_id, coordinate, len(raw), hashlib.sha256(raw).hexdigest()))
print(json.dumps(rows, sort_keys=True, separators=(",", ":")))
"""
        outputs = []
        for seed, timezone in (("0", "UTC"), ("1", "Asia/Tokyo")):
            environment = os.environ.copy()
            environment.update(
                {
                    "LANG": "C",
                    "LC_ALL": "C",
                    "PYTHONHASHSEED": seed,
                    "TZ": timezone,
                }
            )
            outputs.append(
                subprocess.check_output(
                    [sys.executable, "-c", script],
                    cwd=os.path.dirname(os.path.dirname(__file__)),
                    env=environment,
                    text=True,
                ).strip()
            )
        self.assertEqual(outputs[0], outputs[1])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
