"""Focused tests for relation and source-instance parameter projections."""

from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import json
import unittest
from unittest import mock

from eval import persona_v2_concrete_overlay_membership_package as concrete
from eval import persona_v2_semantic_projection_relations_parameters as package
from eval import (
    persona_v2_semantic_projection_relations_parameters_validator as independent,
)
from eval import persona_v2_source_parameter_assignment_package as parameters


EXPECTED_LEDGER_BYTES = 230_661
EXPECTED_LEDGER_SHA256 = (
    "07171dbd80be9ba45976ad25afd03c7cf57ac3abec379c477f17b65fd0c4d516"
)
EXPECTED_TOTAL_BODY_BYTES = 26_619_238
EXPECTED_RELATION_BODY_BYTES = 8_988_409
EXPECTED_RELATION_MAX_BODY_BYTES = 658_944
EXPECTED_RELATION_MAX_ROW_BYTES = 388
EXPECTED_CELL_BODY_BYTES = 103_149
EXPECTED_CELL_BODY_SHA256 = (
    "f215f54910fad0945f8975d5ab544f71b095fdd5b81b66c1aca8e94bc703594b"
)
EXPECTED_ASSIGNMENT_MAX_BODY_BYTES = 367_471
EXPECTED_ASSIGNMENT_MAX_ROW_BYTES = 110
EXPECTED_UNUSED_PARAMETER_CELL_KEYS = frozenset(
    {
        "archive-zip/ordinary-max",
        "lms-ustar/ordinary-max",
        "model-metadata-zip/ordinary-max",
        "npz/ordinary-max",
        "product-export-zip/ordinary-max",
        "session-ustar/ordinary-max",
        "snapshot-ustar/ordinary-max",
        "team-export-ustar/ordinary-max",
        "tiff-ustar/ordinary-max",
    }
)


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _pin_ledger(materials):
    return [
        {
            "artifact_kind": material["artifact_kind"],
            "artifact_schema": material["artifact_schema"],
            "artifact_schema_version": material["artifact_schema_version"],
            "body_bytes": len(material["bytes"]),
            "body_sha256": _sha256(material["bytes"]),
            "class_id": material["class_id"],
            "coordinates": material["coordinates"],
            "direct_body_pins": material["direct_body_pins"],
            "framing": material["framing"],
            "full_owner_pins": material["full_owner_pins"],
        }
        for material in materials
    ]


def _rows(materials):
    for material in materials:
        if material["framing"] == "canonical-jsonl-lf":
            yield from material["bytes"].splitlines(keepends=True)


class PersonaV2SemanticProjectionRelationsParametersStaticTests(
    unittest.TestCase
):
    def test_public_contract_and_independent_import_boundary(self):
        self.assertEqual(
            package.CLASS_ORDER,
            ("concrete-overlay-relations", "source-instance-parameters"),
        )
        self.assertEqual(package.EXPECTED_MATERIAL_COUNT, 114)
        self.assertEqual(package.EXPECTED_RELATION_BODY_COUNT, 40)
        self.assertEqual(package.EXPECTED_RELATION_ROW_COUNT, 25_560)
        self.assertEqual(package.EXPECTED_CELL_COUNT, 363)
        self.assertEqual(package.EXPECTED_ASSIGNMENT_BODY_COUNT, 73)
        self.assertEqual(package.EXPECTED_ASSIGNMENT_ROW_COUNT, 203_000)
        self.assertEqual(package.EXPECTED_ASSIGNMENT_BODY_BYTES, 17_527_680)
        self.assertEqual(package.MATERIAL_FIELDS, independent.MATERIAL_FIELDS)
        self.assertEqual(package.FULL_OWNER_PIN_FIELDS, independent.FULL_OWNER_PIN_FIELDS)
        self.assertEqual(
            package.DIRECT_BODY_PIN_FIELDS,
            independent.DIRECT_BODY_PIN_FIELDS,
        )
        for name in (
            "iter_relations_parameter_projection_materials",
            "projection_body_bytes",
            "validate_projection_body",
        ):
            self.assertTrue(callable(getattr(package, name)))
        for name in (
            "iter_expected_relations_parameter_projection_materials",
            "validate_projection_body",
            "validate_all_relations_parameter_projection_bodies",
            "reauthenticate_all_projection_owners",
        ):
            self.assertTrue(callable(getattr(independent, name)))

        tree = ast.parse(inspect.getsource(independent))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
                imports.extend(alias.name for alias in node.names)
        self.assertFalse(
            any(
                name.endswith(
                    "persona_v2_semantic_projection_relations_parameters"
                )
                for name in imports
            ),
            imports,
        )
        self.assertIs(type(package.CONCRETE_SUITE_PIN), tuple)
        self.assertIs(type(package.PARAMETER_SUITE_PIN), tuple)
        self.assertIs(type(independent.CONCRETE_SUITE_PIN), tuple)
        self.assertIs(type(independent.PARAMETER_SUITE_PIN), tuple)

    def test_invalid_coordinates_and_non_bytes_fail_before_owner_work(self):
        error = independent.PersonaV2SemanticProjectionRelationsParametersValidationError
        with self.assertRaises(error):
            independent.validate_projection_body("unknown", {}, b"{}")
        with self.assertRaises(error):
            independent.validate_projection_body(
                package.RELATION_CLASS_ID,
                {"persona_id": "p01"},
                b"{}",
            )
        with self.assertRaises(error):
            independent.validate_projection_body(
                package.PARAMETER_CLASS_ID,
                {"parameter_catalog_id": "wrong"},
                b"{}",
            )
        with self.assertRaises(error):
            independent.validate_projection_body(
                package.PARAMETER_CLASS_ID,
                {"parameter_catalog_id": "global-source-parameter-cells-v1"},
                bytearray(b"{}"),
            )
        class BytesSubclass(bytes):
            pass

        with self.assertRaises(error):
            independent.validate_projection_body(
                package.PARAMETER_CLASS_ID,
                {"parameter_catalog_id": "global-source-parameter-cells-v1"},
                BytesSubclass(b"{}"),
            )

    def test_all_coordinate_shapes_and_exact_builtin_types(self):
        relation = {"origin": "pilot", "persona_id": "p01"}
        cell = {"parameter_catalog_id": "global-source-parameter-cells-v1"}
        assignment = {
            "origin": "full-residual",
            "persona_id": "p20",
            "source_shard_id": "source-shard-0001",
            "source_shard_ordinal": 1,
        }
        for class_id, coordinates, expected_kind in (
            (package.RELATION_CLASS_ID, relation, "relation"),
            (package.PARAMETER_CLASS_ID, cell, "cell"),
            (package.PARAMETER_CLASS_ID, assignment, "assignment"),
        ):
            with self.subTest(coordinates=coordinates):
                self.assertEqual(
                    package._require_coordinates(class_id, coordinates),
                    expected_kind,
                )
                self.assertIs(type(independent._coordinate_key(class_id, coordinates)), tuple)

        class DictSubclass(dict):
            pass

        class StringSubclass(str):
            pass

        class IntegerSubclass(int):
            pass

        invalid = (
            (package.RELATION_CLASS_ID, DictSubclass(relation)),
            (
                package.RELATION_CLASS_ID,
                {StringSubclass("origin"): "pilot", "persona_id": "p01"},
            ),
            (
                package.RELATION_CLASS_ID,
                {"origin": "pilot", "persona_id": StringSubclass("p01")},
            ),
            (
                package.PARAMETER_CLASS_ID,
                {
                    **assignment,
                    "source_shard_id": StringSubclass("source-shard-0001"),
                },
            ),
            (
                package.PARAMETER_CLASS_ID,
                {
                    **assignment,
                    "source_shard_ordinal": IntegerSubclass(1),
                },
            ),
        )
        for class_id, coordinates in invalid:
            with self.subTest(coordinates=coordinates):
                with self.assertRaises(
                    package.PersonaV2SemanticProjectionRelationsParametersError
                ):
                    package._require_coordinates(class_id, coordinates)
                with self.assertRaises(
                    independent.PersonaV2SemanticProjectionRelationsParametersValidationError
                ):
                    independent._coordinate_key(class_id, coordinates)

    def test_coordinate_and_body_caps_run_before_canonicalization_or_owners(self):
        error = independent.PersonaV2SemanticProjectionRelationsParametersValidationError
        huge_key = "x" * 1_000_000
        huge_coordinates = {huge_key: "value"}
        with mock.patch.object(
            independent, "_snapshot", side_effect=AssertionError("late snapshot")
        ):
            with self.assertRaises(error):
                independent.validate_projection_body(
                    package.PARAMETER_CLASS_ID, huge_coordinates, b"{}"
                )

        assignment_coordinates = {
            "origin": "pilot",
            "persona_id": "p01",
            "source_shard_id": "x" * 1_000_000,
            "source_shard_ordinal": 1,
        }
        with (
            mock.patch.object(
                independent,
                "_snapshot",
                side_effect=AssertionError("late snapshot"),
            ),
            mock.patch.object(
                independent,
                "_expected_material",
                side_effect=AssertionError("late owner"),
            ),
        ):
            with self.assertRaises(error):
                independent.validate_projection_body(
                    package.PARAMETER_CLASS_ID,
                    assignment_coordinates,
                    b"{}",
                )
        with mock.patch.object(
            package,
            "_parameter_origin",
            side_effect=AssertionError("late owner"),
        ):
            with self.assertRaises(
                package.PersonaV2SemanticProjectionRelationsParametersError
            ):
                package.projection_body_bytes(
                    package.PARAMETER_CLASS_ID, assignment_coordinates
                )

        cell_coordinates = {
            "parameter_catalog_id": "global-source-parameter-cells-v1"
        }
        oversized = b"x" * (package.MAX_CELL_BODY_BYTES + 1)
        with (
            mock.patch.object(
                independent,
                "_snapshot",
                side_effect=AssertionError("late snapshot"),
            ),
            mock.patch.object(
                independent,
                "_expected_material",
                side_effect=AssertionError("late owner"),
            ),
        ):
            with self.assertRaises(error):
                independent.validate_projection_body(
                    package.PARAMETER_CLASS_ID, cell_coordinates, oversized
                )
        with mock.patch.object(
            independent,
            "_expected_material",
            side_effect=AssertionError("late owner"),
        ):
            with self.assertRaises(error):
                independent._call_provider(
                    lambda _class_id, _coordinates: oversized,
                    package.PARAMETER_CLASS_ID,
                    cell_coordinates,
                    replay=False,
                )

    def test_rich_descriptor_and_skipped_anchor_schema_regressions(self):
        rich = b"{}\n"
        descriptor = {key: None for key in concrete.SHARD_DESCRIPTOR_FIELDS}
        descriptor.update(
            {
                "body_bytes": 1,
                "body_sha256": _sha256(rich),
                "file_name": (
                    "p01-concrete-overlay-membership-pilot-0000.jsonl"
                ),
                "maximum_row_bytes_including_lf": len(rich),
                "origin": "pilot",
                "persona_id": "p01",
                "row_count": 1,
                "shard_index": 0,
            }
        )
        origin_value = {"shard_descriptors": [descriptor]}
        with self.assertRaises(
            package.PersonaV2SemanticProjectionRelationsParametersError
        ):
            package._require_rich_body_descriptor(
                origin_value, rich, persona_id="p01", origin="pilot"
            )
        with self.assertRaises(
            independent.PersonaV2SemanticProjectionRelationsParametersValidationError
        ):
            independent._require_rich_body_descriptor(
                origin_value, rich, persona_id="p01", origin="pilot"
            )

        malformed_anchor = {"row_kind": "semantic-anchor-membership"}
        with mock.patch.object(
            concrete,
            "iter_concrete_overlay_membership_origin_rows",
            return_value=iter([malformed_anchor]),
        ):
            with self.assertRaises(
                package.PersonaV2SemanticProjectionRelationsParametersError
            ):
                package._relation_body_cached.__wrapped__("p01", "pilot")
        with self.assertRaises(
            independent.PersonaV2SemanticProjectionRelationsParametersValidationError
        ):
            independent._project_relation_row(malformed_anchor)


class PersonaV2SemanticProjectionRelationsParametersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.materials = list(
            package.iter_relations_parameter_projection_materials()
        )
        cls.expected = list(
            independent.iter_expected_relations_parameter_projection_materials()
        )
        cls.by_schema = {
            schema: [
                material
                for material in cls.materials
                if material["artifact_schema"] == schema
            ]
            for schema in (
                package.RELATION_SCHEMA,
                package.CELL_SCHEMA,
                package.ASSIGNMENT_SCHEMA,
            )
        }

    def test_exact_stream_totals_schemas_and_test_owned_pin_golden(self):
        self.assertEqual(self.materials, self.expected)
        self.assertEqual(len(self.materials), 114)
        self.assertEqual(
            [len(self.by_schema[schema]) for schema in self.by_schema],
            [40, 1, 73],
        )
        coordinates = [
            (material["class_id"], _canonical(material["coordinates"]))
            for material in self.materials
        ]
        self.assertEqual(len(set(coordinates)), 114)

        ledger_raw = _canonical(_pin_ledger(self.materials))
        self.assertEqual(len(ledger_raw), EXPECTED_LEDGER_BYTES)
        self.assertEqual(_sha256(ledger_raw), EXPECTED_LEDGER_SHA256)
        self.assertEqual(
            sum(len(material["bytes"]) for material in self.materials),
            EXPECTED_TOTAL_BODY_BYTES,
        )

        relation = self.by_schema[package.RELATION_SCHEMA]
        relation_rows = list(_rows(relation))
        self.assertEqual(len(relation_rows), 25_560)
        self.assertEqual(
            sum(len(material["bytes"]) for material in relation),
            EXPECTED_RELATION_BODY_BYTES,
        )
        self.assertEqual(
            max(len(material["bytes"]) for material in relation),
            EXPECTED_RELATION_MAX_BODY_BYTES,
        )
        self.assertEqual(max(map(len, relation_rows)), EXPECTED_RELATION_MAX_ROW_BYTES)

        cell = self.by_schema[package.CELL_SCHEMA][0]
        self.assertEqual(len(cell["bytes"]), EXPECTED_CELL_BODY_BYTES)
        self.assertEqual(_sha256(cell["bytes"]), EXPECTED_CELL_BODY_SHA256)
        cell_value = json.loads(cell["bytes"])
        self.assertEqual(set(cell_value), package.CELL_PROJECTION_FIELDS)
        self.assertEqual(len(cell_value["parameter_cells"]), 363)
        self.assertTrue(
            all(
                set(row) == package.CELL_FIELDS
                for row in cell_value["parameter_cells"]
            )
        )

        assignments = self.by_schema[package.ASSIGNMENT_SCHEMA]
        assignment_rows = list(_rows(assignments))
        self.assertEqual(len(assignment_rows), 203_000)
        catalog_cell_keys = {
            row["parameter_cell_key"] for row in cell_value["parameter_cells"]
        }
        assignment_cell_keys = {
            json.loads(row)["parameter_cell_key"] for row in assignment_rows
        }
        self.assertEqual(len(assignment_cell_keys), 354)
        self.assertFalse(assignment_cell_keys - catalog_cell_keys)
        self.assertEqual(
            catalog_cell_keys - assignment_cell_keys,
            EXPECTED_UNUSED_PARAMETER_CELL_KEYS,
        )
        self.assertEqual(
            sum(len(material["bytes"]) for material in assignments),
            17_527_680,
        )
        self.assertEqual(
            max(len(material["bytes"]) for material in assignments),
            EXPECTED_ASSIGNMENT_MAX_BODY_BYTES,
        )
        self.assertEqual(
            max(map(len, assignment_rows)), EXPECTED_ASSIGNMENT_MAX_ROW_BYTES
        )

    def test_material_fields_pins_body_dispatch_and_content_boundaries(self):
        forbidden = {
            "payload_seed_rule",
            "source_or_shared_payload_seed_rule",
        }
        for material in self.materials:
            with self.subTest(coordinates=material["coordinates"]):
                self.assertEqual(set(material), package.MATERIAL_FIELDS)
                self.assertIs(type(material["bytes"]), bytes)
                self.assertEqual(
                    package.projection_body_bytes(
                        material["class_id"], material["coordinates"]
                    ),
                    material["bytes"],
                )
                for pin in material["full_owner_pins"]:
                    self.assertEqual(set(pin), package.FULL_OWNER_PIN_FIELDS)
                for pin in material["direct_body_pins"]:
                    self.assertEqual(set(pin), package.DIRECT_BODY_PIN_FIELDS)

        for material in self.by_schema[package.RELATION_SCHEMA]:
            for raw in material["bytes"].splitlines():
                row = json.loads(raw)
                fields = {
                    "content-relation": package.RELATION_CONTENT_FIELDS,
                    "attachment-membership": package.RELATION_ATTACHMENT_FIELDS,
                }[row["row_kind"]]
                self.assertEqual(set(row), fields)
                self.assertTrue(forbidden.isdisjoint(row))

        for material in self.by_schema[package.ASSIGNMENT_SCHEMA]:
            for raw in material["bytes"].splitlines():
                self.assertEqual(set(json.loads(raw)), package.ASSIGNMENT_ROW_FIELDS)

    def test_detached_materials_and_immutable_validator_raw_cache(self):
        producer_iterator = package.iter_relations_parameter_projection_materials()
        mutated = next(producer_iterator)
        sibling = next(producer_iterator)
        sibling_owner_sha = sibling["full_owner_pins"][0]["sha256"]
        self.assertIsNot(
            mutated["full_owner_pins"], sibling["full_owner_pins"]
        )
        self.assertIsNot(
            mutated["full_owner_pins"][0], sibling["full_owner_pins"][0]
        )
        mutated["coordinates"]["origin"] = "poisoned"
        mutated["full_owner_pins"][0]["sha256"] = "0" * 64
        self.assertEqual(
            sibling["full_owner_pins"][0]["sha256"], sibling_owner_sha
        )
        rebuilt = next(package.iter_relations_parameter_projection_materials())
        self.assertEqual(rebuilt, self.materials[0])
        self.assertNotEqual(mutated, rebuilt)

        expected_iterator = (
            independent.iter_expected_relations_parameter_projection_materials()
        )
        expected = next(expected_iterator)
        expected_sibling = next(expected_iterator)
        expected_sibling_sha = expected_sibling["direct_body_pins"][0]["sha256"]
        self.assertIsNot(
            expected["direct_body_pins"], expected_sibling["direct_body_pins"]
        )
        expected["direct_body_pins"][0]["sha256"] = "f" * 64
        self.assertEqual(
            expected_sibling["direct_body_pins"][0]["sha256"],
            expected_sibling_sha,
        )
        rebuilt_expected = next(
            independent.iter_expected_relations_parameter_projection_materials()
        )
        self.assertEqual(rebuilt_expected, self.expected[0])
        self.assertLessEqual(
            len(independent._EXPECTED_MATERIAL_RAW_CACHE),
            package.EXPECTED_MATERIAL_COUNT,
        )
        self.assertTrue(
            all(
                type(key) is tuple
                and type(raw) is tuple
                and len(raw) == 2
                and all(type(item) is bytes for item in raw)
                for key, raw in independent._EXPECTED_MATERIAL_RAW_CACHE.items()
            )
        )

    def test_representative_body_validation_and_tamper_rejection(self):
        samples = (
            self.by_schema[package.RELATION_SCHEMA][0],
            self.by_schema[package.CELL_SCHEMA][0],
            self.by_schema[package.ASSIGNMENT_SCHEMA][0],
        )
        error = independent.PersonaV2SemanticProjectionRelationsParametersValidationError
        for material in samples:
            with self.subTest(schema=material["artifact_schema"]):
                self.assertIs(
                    independent.validate_projection_body(
                        material["class_id"],
                        copy.deepcopy(material["coordinates"]),
                        material["bytes"],
                    ),
                    True,
                )

        material = samples[1]
        tampered = material["bytes"][:-1] + bytes([material["bytes"][-1] ^ 1])
        with self.assertRaises(error):
            independent.validate_projection_body(
                material["class_id"], material["coordinates"], tampered
            )
        self.assertIs(
            package.validate_projection_body(
                material["class_id"],
                copy.deepcopy(material["coordinates"]),
                material["bytes"],
            ),
            True,
        )

    def test_final_postflight_deduplicates_live_full_owner_builds(self):
        with (
            mock.patch.object(
                independent,
                "_load_concrete_suite",
                wraps=independent._load_concrete_suite,
            ) as concrete_suite,
            mock.patch.object(
                independent,
                "_load_concrete_origin",
                wraps=independent._load_concrete_origin,
            ) as concrete_origin,
            mock.patch.object(
                independent,
                "_load_parameter_suite",
                wraps=independent._load_parameter_suite,
            ) as parameter_suite,
            mock.patch.object(
                independent,
                "_load_parameter_origin",
                wraps=independent._load_parameter_origin,
            ) as parameter_origin,
            mock.patch.object(
                independent,
                "_load_cell_catalog",
                wraps=independent._load_cell_catalog,
            ) as cell_catalog,
        ):
            self.assertIs(
                independent.reauthenticate_all_projection_owners(), True
            )
        self.assertEqual(concrete_suite.call_count, 1)
        self.assertEqual(concrete_origin.call_count, 40)
        self.assertEqual(parameter_suite.call_count, 1)
        self.assertEqual(parameter_origin.call_count, 40)
        self.assertEqual(cell_catalog.call_count, 1)

    def test_provider_control_flow_replays_twice_and_checks_live_owners(self):
        material = self.by_schema[package.CELL_SCHEMA][0]
        calls = []

        def provider(class_id, coordinates):
            calls.append((class_id, copy.deepcopy(coordinates)))
            return material["bytes"]

        with (
            mock.patch.object(independent, "EXPECTED_MATERIAL_COUNT", 1),
            mock.patch.object(
                independent,
                "_open_expected_materials",
                return_value=[copy.deepcopy(material)],
            ),
            mock.patch.object(
                independent,
                "reauthenticate_all_projection_owners",
                return_value=True,
            ),
        ):
            self.assertIs(
                independent.validate_all_relations_parameter_projection_bodies(
                    provider
                ),
                True,
            )
        self.assertEqual(calls, [(material["class_id"], material["coordinates"])] * 2)

        tampered_cases = []
        wrong_framing = copy.deepcopy(self.expected)
        wrong_framing[0]["framing"] = "canonical-json"
        tampered_cases.append(wrong_framing)
        wrong_pin = copy.deepcopy(self.expected)
        wrong_pin[0]["direct_body_pins"][0]["sha256"] = "0" * 64
        tampered_cases.append(wrong_pin)
        for tampered_materials in tampered_cases:
            provider_calls = []
            with mock.patch.object(
                independent,
                "iter_expected_relations_parameter_projection_materials",
                return_value=iter(tampered_materials),
            ):
                with self.assertRaises(
                    independent.PersonaV2SemanticProjectionRelationsParametersValidationError
                ):
                    independent.validate_all_relations_parameter_projection_bodies(
                        lambda class_id, coordinates: provider_calls.append(
                            (class_id, coordinates)
                        )
                    )
            self.assertEqual(provider_calls, [])

        patcher = None

        def mutating_provider(class_id, coordinates):
            nonlocal patcher
            original = parameters.build_source_parameter_cell_catalog

            def poisoned():
                value = original()
                value["parameter_cells"][0]["target_bytes"] += 1
                return value

            patcher = mock.patch.object(
                parameters,
                "build_source_parameter_cell_catalog",
                poisoned,
            )
            patcher.start()
            return material["bytes"]

        try:
            with (
                mock.patch.object(independent, "EXPECTED_MATERIAL_COUNT", 1),
                mock.patch.object(
                    independent,
                    "_open_expected_materials",
                    return_value=[copy.deepcopy(material)],
                ),
                mock.patch.object(
                    independent,
                    "reauthenticate_all_projection_owners",
                    return_value=True,
                ),
                self.assertRaises(
                    independent.PersonaV2SemanticProjectionRelationsParametersValidationError
                ),
            ):
                independent.validate_all_relations_parameter_projection_bodies(
                    mutating_provider
                )
        finally:
            if patcher is not None:
                patcher.stop()

    def test_provider_failure_replay_copy_and_final_postflight_control(self):
        material = self.by_schema[package.CELL_SCHEMA][0]
        error = independent.PersonaV2SemanticProjectionRelationsParametersValidationError

        def patches(postflight):
            return (
                mock.patch.object(independent, "EXPECTED_MATERIAL_COUNT", 1),
                mock.patch.object(
                    independent,
                    "_open_expected_materials",
                    return_value=[copy.deepcopy(material)],
                ),
                mock.patch.object(
                    independent, "_reauthenticate_material_owners"
                ),
                mock.patch.object(
                    independent,
                    "reauthenticate_all_projection_owners",
                    postflight,
                ),
            )

        first_postflight = mock.Mock(return_value=True)
        first_patches = patches(first_postflight)
        with first_patches[0], first_patches[1], first_patches[2] as owners, first_patches[3]:
            with self.assertRaisesRegex(error, "provider failed"):
                independent.validate_all_relations_parameter_projection_bodies(
                    lambda _class_id, _coordinates: (_ for _ in ()).throw(
                        RuntimeError("first")
                    )
                )
        self.assertEqual(owners.call_count, 1)
        self.assertEqual(first_postflight.call_count, 2)

        replay_calls = 0
        replay_postflight = mock.Mock(return_value=True)

        def replay_failure(_class_id, _coordinates):
            nonlocal replay_calls
            replay_calls += 1
            if replay_calls == 2:
                raise RuntimeError("replay")
            return material["bytes"]

        replay_patches = patches(replay_postflight)
        with replay_patches[0], replay_patches[1], replay_patches[2] as owners, replay_patches[3]:
            with self.assertRaisesRegex(error, "during replay"):
                independent.validate_all_relations_parameter_projection_bodies(
                    replay_failure
                )
        self.assertEqual(replay_calls, 2)
        self.assertEqual(owners.call_count, 2)
        self.assertEqual(replay_postflight.call_count, 2)

        coordinate_images = []
        coordinate_ids = []
        copy_postflight = mock.Mock(return_value=True)

        def mutating_coordinates(_class_id, coordinates):
            coordinate_images.append(copy.deepcopy(coordinates))
            coordinate_ids.append(id(coordinates))
            coordinates["injected"] = True
            return material["bytes"]

        copy_patches = patches(copy_postflight)
        with copy_patches[0], copy_patches[1], copy_patches[2], copy_patches[3]:
            self.assertIs(
                independent.validate_all_relations_parameter_projection_bodies(
                    mutating_coordinates
                ),
                True,
            )
        self.assertEqual(
            coordinate_images,
            [material["coordinates"], material["coordinates"]],
        )
        self.assertNotEqual(coordinate_ids[0], coordinate_ids[1])
        self.assertNotIn("injected", material["coordinates"])
        self.assertEqual(copy_postflight.call_count, 2)

        nondeterministic_postflight = mock.Mock(return_value=True)
        nondeterministic_patches = patches(nondeterministic_postflight)
        with (
            nondeterministic_patches[0],
            nondeterministic_patches[1],
            nondeterministic_patches[2] as owners,
            nondeterministic_patches[3],
            mock.patch.object(
                independent,
                "_call_provider",
                side_effect=[b"first", b"replay"],
            ) as provider_call,
            mock.patch.object(independent, "_validate_body_semantics"),
        ):
            with self.assertRaisesRegex(error, "nondeterministic"):
                independent.validate_all_relations_parameter_projection_bodies(
                    lambda _class_id, _coordinates: material["bytes"]
                )
        self.assertEqual(provider_call.call_count, 2)
        self.assertEqual(owners.call_count, 2)
        self.assertEqual(nondeterministic_postflight.call_count, 2)

        false_postflight = mock.Mock(side_effect=[True, False])
        false_patches = patches(false_postflight)
        with false_patches[0], false_patches[1], false_patches[2], false_patches[3]:
            with self.assertRaisesRegex(error, "did not return exact True"):
                independent.validate_all_relations_parameter_projection_bodies(
                    lambda _class_id, _coordinates: material["bytes"]
                )
        self.assertEqual(false_postflight.call_count, 2)

    def test_warm_cache_poison_is_rejected_before_semantics_or_provider(self):
        material = self.by_schema[package.CELL_SCHEMA][0]
        error = independent.PersonaV2SemanticProjectionRelationsParametersValidationError
        original_catalog = parameters.build_source_parameter_cell_catalog

        def poisoned_catalog():
            value = original_catalog()
            value["parameter_cells"][0]["target_bytes"] += 1
            return value

        with (
            mock.patch.object(
                parameters,
                "build_source_parameter_cell_catalog",
                poisoned_catalog,
            ),
            mock.patch.object(
                independent, "_validate_body_semantics"
            ) as semantics,
        ):
            with self.assertRaises(error):
                independent.validate_projection_body(
                    material["class_id"],
                    copy.deepcopy(material["coordinates"]),
                    material["bytes"],
                )
        self.assertEqual(semantics.call_count, 0)

        provider_calls = 0
        patcher = mock.patch.object(
            parameters,
            "build_source_parameter_cell_catalog",
            poisoned_catalog,
        )
        patcher.start()

        def restoring_provider(_class_id, _coordinates):
            nonlocal provider_calls
            provider_calls += 1
            patcher.stop()
            return material["bytes"]

        def reauthenticate_cell_owner():
            independent._reauthenticate_material_owners(
                material["class_id"], material["coordinates"]
            )
            return True

        try:
            with (
                mock.patch.object(independent, "EXPECTED_MATERIAL_COUNT", 1),
                mock.patch.object(
                    independent,
                    "_open_expected_materials",
                    return_value=[copy.deepcopy(material)],
                ),
                mock.patch.object(
                    independent,
                    "reauthenticate_all_projection_owners",
                    side_effect=reauthenticate_cell_owner,
                ),
                self.assertRaises(error),
            ):
                independent.validate_all_relations_parameter_projection_bodies(
                    restoring_provider
                )
        finally:
            patcher.stop()
        self.assertEqual(provider_calls, 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
