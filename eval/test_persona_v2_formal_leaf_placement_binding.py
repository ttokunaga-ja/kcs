"""Focused regressions for the non-authorizing formal-leaf placement binding."""

from __future__ import annotations

import ast
import collections
import copy
import hashlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

try:  # Support package and direct discovery modes.
    from . import persona_v2_device_lane_compositor as compositor
    from . import persona_v2_formal_leaf_placement_binding as package
    from . import persona_v2_formal_leaf_placement_binding_validator as independent
    from . import persona_v2_topology as topology
except ImportError:  # pragma: no cover - direct discovery compatibility
    import persona_v2_device_lane_compositor as compositor
    import persona_v2_formal_leaf_placement_binding as package
    import persona_v2_formal_leaf_placement_binding_validator as independent
    import persona_v2_topology as topology


BODY_RECEIPT = (
    889_056,
    "98e7239f498c8ebff3f2c754a24036ac7c5263a2f5f6b2bb66275ceaccd8f66e",
)
DESCRIPTOR_RECEIPT = (
    27_117,
    "d67b54fd1851358902842f464611d07008a06750a3165e58d47bd22954e92dc8",
)


class PersonaV2FormalLeafPlacementBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = package.build_formal_leaf_placement_binding()
        cls.raw = package.canonical_json_bytes(cls.value)
        cls.rows = package.build_formal_leaf_placement_rows()
        cls.body = package.formal_leaf_placement_body_bytes()
        cls.topology = topology.build_topology_contract()
        cls.compositor = compositor.build_device_lane_compositor()

    def fresh(self):
        return copy.deepcopy(self.value)

    def validate_independently(
        self,
        value,
        *,
        topology_provider=None,
        compositor_provider=None,
        body_provider=None,
    ):
        return independent.validate_formal_leaf_placement_binding(
            value,
            producer_expected_golden=(
                package._expected_body_pin(),
                package._expected_descriptor_golden(),
            ),
            topology_provider=(
                (lambda: copy.deepcopy(self.topology))
                if topology_provider is None
                else topology_provider
            ),
            compositor_provider=(
                (lambda: copy.deepcopy(self.compositor))
                if compositor_provider is None
                else compositor_provider
            ),
            body_provider=(
                (lambda artifact_id, body_id: self.body)
                if body_provider is None
                else body_provider
            ),
        )

    def assert_rejected(self, value, **kwargs):
        with self.assertRaises(
            independent.PersonaV2FormalLeafPlacementBindingValidationError
        ):
            self.validate_independently(value, **kwargs)

    def test_identity_inputs_and_four_freeze_receipts_are_exact(self):
        self.assertEqual(
            (package.EXPECTED_BODY_BYTES, package.EXPECTED_BODY_SHA256),
            BODY_RECEIPT,
        )
        self.assertEqual(
            (independent.EXPECTED_BODY_BYTES, independent.EXPECTED_BODY_SHA256),
            BODY_RECEIPT,
        )
        self.assertEqual(
            (package.EXPECTED_CANONICAL_BYTES, package.EXPECTED_SHA256),
            DESCRIPTOR_RECEIPT,
        )
        self.assertEqual(
            (independent.EXPECTED_CANONICAL_BYTES, independent.EXPECTED_SHA256),
            DESCRIPTOR_RECEIPT,
        )
        self.assertEqual((len(self.body), hashlib.sha256(self.body).hexdigest()), BODY_RECEIPT)
        self.assertEqual((len(self.raw), hashlib.sha256(self.raw).hexdigest()), DESCRIPTOR_RECEIPT)
        self.assertEqual(self.value["artifact_schema"], package.ARTIFACT_SCHEMA)
        self.assertEqual(self.value["artifact_schema_version"], 1)
        self.assertEqual(self.value["artifact_id"], package.ARTIFACT_ID)
        self.assertEqual(self.value["body_id"], package.BODY_ID)
        self.assertFalse(self.value["body_embedded"])
        self.assertTrue(self.value["body_final_lf"])
        self.assertTrue(self.value["completion_claims"]["body_descriptor_golden_frozen"])
        self.assertFalse(self.value["g0_contract_frozen"])
        self.assertTrue(all(flag is False for flag in self.value["authority"].values()))
        self.assertEqual(
            [(row["artifact_schema"], row["canonical_bytes"], row["sha256"])
             for row in self.value["dependency_bindings"]],
            [
                (
                    package.TOPOLOGY_PIN[0],
                    package.TOPOLOGY_PIN[2],
                    package.TOPOLOGY_PIN[3],
                ),
                (
                    package.COMPOSITOR_PIN[0],
                    package.COMPOSITOR_PIN[2],
                    package.COMPOSITOR_PIN[3],
                ),
            ],
        )

    def test_exact_replay_persona_scope_order_and_path_registry_properties(self):
        rows = self.rows
        self.assertEqual(len(rows), 1_200)
        self.assertEqual(rows[0]["row_id"], "formal-leaf-placement-formal-replay-01-p01-scope-01")
        self.assertEqual(rows[20]["row_id"], "formal-leaf-placement-formal-replay-01-p02-scope-01")
        self.assertEqual(rows[400]["row_id"], "formal-leaf-placement-formal-replay-02-p01-scope-01")
        self.assertEqual(rows[-1]["row_id"], "formal-leaf-placement-formal-replay-03-p20-scope-20")
        self.assertEqual(
            collections.Counter(row["scope_kind"] for row in rows),
            {"primary": 720, "secondary": 480},
        )
        self.assertEqual(
            collections.Counter(row["leaf_depth_from_home"] for row in rows),
            {2: 69, 3: 564, 4: 339, 5: 132, 6: 96},
        )
        self.assertEqual(len({row["leaf_root"] for row in rows}), 1_200)
        self.assertEqual(len({row["leaf_root"].casefold() for row in rows}), 1_200)
        self.assertEqual(len({row["home_root"] for row in rows}), 60)
        self.assertEqual(len({row["registry_root"] for row in rows}), 60)
        self.assertEqual(
            set(rows[0]),
            package.ROW_FIELDS,
        )
        by_home = collections.defaultdict(list)
        for row in rows:
            self.assertEqual(row["leaf_root"], f"{row['home_root']}/{row['relative_path']}")
            self.assertEqual(row["leaf_depth_from_home"], len(row["relative_path"].split("/")))
            self.assertTrue(row["direct_child_only"])
            self.assertFalse(row["runtime_scope_id_assigned"])
            by_home[row["home_root"]].append(row["leaf_root"])
        for roots in by_home.values():
            self.assertEqual(len(roots), 20)
            for left_index, left in enumerate(roots):
                left_parts = left.split("/")
                for right in roots[left_index + 1:]:
                    right_parts = right.split("/")
                    self.assertNotEqual(left_parts, right_parts)
                    self.assertNotEqual(left_parts, right_parts[:len(left_parts)])
                    self.assertNotEqual(right_parts, left_parts[:len(right_parts)])

    def test_body_and_registry_planning_digests_match_ordered_rows(self):
        self.assertTrue(self.body.endswith(b"\n"))
        self.assertNotIn(b"\r", self.body)
        lines = self.body.splitlines(keepends=True)
        self.assertEqual(len(lines), 1_200)
        self.assertTrue(all(line.endswith(b"\n") for line in lines))
        self.assertEqual(max(map(len, lines)), self.value["maximum_lf_inclusive_row_bytes"])
        self.assertEqual(
            self.value["planning_digests"]["scope_registry_sha256"],
            hashlib.sha256(self.body).hexdigest(),
        )
        projection = b"".join(
            json.dumps(
                {"leaf_root": row["leaf_root"]},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8") + b"\n"
            for row in self.rows
        )
        self.assertEqual(
            self.value["planning_digests"]["leaf_path_projection_sha256"],
            hashlib.sha256(projection).hexdigest(),
        )
        summaries = self.value["registry_summaries"]
        self.assertEqual(len(summaries), 60)
        self.assertEqual(sum(row["entry_count"] for row in summaries), 1_200)
        self.assertEqual(
            [(row["replay_id"], row["persona_id"]) for row in summaries[:2]],
            [("formal-replay-01", "p01"), ("formal-replay-01", "p02")],
        )
        self.assertEqual(
            (summaries[-1]["replay_id"], summaries[-1]["persona_id"]),
            ("formal-replay-03", "p20"),
        )
        for summary, start in zip(summaries, range(0, 1_200, 20)):
            group = self.rows[start:start + 20]
            registry_body = b"".join(lines[start:start + 20])
            registry_projection = b"".join(
                json.dumps(
                    {"leaf_root": row["leaf_root"]},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8") + b"\n"
                for row in group
            )
            self.assertEqual(summary["entry_count"], 20)
            self.assertEqual(summary["home_root"], group[0]["home_root"])
            self.assertEqual(summary["registry_root"], group[0]["registry_root"])
            self.assertEqual(summary["registry_sha256"], hashlib.sha256(registry_body).hexdigest())
            self.assertEqual(summary["leaf_path_sha256"], hashlib.sha256(registry_projection).hexdigest())

    def test_independent_validator_never_imports_producer_and_accepts_bytes(self):
        source = inspect.getsource(independent)
        self.assertNotIn("persona_v2_formal_leaf_placement_binding as", source)
        tree = ast.parse(source)
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.extend(alias.name for alias in node.names)
        self.assertNotIn("persona_v2_formal_leaf_placement_binding", imports)
        self.assertFalse(
            any(
                name.endswith("persona_v2_formal_leaf_placement_binding")
                for name in imports
            )
        )
        self.assertTrue(self.validate_independently(self.value))
        loaded = independent.load_and_validate_formal_leaf_placement_binding(
            self.raw,
            producer_expected_golden=(
                package._expected_body_pin(),
                package._expected_descriptor_golden(),
            ),
            body_provider=lambda artifact_id, body_id: self.body,
        )
        self.assertEqual(loaded, self.value)
        self.assertEqual(
            package.formal_leaf_placement_binding_sha256(self.value),
            DESCRIPTOR_RECEIPT[1],
        )

    def test_outputs_are_detached_and_three_providers_are_read_exactly_twice(self):
        first = package.build_formal_leaf_placement_binding()
        first["registry_summaries"][0]["home_root"] = "poisoned"
        first_rows = package.build_formal_leaf_placement_rows()
        first_rows[0]["leaf_root"] = "poisoned"
        self.assertEqual(
            package.build_formal_leaf_placement_binding()["registry_summaries"][0]["home_root"],
            self.value["registry_summaries"][0]["home_root"],
        )
        self.assertEqual(package.build_formal_leaf_placement_rows()[0]["leaf_root"], self.rows[0]["leaf_root"])

        topology_provider = mock.Mock(
            side_effect=[copy.deepcopy(self.topology), copy.deepcopy(self.topology)]
        )
        compositor_provider = mock.Mock(
            side_effect=[copy.deepcopy(self.compositor), copy.deepcopy(self.compositor)]
        )
        body_provider = mock.Mock(side_effect=[self.body, self.body])
        self.assertTrue(
            self.validate_independently(
                self.value,
                topology_provider=topology_provider,
                compositor_provider=compositor_provider,
                body_provider=body_provider,
            )
        )
        self.assertEqual(topology_provider.call_count, 2)
        self.assertEqual(compositor_provider.call_count, 2)
        self.assertEqual(body_provider.call_count, 2)
        self.assertEqual(
            body_provider.call_args_list[0].args,
            (package.ARTIFACT_ID, package.BODY_ID),
        )

    def test_descriptor_body_and_input_tampering_are_rejected(self):
        mutations = []
        authority = self.fresh()
        authority["authority"]["authorizes_physical_write"] = True
        mutations.append(authority)
        planning_digest = self.fresh()
        planning_digest["planning_digests"]["scope_registry_sha256"] = "0" * 64
        mutations.append(planning_digest)
        registry = self.fresh()
        registry["registry_summaries"][0]["registry_root"] = "formal-replay-01/devices/p02-forged/.kio-eval-device"
        mutations.append(registry)
        extra = self.fresh()
        extra["writer_receipt"] = {}
        mutations.append(extra)
        for mutation in mutations:
            with self.subTest(mutation=next(iter(set(mutation) - set(self.value)), "existing")):
                self.assert_rejected(mutation)

        reordered = b"".join(self.body.splitlines(keepends=True)[::-1])
        self.assert_rejected(
            self.value,
            body_provider=lambda artifact_id, body_id: reordered,
        )
        self.assert_rejected(
            self.value,
            body_provider=lambda artifact_id, body_id: self.body[:-1],
        )
        malformed_lines = self.body.splitlines(keepends=True)
        malformed_lines[0] = b'{"row_id":"first","row_id":"second"}\n'
        self.assert_rejected(
            self.value,
            body_provider=lambda artifact_id, body_id: b"".join(malformed_lines),
        )
        self.assert_rejected(
            self.value,
            body_provider=lambda artifact_id, body_id: b"\xef\xbb\xbf" + self.body,
        )
        tampered_topology = copy.deepcopy(self.topology)
        tampered_topology["personas"][0]["scopes"][0]["relative_path"] = "forged/path"
        self.assert_rejected(
            self.value,
            topology_provider=lambda: tampered_topology,
        )
        tampered_compositor = copy.deepcopy(self.compositor)
        tampered_compositor["personas"][0]["formal_replay_mappings"][0]["home_root"] = "forged/home"
        self.assert_rejected(
            self.value,
            compositor_provider=lambda: tampered_compositor,
        )

    def test_strict_json_toctou_and_alias_bombs_fail_closed(self):
        duplicate = b'{"artifact_id":"first","artifact_id":"second"}'
        with self.assertRaisesRegex(
            independent.PersonaV2FormalLeafPlacementBindingValidationError,
            "duplicate JSON key",
        ):
            independent.strict_load_canonical_json_bytes(duplicate)
        with self.assertRaisesRegex(
            independent.PersonaV2FormalLeafPlacementBindingValidationError,
            "not exact canonical JSON",
        ):
            independent.strict_load_canonical_json_bytes(self.raw.replace(b'":', b'": ', 1))
        with self.assertRaises(
            independent.PersonaV2FormalLeafPlacementBindingValidationError
        ):
            independent.strict_load_canonical_json_bytes(b"\xef\xbb\xbf" + self.raw)

        first = copy.deepcopy(self.topology)
        second = copy.deepcopy(self.topology)
        second["personas"][0]["role"] = "forged-role"
        drifting_topology = mock.Mock(side_effect=[first, second])
        self.assert_rejected(self.value, topology_provider=drifting_topology)

        drifting_body = mock.Mock(side_effect=[self.body, self.body[:-1]])
        self.assert_rejected(self.value, body_provider=drifting_body)
        self.assertEqual(drifting_body.call_count, 2)

        malformed_receipt = self.fresh()
        malformed_receipt["first_row_lf_bytes"] = True
        never_opened = mock.Mock(side_effect=AssertionError("provider must not open"))
        self.assert_rejected(malformed_receipt, body_provider=never_opened)
        self.assertEqual(never_opened.call_count, 0)

        shared = []
        alias_bomb = {f"branch-{ordinal}": shared for ordinal in range(60)}
        with self.assertRaises(
            independent.PersonaV2FormalLeafPlacementBindingValidationError
        ):
            independent.validate_formal_leaf_placement_binding(alias_bomb)

    def test_authorized_entrypoints_stay_fail_closed(self):
        with self.assertRaises(package.PersonaV2FormalLeafPlacementBindingError):
            package.require_authorized_formal_leaf_placement_binding()
        with self.assertRaises(package.PersonaV2FormalLeafPlacementBindingError):
            package.require_issued_formal_leaf_placement_binding()
        with self.assertRaises(independent.PersonaV2FormalLeafPlacementBindingValidationError):
            independent.require_authorized_formal_leaf_placement_binding(self.value)

    def test_cold_hash_seed_replays_hold_all_four_pins(self):
        program = (
            "import json; from eval import persona_v2_formal_leaf_placement_binding as p; "
            "v=p.build_formal_leaf_placement_binding(); b=p.formal_leaf_placement_body_bytes(); "
            "print(json.dumps([len(b),p._sha256(b),len(p.canonical_json_bytes(v)),p.formal_leaf_placement_binding_sha256(v)]))"
        )
        observed = []
        root = Path(__file__).resolve().parents[1]
        for seed in ("101", "907"):
            environment = dict(os.environ, PYTHONHASHSEED=seed)
            result = subprocess.run(
                [sys.executable, "-c", program],
                cwd=root,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            observed.append(tuple(json.loads(result.stdout)))
        self.assertEqual(
            observed,
            [
                (BODY_RECEIPT[0], BODY_RECEIPT[1], DESCRIPTOR_RECEIPT[0], DESCRIPTOR_RECEIPT[1]),
                (BODY_RECEIPT[0], BODY_RECEIPT[1], DESCRIPTOR_RECEIPT[0], DESCRIPTOR_RECEIPT[1]),
            ],
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
