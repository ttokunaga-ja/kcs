"""Focused tests for the three standalone global content projections."""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib
import inspect
import os
import subprocess
import sys
import unittest
from unittest import mock

from eval import persona_v2_realism_profile as realism
from eval import persona_v2_route_affinity as route
from eval import persona_v2_semantic_projection_global_content as package
from eval import persona_v2_semantic_projection_global_content_validator as independent
from eval import persona_v2_topology as topology


EXPECTED_PROJECTION_PINS = {
    "topology-path-load": (
        133_187,
        "32b71dae205988d9671d6c3635bbe9690a03af4db363229c413f79c457375483",
    ),
    "realism-locale-security": (
        32_762,
        "9bf892c4cf71608c167e5dfcf168cad4fff125293689b178a5acc57dfb30130d",
    ),
    "route-scores": (
        88_085,
        "c088ba4cfabffd9474afee35d0874bfae45fd07a801ccd763bfe97b6d17ce535",
    ),
}
EXPECTED_DIRECT_FRAGMENT_PINS = {
    "topology-path-load-source-fragment": (
        132_561,
        "72cc4ce344e6b5ce6eda7a411b59ed8cf9ac89ba4248e381eba64a38fcefb3bb",
    ),
    "realism-locale-security-source-fragment": (
        32_196,
        "4119140b11132fa8213c8ca21c2b96fdc626d7ead167575e573c86e2fdf62197",
    ),
    "route-score-row-body": (
        69_762,
        "1e337e27433e73a1c4e9b5827138930b9a44cc8af5f88ee9e8bca1af45d85183",
    ),
    "topology-scope-axis-body": (
        17_284,
        "d9fa1f53526190c57a4a0a23ebfd09754c7decbcd04157bf4dc1f8a2a910e28c",
    ),
}
EXPECTED_OWNER_PINS = {
    "full-topology-owner-pin": (
        134_195,
        "02e0e68d37378a1123743673aad826757d17480de77a5a7313f09932c5759c4a",
    ),
    "full-realism-owner-pin": (
        36_811,
        "990139d3a544ad57ea77752a6a2de8d4345897e961ca85bd506bd1ee041b3fdb",
    ),
    "full-route-owner-pin": (
        70_626,
        "7536b815ed5f614db2c31d49138385c7be76c71d45d7fc30f3380b3a9ae3b957",
    ),
}
EXPECTED_SCHEMAS = {
    "topology-path-load": (
        "kio.persona.pc-topology-path-load-content-projection/v1",
        "persona-pc-v2-topology-path-load-content-projection",
    ),
    "realism-locale-security": (
        "kio.persona.pc-realism-locale-security-content-projection/v1",
        "persona-pc-v2-realism-locale-security-content-projection",
    ),
    "route-scores": (
        "kio.persona.pc-route-scores-content-projection/v1",
        "persona-pc-v2-route-scores-content-projection",
    ),
}
FORBIDDEN_KEY_TOKENS = frozenset(
    {
        "answer",
        "authority",
        "blocker",
        "completion",
        "distractor",
        "g0",
        "observed",
        "oracle",
        "query",
        "review",
        "runtime",
        "sha256",
        "solution",
    }
)


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _walk_keys(value):
    if type(value) is dict:
        for key, item in value.items():
            yield key
            yield from _walk_keys(item)
    elif type(value) is list:
        for item in value:
            yield from _walk_keys(item)


class PersonaV2SemanticProjectionGlobalContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.values = {
            "topology-path-load": (
                package.build_topology_path_load_content_projection()
            ),
            "realism-locale-security": (
                package.build_realism_locale_security_content_projection()
            ),
            "route-scores": package.build_route_scores_content_projection(),
        }
        cls.materials = list(package.iter_global_content_projection_materials())

    def test_exact_schemas_shapes_and_test_owned_golden_pins(self):
        self.assertEqual(tuple(self.values), package.CLASS_ORDER)
        for class_id, value in self.values.items():
            with self.subTest(class_id=class_id):
                schema, kind = EXPECTED_SCHEMAS[class_id]
                self.assertEqual(value["artifact_schema"], schema)
                self.assertEqual(value["artifact_kind"], kind)
                self.assertEqual(value["artifact_schema_version"], 1)
                self.assertEqual(value["fixture_id"], "kio-persona-pc-v2")
                self.assertEqual(value["fixture_schema_version"], 2)
                self.assertEqual(set(value), package.TOP_LEVEL_FIELDS)
                raw = package.canonical_json_bytes(value)
                self.assertEqual(
                    (len(raw), _sha256(raw)), EXPECTED_PROJECTION_PINS[class_id]
                )
                self.assertEqual(
                    package.global_content_projection_sha256(copy.deepcopy(value)),
                    EXPECTED_PROJECTION_PINS[class_id][1],
                )
                self.assertLessEqual(len(raw), package.TARGET_PROJECTION_BYTES)
                for key in _walk_keys(value):
                    tokens = frozenset(
                        token
                        for token in key.replace("_", "-").lower().split("-")
                        if token
                    )
                    self.assertTrue(
                        tokens.isdisjoint(FORBIDDEN_KEY_TOKENS),
                        (class_id, key),
                    )

        topology_value = self.values["topology-path-load"]
        self.assertEqual(
            topology_value["summary"],
            {
                "persona_count": 20,
                "primary_scope_count": 240,
                "scope_count": 400,
                "secondary_scope_count": 160,
            },
        )
        realism_value = self.values["realism-locale-security"]
        self.assertEqual(realism_value["summary"]["persona_count"], 20)
        self.assertTrue(
            realism_value["content_rules"][
                "os_semantics_are_declared_target_metadata_only"
            ]
        )
        self.assertTrue(
            all(
                "os_execution_mode" not in row
                for row in realism_value["content_sections"][
                    "persona_realism_rows"
                ]
            )
        )
        route_value = self.values["route-scores"]
        self.assertEqual(
            route_value["summary"],
            {
                "persona_count": 20,
                "route_score_cell_count": 10_820,
                "route_score_row_count": 541,
                "scope_axis_row_count": 400,
            },
        )

    def test_route_scope_axis_binds_every_ordinal_to_exact_scope_key(self):
        route_value = self.values["route-scores"]
        axes = route_value["content_sections"]["persona_scope_axes"]
        topology_value = topology.build_topology_contract()
        expected = [
            {
                "persona_id": persona["persona_id"],
                "scopes": [
                    {
                        "ordinal": scope["ordinal"],
                        "scope_key": scope["scope_key"],
                    }
                    for scope in persona["scopes"]
                ],
            }
            for persona in topology_value["personas"]
        ]
        self.assertEqual(axes, expected)
        axis_by_persona = {row["persona_id"]: row["scopes"] for row in axes}
        for row in route_value["content_sections"]["route_score_rows"]:
            self.assertEqual(len(row["scores_by_scope_ordinal"]), 20)
            self.assertEqual(
                [scope["ordinal"] for scope in axis_by_persona[row["persona_id"]]],
                list(range(1, 21)),
            )
        self.assertEqual(
            route_value["content_rules"]["score_zero_semantics"],
            "soft-no-specific-affinity-never-hard-eligibility-ban",
        )

    def test_material_api_matches_independent_reconstruction_and_exact_pins(self):
        expected = list(independent.iter_expected_global_content_projection_materials())
        self.assertEqual(self.materials, expected)
        self.assertEqual(
            tuple(row["class_id"] for row in self.materials), package.CLASS_ORDER
        )
        for material in self.materials:
            class_id = material["class_id"]
            self.assertEqual(set(material), package.MATERIAL_FIELDS)
            self.assertEqual(material["coordinates"], {})
            self.assertEqual(material["body_framing"], "canonical-json")
            self.assertEqual(
                (len(material["body"]), _sha256(material["body"])),
                EXPECTED_PROJECTION_PINS[class_id],
            )
            self.assertEqual(
                package.projection_body_bytes(class_id, {}), material["body"]
            )
            self.assertEqual(
                independent.expected_projection_body_bytes(class_id, {}),
                material["body"],
            )
            for pin in material["full_owner_pins"]:
                self.assertEqual(
                    (pin["canonical_bytes"], pin["sha256"]),
                    EXPECTED_OWNER_PINS[pin["owner_role"]],
                )
            for pin in material["direct_body_pins"]:
                self.assertEqual(
                    (pin["canonical_bytes"], pin["sha256"]),
                    EXPECTED_DIRECT_FRAGMENT_PINS[pin["direct_pin_role"]],
                )

        mutated = list(package.iter_global_content_projection_materials())
        mutated[0]["full_owner_pins"][0]["sha256"] = "0" * 64
        rebuilt = list(package.iter_global_content_projection_materials())
        self.assertEqual(rebuilt, expected)
        self.assertNotEqual(mutated, rebuilt)

    def test_public_and_independent_validation_reject_tampering(self):
        validators = {
            "topology-path-load": (
                package.validate_topology_path_load_content_projection,
                independent.validate_topology_path_load_content_projection,
            ),
            "realism-locale-security": (
                package.validate_realism_locale_security_content_projection,
                independent.validate_realism_locale_security_content_projection,
            ),
            "route-scores": (
                package.validate_route_scores_content_projection,
                independent.validate_route_scores_content_projection,
            ),
        }
        for class_id, value in self.values.items():
            for validator in validators[class_id]:
                with self.subTest(class_id=class_id, validator=validator.__module__):
                    self.assertIs(validator(copy.deepcopy(value)), True)

            tampered = copy.deepcopy(value)
            tampered["summary"]["persona_count"] = 19
            for validator in validators[class_id]:
                with self.assertRaises(
                    independent.PersonaV2SemanticProjectionGlobalContentValidationError
                ):
                    validator(copy.deepcopy(tampered))

        for class_id, value in self.values.items():
            raw = package.canonical_json_bytes(value)
            self.assertIs(independent.validate_projection_body(class_id, {}, raw), True)
            with self.assertRaises(
                independent.PersonaV2SemanticProjectionGlobalContentValidationError
            ):
                independent.validate_projection_body(class_id, {}, bytearray(raw))
            with self.assertRaises(
                independent.PersonaV2SemanticProjectionGlobalContentValidationError
            ):
                independent.validate_projection_body(class_id, {"persona_id": "p01"}, raw)

    def test_validator_does_not_import_the_projection_producer(self):
        tree = ast.parse(inspect.getsource(independent))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        self.assertFalse(
            any(
                name.endswith("persona_v2_semantic_projection_global_content")
                for name in imported
            ),
            imported,
        )
        for function in (
            independent._topology_owner_raw,
            independent._realism_owner_raw,
            independent._route_owner_raw,
            independent._topology_fragment_raw,
            independent._realism_fragment_raw,
            independent._route_rows_fragment_raw,
            independent._topology_scope_axis_raw,
            independent._expected_topology_raw,
            independent._expected_realism_raw,
            independent._expected_route_raw,
        ):
            self.assertIs(type(function()), bytes, function.__name__)

    def test_provider_replays_exactly_twice_and_fails_closed_on_tamper(self):
        target = list(package.iter_global_content_projection_materials())
        calls = []

        def provider(descriptor):
            calls.append(copy.deepcopy(descriptor))
            return package.projection_body_bytes(
                descriptor["class_id"], descriptor["coordinates"]
            )

        self.assertIs(
            independent.validate_global_content_projection_materials(target, provider),
            True,
        )
        self.assertEqual(
            [row["class_id"] for row in calls],
            [class_id for class_id in package.CLASS_ORDER for _ in range(2)],
        )
        self.assertTrue(all("body" not in row for row in calls))

        nondeterministic_calls = []

        def nondeterministic(descriptor):
            body = package.projection_body_bytes(
                descriptor["class_id"], descriptor["coordinates"]
            )
            nondeterministic_calls.append(descriptor["class_id"])
            if len(nondeterministic_calls) == 2:
                return body[:-1] + bytes([body[-1] ^ 1])
            return body

        with self.assertRaisesRegex(
            independent.PersonaV2SemanticProjectionGlobalContentValidationError,
            "nondeterministic",
        ):
            independent.validate_global_content_projection_materials(
                list(package.iter_global_content_projection_materials()),
                nondeterministic,
            )

        callback_count = 0

        def mutating_target(descriptor):
            nonlocal callback_count
            callback_count += 1
            target[0]["coordinates"]["injected"] = True
            return package.projection_body_bytes(
                descriptor["class_id"], descriptor["coordinates"]
            )

        with self.assertRaises(
            independent.PersonaV2SemanticProjectionGlobalContentValidationError
        ):
            independent.validate_global_content_projection_materials(
                target,
                mutating_target,
            )
        self.assertEqual(callback_count, 1)

    def test_callback_and_final_owner_reauthentication_use_live_builders(self):
        target = list(package.iter_global_content_projection_materials())
        patcher = None

        def provider(descriptor):
            nonlocal patcher
            if patcher is None:
                original = topology.build_topology_contract

                def poisoned():
                    value = original()
                    value["personas"][0]["scopes"][0]["relative_path"] = "poisoned/path"
                    return value

                patcher = mock.patch.object(topology, "build_topology_contract", poisoned)
                patcher.start()
            return package.projection_body_bytes(
                descriptor["class_id"], descriptor["coordinates"]
            )

        try:
            with self.assertRaisesRegex(
                independent.PersonaV2SemanticProjectionGlobalContentValidationError,
                "owner rebuild failed",
            ):
                independent.validate_global_content_projection_materials(target, provider)
        finally:
            if patcher is not None:
                patcher.stop()

        original_fragment = independent._topology_source_fragment
        patcher = None

        def direct_fragment_provider(descriptor):
            nonlocal patcher
            if patcher is None:
                def poisoned_fragment(value):
                    fragment = original_fragment(value)
                    fragment["persona_topology_rows"][0]["role"] = "poisoned"
                    return fragment

                patcher = mock.patch.object(
                    independent,
                    "_topology_source_fragment",
                    poisoned_fragment,
                )
                patcher.start()
            return package.projection_body_bytes(
                descriptor["class_id"], descriptor["coordinates"]
            )

        try:
            with self.assertRaisesRegex(
                independent.PersonaV2SemanticProjectionGlobalContentValidationError,
                "direct fragment",
            ):
                independent.validate_global_content_projection_materials(
                    list(package.iter_global_content_projection_materials()),
                    direct_fragment_provider,
                )
        finally:
            if patcher is not None:
                patcher.stop()

        self.assertIs(independent.reauthenticate_all_projection_owners(), True)

    def test_all_owner_reauthentication_reads_each_live_owner_once(self):
        cached_builders = (
            independent._topology_owner_raw,
            independent._realism_owner_raw,
            independent._route_owner_raw,
            independent._topology_fragment_raw,
            independent._realism_fragment_raw,
            independent._route_rows_fragment_raw,
            independent._topology_scope_axis_raw,
        )
        for builder in cached_builders:
            builder.cache_clear()

        originals = {
            "topology": independent._fresh_topology_owner,
            "realism": independent._fresh_realism_owner,
            "route": independent._fresh_route_owner,
        }
        counts = {name: 0 for name in originals}

        def counted(name):
            def invoke():
                counts[name] += 1
                return originals[name]()

            return invoke

        with (
            mock.patch.object(
                independent,
                "_fresh_topology_owner",
                side_effect=counted("topology"),
            ),
            mock.patch.object(
                independent,
                "_fresh_realism_owner",
                side_effect=counted("realism"),
            ),
            mock.patch.object(
                independent,
                "_fresh_route_owner",
                side_effect=counted("route"),
            ),
        ):
            self.assertIs(independent.reauthenticate_all_projection_owners(), True)
        self.assertEqual(counts, {"topology": 1, "realism": 1, "route": 1})

    def test_material_metadata_tamper_short_circuits_provider(self):
        cases = []
        wrong_pin = copy.deepcopy(self.materials)
        wrong_pin[0]["direct_body_pins"][0]["sha256"] = "0" * 64
        cases.append(wrong_pin)
        wrong_order = copy.deepcopy(self.materials)
        wrong_order[0], wrong_order[1] = wrong_order[1], wrong_order[0]
        cases.append(wrong_order)
        extra_owner = copy.deepcopy(self.materials)
        extra_owner[0]["full_owner_pins"].append(
            copy.deepcopy(extra_owner[0]["full_owner_pins"][0])
        )
        cases.append(extra_owner)

        for candidate in cases:
            calls = []
            with self.subTest(candidate=candidate[0]["class_id"]):
                with self.assertRaises(
                    independent.PersonaV2SemanticProjectionGlobalContentValidationError
                ):
                    independent.validate_global_content_projection_materials(
                        candidate,
                        lambda descriptor: calls.append(descriptor),
                    )
                self.assertEqual(calls, [])

    def test_material_snapshot_rejects_subclasses_before_deepcopy(self):
        deepcopy_calls = []

        class HookedString(str):
            def __deepcopy__(self, _memo):
                deepcopy_calls.append(str(self))
                return str(self)

        candidates = []
        scalar_subclass = copy.deepcopy(self.materials)
        scalar_subclass[0]["artifact_kind"] = HookedString(
            scalar_subclass[0]["artifact_kind"]
        )
        candidates.append(scalar_subclass)

        nested_subclass = copy.deepcopy(self.materials)
        nested_subclass[0]["full_owner_pins"][0]["owner_id"] = HookedString(
            nested_subclass[0]["full_owner_pins"][0]["owner_id"]
        )
        candidates.append(nested_subclass)

        key_subclass = copy.deepcopy(self.materials)
        artifact_kind = key_subclass[0].pop("artifact_kind")
        key_subclass[0][HookedString("artifact_kind")] = artifact_kind
        candidates.append(key_subclass)

        oversized_pin = copy.deepcopy(self.materials)
        oversized_pin[0]["full_owner_pins"][0]["owner_id"] = "x" * 4_097
        candidates.append(oversized_pin)

        for case_index, candidate in enumerate(candidates):
            provider_calls = []
            with self.subTest(case_index=case_index):
                with self.assertRaises(
                    independent.PersonaV2SemanticProjectionGlobalContentValidationError
                ):
                    independent.validate_global_content_projection_materials(
                        candidate,
                        lambda descriptor: provider_calls.append(descriptor),
                    )
                self.assertEqual(provider_calls, [])
        self.assertEqual(deepcopy_calls, [])

    def test_hashes_are_stable_across_hash_seed_and_timezone(self):
        script = (
            "import hashlib,json; "
            "from eval import persona_v2_semantic_projection_global_content as p; "
            "print(json.dumps([(r['class_id'],len(r['body']),"
            "hashlib.sha256(r['body']).hexdigest()) for r in "
            "p.iter_global_content_projection_materials()],separators=(',',':')))"
        )
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
