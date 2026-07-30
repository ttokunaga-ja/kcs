"""Focused gates for the non-authorizing core-versus-legacy count audit."""

from __future__ import annotations

import ast
import collections
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

try:  # Support package and direct discovery modes.
    from . import persona_v2_core_extension_allocation_manifest as core
    from . import (
        persona_v2_core_extension_legacy_source_allocation_compatibility_audit
        as audit,
    )
    from . import (
        persona_v2_core_extension_legacy_source_allocation_compatibility_audit_validator
        as independent,
    )
    from . import persona_v2_variant_catalog as legacy_catalog
except ImportError:  # pragma: no cover - direct discovery compatibility
    import persona_v2_core_extension_allocation_manifest as core
    import persona_v2_core_extension_legacy_source_allocation_compatibility_audit as audit
    import persona_v2_core_extension_legacy_source_allocation_compatibility_audit_validator as independent
    import persona_v2_variant_catalog as legacy_catalog


def _imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.append(node.module)
            names.extend(alias.name for alias in node.names)
    return names


def _keys(value):
    result = []
    stack = [value]
    while stack:
        current = stack.pop()
        if type(current) is dict:
            result.extend(current)
            stack.extend(current.values())
        elif type(current) is list:
            stack.extend(current)
    return result


class CoreExtensionLegacyAllocationCompatibilityAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.descriptor = audit.build_core_extension_legacy_source_allocation_compatibility_audit()
        cls.raw = audit.canonical_json_bytes(cls.descriptor)
        cls.body = audit.core_extension_legacy_source_allocation_delta_body_bytes()

    def _validator_arguments(self, **overrides):
        arguments = {
            "producer_expected_golden": audit._expected_golden(),
            "core_descriptor_provider": core.build_core_extension_allocation_manifest,
            "core_body_provider": lambda artifact_id, body_id: (
                core.core_extension_allocation_body_bytes()
                if artifact_id == audit.CORE_ARTIFACT_ID and body_id == audit.CORE_BODY_ID
                else self.fail("unexpected core body coordinates")
            ),
            "legacy_variant_catalog_provider": legacy_catalog.build_variant_catalog,
            "delta_body_provider": lambda artifact_id, body_id: (
                audit.core_extension_legacy_source_allocation_delta_body_bytes()
                if artifact_id == audit.ARTIFACT_ID and body_id == audit.BODY_ID
                else self.fail("unexpected delta body coordinates")
            ),
        }
        arguments.update(overrides)
        return arguments

    def test_identity_exact_goldens_and_independent_replay(self):
        exact = (
            3_500,
            "f2eb954e5d097cd41ed5cd7f92904b9987f6b08eb5532a9587ea6bd6043a27b1",
            236_068,
            "ff2f50a342e92e8b43c4d743811ee7bddd6772c20c6e2cf0530ee160ca0385dd",
        )
        self.assertEqual(audit._expected_golden(), exact)
        self.assertEqual(independent._expected_golden(), exact)
        self.assertEqual((len(self.raw), hashlib.sha256(self.raw).hexdigest()), exact[:2])
        self.assertEqual((len(self.body), hashlib.sha256(self.body).hexdigest()), exact[2:])
        self.assertTrue(audit.validate_core_extension_legacy_source_allocation_compatibility_audit(self.descriptor))
        self.assertTrue(
            independent.validate_core_extension_legacy_source_allocation_compatibility_audit(
                self.descriptor, **self._validator_arguments()
            )
        )

    def test_mismatch_is_valid_result_not_adoption_authority(self):
        result = self.descriptor["result"]
        self.assertEqual(result, {
            "additive_reuse_authorized": False,
            "cellwise_compatible": False,
            "compatibility_status": "incompatible",
            "legacy_source_allocation_compatibility": "unresolved",
            "legacy_source_projection_reuse_authorized": False,
        })
        self.assertEqual(self.descriptor["summary"], {
            "coordinate_count": 566,
            "core_full_total": 203_000,
            "core_pilot_total": 20_300,
            "full_equal_coordinate_count": 77,
            "full_l1_delta": 70_500,
            "full_mismatch_coordinate_count": 489,
            "full_only_mismatch_coordinate_count": 6,
            "legacy_full_total": 203_000,
            "legacy_pilot_total": 20_300,
            "pilot_equal_coordinate_count": 83,
            "pilot_l1_delta": 7_050,
            "pilot_mismatch_coordinate_count": 483,
            "pilot_only_mismatch_coordinate_count": 0,
            "union_mismatch_coordinate_count": 489,
        })
        self.assertEqual(set(self.descriptor["authority"]), audit.AUTHORITY_FIELDS)
        self.assertTrue(all(flag is False for flag in self.descriptor["authority"].values()))
        self.assertTrue(all(flag is False for flag in self.descriptor["completion_claims"].values()))
        with self.assertRaises(audit.PersonaV2CoreExtensionLegacyAllocationCompatibilityAuditError):
            audit.require_issued_core_extension_legacy_source_allocation_compatibility_audit()

    def test_delta_body_exact_rows_and_count_only_scope(self):
        lines = self.body.splitlines(keepends=True)
        self.assertEqual(len(lines), 489)
        self.assertTrue(all(line.endswith(b"\n") for line in lines))
        self.assertLessEqual(max(map(len, lines)), audit.MAX_DELTA_ROW_BYTES_INCLUDING_LF)
        rows = [json.loads(line) for line in lines]
        self.assertEqual(rows[0]["row_id"], "core-vs-legacy-allocation-p01-md-markdown")
        self.assertEqual(rows[-1]["row_id"], "core-vs-legacy-allocation-p20-domain_binary-source-drop-ustar")
        self.assertEqual(
            {field for row in rows for field in row},
            independent.DELTA_ROW_FIELDS,
        )
        self.assertFalse(any("tiny" in field for row in rows for field in row))
        self.assertFalse(any("source" in field or "path" in field or "chunk" in field for row in rows for field in row))
        by_coordinate = {
            (row["persona_id"], row["family_id"], row["variant_id"]): row
            for row in rows
        }
        p01_docx = by_coordinate[("p01", "docx", "docx")]
        self.assertEqual((p01_docx["core_full_count"], p01_docx["legacy_full_count"]), (24, 360))
        self.assertEqual((p01_docx["core_pilot_count"], p01_docx["legacy_pilot_count"]), (2, 36))
        self.assertEqual(p01_docx["full_delta_direction"], "legacy-greater")
        self.assertEqual(p01_docx["pilot_delta_direction"], "legacy-greater")
        self.assertFalse(p01_docx["full_equal"])
        self.assertFalse(p01_docx["pilot_equal"])

    def test_coordinate_shape_and_catalog_binding_are_exact(self):
        binding = self.descriptor["legacy_variant_catalog_binding"]
        self.assertEqual(binding, {
            "artifact_kind": "persona-pc-v2-variant-catalog",
            "artifact_schema": "kio.persona.pc-variant-catalog/v2",
            "artifact_schema_version": 2,
            "canonical_bytes": 211_733,
            "sha256": "807dd3cdd8df613ac21e6ba64877fb5abb40c72ed4949abaa0d440a449e7f9e9",
        })
        core_binding = self.descriptor["core_allocation_binding"]
        self.assertEqual(core_binding["canonical_bytes"], 5_357)
        self.assertEqual(core_binding["body_canonical_bytes"], 426_889)
        self.assertEqual(core_binding["body_id"], audit.CORE_BODY_ID)
        contract = self.descriptor["comparison_contract"]
        self.assertEqual(contract["coordinate_key"], ["persona_id", "family_id", "variant_id"])
        self.assertEqual(contract["allocation_count_fields"], ["full_count", "pilot_count"])
        self.assertEqual(contract["tiny_count_comparison"], "not-applicable-legacy-has-tiny-smoke-not-core-tiny")
        self.assertEqual(contract["tolerance"], "exact-integer-equality")

    def test_provider_reads_are_bounded_twice_and_unstable_inputs_fail(self):
        calls = collections.Counter()

        def descriptor_provider():
            calls["descriptor"] += 1
            return core.build_core_extension_allocation_manifest()

        def core_body_provider(artifact_id, body_id):
            self.assertEqual((artifact_id, body_id), (audit.CORE_ARTIFACT_ID, audit.CORE_BODY_ID))
            calls["core_body"] += 1
            return core.core_extension_allocation_body_bytes()

        def catalog_provider():
            calls["catalog"] += 1
            return legacy_catalog.build_variant_catalog()

        def delta_provider(artifact_id, body_id):
            self.assertEqual((artifact_id, body_id), (audit.ARTIFACT_ID, audit.BODY_ID))
            calls["delta"] += 1
            return audit.core_extension_legacy_source_allocation_delta_body_bytes()

        self.assertTrue(
            independent.validate_core_extension_legacy_source_allocation_compatibility_audit(
                self.descriptor,
                **self._validator_arguments(
                    core_descriptor_provider=descriptor_provider,
                    core_body_provider=core_body_provider,
                    legacy_variant_catalog_provider=catalog_provider,
                    delta_body_provider=delta_provider,
                ),
            )
        )
        self.assertEqual(calls, {"descriptor": 2, "core_body": 2, "catalog": 2, "delta": 2})

        descriptor_reads = [
            core.build_core_extension_allocation_manifest(),
            {"not": "the core descriptor"},
        ]

        def unstable_descriptor_provider():
            return descriptor_reads.pop(0)

        with self.assertRaises(independent.PersonaV2CoreExtensionLegacyAllocationCompatibilityAuditValidationError):
            independent.validate_core_extension_legacy_source_allocation_compatibility_audit(
                self.descriptor,
                **self._validator_arguments(core_descriptor_provider=unstable_descriptor_provider),
            )

    def test_tampering_descriptor_catalog_or_delta_body_fails_closed(self):
        changed = copy.deepcopy(self.descriptor)
        changed["summary"]["full_mismatch_coordinate_count"] -= 1
        with self.assertRaises(independent.PersonaV2CoreExtensionLegacyAllocationCompatibilityAuditValidationError):
            independent.validate_core_extension_legacy_source_allocation_compatibility_audit(
                changed, **self._validator_arguments()
            )

        def tampered_catalog_provider():
            value = legacy_catalog.build_variant_catalog()
            value["persona_variant_marginals"][0]["full_count"] += 1
            value["persona_variant_marginals"][1]["full_count"] -= 1
            return value

        with self.assertRaises(independent.PersonaV2CoreExtensionLegacyAllocationCompatibilityAuditValidationError):
            independent.validate_core_extension_legacy_source_allocation_compatibility_audit(
                self.descriptor,
                **self._validator_arguments(legacy_variant_catalog_provider=tampered_catalog_provider),
            )

        def swapped_core_body_provider(_artifact_id, _body_id):
            return core.core_extension_allocation_body_bytes()[:-1]

        with self.assertRaises(independent.PersonaV2CoreExtensionLegacyAllocationCompatibilityAuditValidationError):
            independent.validate_core_extension_legacy_source_allocation_compatibility_audit(
                self.descriptor,
                **self._validator_arguments(core_body_provider=swapped_core_body_provider),
            )

        def truncated_delta_provider(_artifact_id, _body_id):
            return self.body.splitlines(keepends=True)[0]

        with self.assertRaises(independent.PersonaV2CoreExtensionLegacyAllocationCompatibilityAuditValidationError):
            independent.validate_core_extension_legacy_source_allocation_compatibility_audit(
                self.descriptor,
                **self._validator_arguments(delta_body_provider=truncated_delta_provider),
            )

    def test_import_boundary_and_no_execution_coordinate_leak_in_delta_rows(self):
        producer_path = Path(audit.__file__)
        validator_path = Path(independent.__file__)
        self.assertFalse(
            [
                name
                for name in _imports(validator_path)
                if "core_extension_legacy_source_allocation_compatibility_audit" in name
                and "validator" not in name
            ]
        )
        for path in (producer_path, validator_path):
            self.assertFalse(
                [
                    name
                    for name in _imports(path)
                    if "format_implementation_registry" in name or "renderer" in name
                ]
            )
        delta_rows = [json.loads(line) for line in self.body.splitlines()]
        forbidden = ("query", "oracle", "history", "scope", "path", "chunk", "source_id")
        self.assertFalse(
            [
                key
                for row in delta_rows
                for key in _keys(row)
                if any(token in key.lower() for token in forbidden)
            ]
        )

    @unittest.skipUnless(
        os.environ.get("KIO_RUN_CORE_LEGACY_ALLOCATION_AUDIT_COLD") == "1",
        "set KIO_RUN_CORE_LEGACY_ALLOCATION_AUDIT_COLD=1 for cold hash-seed replay",
    )
    def test_opt_in_two_seed_cold_replay(self):
        code = (
            "from eval import persona_v2_core_extension_legacy_source_allocation_compatibility_audit as a; "
            "import hashlib; d=a.build_core_extension_legacy_source_allocation_compatibility_audit(); "
            "print(len(a.canonical_json_bytes(d)),hashlib.sha256(a.canonical_json_bytes(d)).hexdigest(),"
            "len(a.core_extension_legacy_source_allocation_delta_body_bytes()),"
            "hashlib.sha256(a.core_extension_legacy_source_allocation_delta_body_bytes()).hexdigest())"
        )
        expected = "3500 f2eb954e5d097cd41ed5cd7f92904b9987f6b08eb5532a9587ea6bd6043a27b1 236068 ff2f50a342e92e8b43c4d743811ee7bddd6772c20c6e2cf0530ee160ca0385dd"
        for seed in ("0", "1"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            completed = subprocess.run(
                [sys.executable, "-c", code],
                cwd=Path(__file__).resolve().parents[1],
                check=False,
                capture_output=True,
                env=env,
                text=True,
                timeout=120,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout.strip(), expected)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
