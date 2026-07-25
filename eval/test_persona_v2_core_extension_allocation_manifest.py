"""Focused fast gates for the persona-core extension allocation candidate."""

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
import time
import unittest
from unittest import mock

try:  # Support package and direct discovery modes.
    from . import persona_v2_core_extension_allocation_manifest as package
    from . import persona_v2_core_extension_allocation_manifest_validator as independent
except ImportError:  # pragma: no cover - direct discovery compatibility
    import persona_v2_core_extension_allocation_manifest as package
    import persona_v2_core_extension_allocation_manifest_validator as independent


EXPECTED_RARE_FULL_SPLITS = {
    "p01": {"ipynb": 24, "pdf-scan": 12, "docx": 24, "xlsx": 20, "pptx": 20, "source-export-zip": 14, "source-ustar": 6},
    "p02": {"pdf-scan": 10, "docx": 30, "xlsx": 20, "pptx": 20, "pcap": 21, "jsonl-gzip": 49},
    "p03": {"py": 21, "go": 6, "ts": 3, "pptx": 20, "pcap": 20, "evidence-zip": 30},
    "p04": {"pdf-scan": 10, "docx": 20, "xlsx": 20, "pptx": 20, "npz": 21, "model-metadata-zip": 9},
    "p05": {"html": 20, "eml": 10, "ipynb": 25, "pdf-scan": 10, "docx": 25, "warehouse-zip": 18, "csv-gzip": 12},
    "p06": {"py": 17, "cpp": 2, "ts": 1, "html": 14, "eml": 6, "ipynb": 20, "pptx": 20},
    "p07": {"xlsx": 20, "pptx": 15, "wav": 12, "aiff": 8, "tiff-ustar": 9, "archive-zip": 6},
    "p08": {"txt": 12, "log": 3, "jsonl": 5, "py": 6, "js": 1, "ts": 3, "pdf-scan": 15, "wav": 7, "aiff": 3, "product-export-zip": 18, "team-export-ustar": 7},
    "p09": {"html": 11, "eml": 19, "xlsx": 30, "recording-project-zip": 21, "session-ustar": 9},
    "p10": {"txt": 21, "log": 3, "jsonl": 6, "png": 15, "jpg": 11, "tif": 3, "bmp": 1, "data-room-zip": 40, "snapshot-ustar": 10},
    "p11": {"json": 11, "yaml": 2, "xml": 3, "sql": 4, "pdf-scan": 25, "wav": 14, "aiff": 6, "crm-zip": 21, "maildir-ustar": 14},
    "p12": {"pdf-scan": 20, "xlsx": 30, "pptx": 20, "wav": 24, "aiff": 6, "ticket-zip": 42, "crm-jsonl-gzip": 18},
    "p13": {"csv": 9, "tsv": 6, "pptx": 20, "dms-zip": 25, "legal-hold-ustar": 10},
    "p14": {"txt": 16, "log": 4, "jsonl": 5, "py": 11, "js": 1, "ts": 3, "png": 14, "jpg": 6, "tif": 4, "bmp": 1, "erp-csv-gzip": 39, "close-package-zip": 26},
    "p15": {"json": 7, "yaml": 2, "xml": 4, "sql": 2, "pptx": 20, "wav": 7, "aiff": 3, "ats-zip": 21, "hris-jsonl-gzip": 14},
    "p16": {"py": 12, "cpp": 2, "ts": 1, "html": 7, "eml": 13, "pptx": 20, "wav": 20, "aiff": 5},
    "p17": {"txt": 27, "log": 9, "jsonl": 9, "json": 5, "yaml": 3, "xml": 9, "sql": 3, "wav": 12, "aiff": 3},
    "p18": {"py": 21, "cpp": 6, "rs": 3, "html": 14, "eml": 16, "pptx": 60},
    "p19": {"txt": 18, "log": 2, "jsonl": 5, "json": 6, "yaml": 2, "xml": 5, "sql": 2, "course-package-zip": 35, "lms-ustar": 15},
    "p20": {"py": 16, "js": 2, "ts": 2, "xlsx": 15, "pptx": 15, "foia-zip": 35, "source-drop-ustar": 15},
}


class PersonaV2CoreExtensionAllocationManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = package.build_core_extension_allocation_manifest()
        cls.raw = package.canonical_json_bytes(cls.value)
        cls.rows = package.build_core_extension_allocation_rows()
        cls.body = package.core_extension_allocation_body_bytes()
        cls.matrix = package.build_core_family_count_matrix()

    def _independent_validate(self, value, provider=None):
        return independent.validate_core_extension_allocation_manifest(
            value,
            producer_expected_golden=package._expected_golden(),
            core_matrix_value=self.matrix,
            body_provider=(
                (lambda artifact_id, body_id: self.body)
                if provider is None
                else provider
            ),
        )

    def test_candidate_identity_external_body_receipt_and_golden_parity(self):
        self.assertEqual(self.value["artifact_schema"], package.ARTIFACT_SCHEMA)
        self.assertEqual(self.value["artifact_schema_version"], 1)
        self.assertEqual(self.value["artifact_id"], package.ARTIFACT_ID)
        self.assertEqual(self.value["body_id"], package.BODY_ID)
        self.assertFalse(self.value["body_embedded"])
        self.assertTrue(self.value["body_final_lf"])
        self.assertEqual(package._expected_golden(), independent._expected_golden())
        self.assertEqual(
            package._expected_golden(),
            (5_357, "ca7caa3813d8f359785cb4dc65e7155f6e36153ba651e1a4b3af0d3695780e9f"),
        )
        self.assertEqual(len(self.body), 426_889)
        self.assertEqual(
            hashlib.sha256(self.body).hexdigest(),
            "f31f696e1692758e4fc52133dba733af77b74d16711034ee05d75b16d64f7d45",
        )
        self.assertEqual(self.value["body_canonical_bytes"], len(self.body))
        self.assertEqual(self.value["body_sha256"], hashlib.sha256(self.body).hexdigest())
        self.assertLess(len(self.raw), package.MAX_MANIFEST_BYTES)

    def test_exact_matrix_body_rows_and_receipts(self):
        self.assertEqual(package.core_family_count_matrix_sha256(self.matrix), package.CORE_MATRIX_PIN[2])
        self.assertEqual(len(self.rows), 566)
        self.assertEqual(sum(row["full_count"] > 0 for row in self.rows), 539)
        lines = self.body.splitlines(keepends=True)
        self.assertEqual(len(lines), 566)
        self.assertTrue(all(line.endswith(b"\n") for line in lines))
        self.assertEqual(max(map(len, lines)), 786)
        first, last = self.rows[0], self.rows[-1]
        self.assertEqual(first["row_id"], "persona-core-v1-extension-p01-md-md")
        self.assertEqual(last["row_id"], "persona-core-v1-extension-p20-domain_binary-source-drop-ustar")
        self.assertEqual(len(lines[0]), 745)
        self.assertEqual(hashlib.sha256(lines[0]).hexdigest(), "351991d32d2b21171ec21a77fd3ba2a52ef89638e845cf2ce590addeba885fb5")
        self.assertEqual(len(lines[-1]), 778)
        self.assertEqual(hashlib.sha256(lines[-1]).hexdigest(), "e663127e173334127c6333909370038fa83181d903a1866a9d1380711fd0b09b")
        self.assertEqual(self.value["first_row_id"], first["row_id"])
        self.assertEqual(self.value["last_row_id"], last["row_id"])

    def test_nested_hamilton_totals_roles_and_family_local_ordinals(self):
        by_persona_family = collections.defaultdict(list)
        variants = set()
        extensions = set()
        roles = collections.Counter()
        for row in self.rows:
            self.assertEqual(set(row), package.ROW_FIELDS)
            self.assertIs(type(row["schema_version"]), int)
            self.assertIsNot(type(row["schema_version"]), bool)
            self.assertEqual(row["schema_version"], 1)
            self.assertEqual(row["row_schema"], package.ROW_SCHEMA)
            self.assertEqual(row["profile_id"], package.PROFILE_ID)
            self.assertEqual(row["format_registry_sha256"], package.FORMAT_REGISTRY_PIN[3])
            by_persona_family[(row["persona_id"], row["family_id"])].append(row)
            variants.add(row["variant_id"])
            extensions.add(row["filename_extension"])
            roles[row["gate_role"]] += row["full_count"]
        self.assertEqual(len(variants), 71)
        self.assertTrue(
            all(
                sum(
                    row["full_count"]
                    for row in self.rows
                    if row["variant_id"] == variant_id
                )
                > 0
                for variant_id in variants
            )
        )
        self.assertEqual(len(extensions), 39)
        self.assertEqual(dict(roles), {
            "contract_contributor": 68_761,
            "incidental_searchable": 62_978,
            "raw_only": 71_261,
        })
        matrix_by_persona = {
            row["persona_id"]: (row["total_files"], row["counts"])
            for row in self.matrix["rows"]
        }
        for (persona_id, family_id), rows in by_persona_family.items():
            ordinal = package.FAMILY_ORDER.index(family_id)
            full_total, full_families = matrix_by_persona[persona_id]
            self.assertEqual([row["variant_ordinal"] for row in rows], list(range(len(rows))))
            self.assertTrue(all(row["family_ordinal"] == ordinal for row in rows))
            self.assertEqual(sum(row["full_count"] for row in rows), full_families[ordinal])
            self.assertEqual(sum(row["pilot_count"] for row in rows), rows[0]["family_pilot_count"])
            self.assertEqual(sum(row["tiny_count"] for row in rows), rows[0]["family_tiny_count"])
            self.assertTrue(all(row["pilot_count"] <= row["full_count"] for row in rows))
            self.assertEqual(rows[0]["family_full_count"], full_families[ordinal])
            self.assertEqual(full_total // 10, sum(row["pilot_count"] for row in self.rows if row["persona_id"] == persona_id))
            self.assertEqual(200, sum(row["tiny_count"] for row in self.rows if row["persona_id"] == persona_id))
        for persona_id, (full_total, full_families) in matrix_by_persona.items():
            rare_families = {
                package.FAMILY_ORDER[ordinal]
                for ordinal, count in enumerate(full_families)
                if 0 < count < full_total // 100
            }
            self.assertEqual(
                sum(
                    row["full_count"]
                    for row in self.rows
                    if row["persona_id"] == persona_id and row["family_id"] in rare_families
                ),
                full_total // 100,
            )
            self.assertEqual(
                sum(
                    row["pilot_count"]
                    for row in self.rows
                    if row["persona_id"] == persona_id and row["family_id"] in rare_families
                ),
                (full_total // 10) // 100,
            )
            self.assertEqual(
                sum(
                    row["tiny_count"]
                    for row in self.rows
                    if row["persona_id"] == persona_id and row["family_id"] in rare_families
                ),
                2,
            )
            actual_rare_split = {
                row["variant_id"]: row["full_count"]
                for row in self.rows
                if row["persona_id"] == persona_id
                and row["family_id"] in rare_families
                and row["full_count"] > 0
            }
            self.assertEqual(actual_rare_split, EXPECTED_RARE_FULL_SPLITS[persona_id])
        self.assertEqual(sum(row["full_count"] for row in self.rows), 203_000)
        self.assertEqual(sum(row["pilot_count"] for row in self.rows), 20_300)
        self.assertEqual(sum(row["tiny_count"] for row in self.rows), 4_000)

    def test_both_validators_and_two_read_provider(self):
        self.assertTrue(package.validate_core_extension_allocation_manifest(self.value))
        provider = mock.Mock(side_effect=lambda artifact_id, body_id: self.body)
        self.assertTrue(self._independent_validate(self.value, provider=provider))
        self.assertEqual(provider.call_count, 2)
        self.assertEqual(provider.call_args_list[0].args, (package.ARTIFACT_ID, package.BODY_ID))

    def test_all_three_input_providers_are_read_twice_before_body(self):
        matrix = mock.Mock(side_effect=[self.matrix, copy.deepcopy(self.matrix)])
        envelope_value = __import__("eval.persona_v2_contract", fromlist=["build_envelope_contract"]).build_envelope_contract()
        envelope_provider = mock.Mock(side_effect=[envelope_value, copy.deepcopy(envelope_value)])
        projection = independent._frozen_format_registry_projection()
        projection_provider = mock.Mock(side_effect=[projection, copy.deepcopy(projection)])
        body = mock.Mock(side_effect=lambda artifact_id, body_id: self.body)
        self.assertTrue(
            independent.validate_core_extension_allocation_manifest(
                self.value,
                producer_expected_golden=package._expected_golden(),
                core_matrix_provider=matrix,
                envelope_provider=envelope_provider,
                format_registry_projection_provider=projection_provider,
                body_provider=body,
            )
        )
        self.assertEqual(matrix.call_count, 2)
        self.assertEqual(envelope_provider.call_count, 2)
        self.assertEqual(projection_provider.call_count, 2)
        self.assertEqual(body.call_count, 2)

    def test_independent_default_input_providers_are_opened_exactly_twice(self):
        """Authentication must not reopen defaults after their two owned reads."""

        original_matrix = independent._core_matrix
        original_envelope = independent.envelope.build_envelope_contract
        original_projection = independent._frozen_format_registry_projection
        matrix = mock.Mock(side_effect=original_matrix)
        envelope_provider = mock.Mock(side_effect=original_envelope)
        projection = mock.Mock(side_effect=original_projection)
        body = mock.Mock(side_effect=lambda artifact_id, body_id: self.body)
        with mock.patch.object(independent, "_core_matrix", matrix), mock.patch.object(
            independent.envelope, "build_envelope_contract", envelope_provider
        ), mock.patch.object(independent, "_frozen_format_registry_projection", projection):
            accepted = independent.accepted_core_extension_allocation_body_bytes(
                self.value,
                producer_expected_golden=package._expected_golden(),
                body_provider=body,
            )
        self.assertEqual(accepted, self.body)
        self.assertEqual(matrix.call_count, 2)
        self.assertEqual(envelope_provider.call_count, 2)
        self.assertEqual(projection.call_count, 2)
        self.assertEqual(body.call_count, 2)

    def test_explicit_input_providers_never_fallback_to_default_builders(self):
        """Value injection remains a two-read adapter, never a default reopen."""

        matrix_value = independent._core_matrix()
        envelope_value = independent.envelope.build_envelope_contract()
        projection_value = independent._frozen_format_registry_projection()
        matrix = mock.Mock(side_effect=[matrix_value, copy.deepcopy(matrix_value)])
        envelope_provider = mock.Mock(side_effect=[envelope_value, copy.deepcopy(envelope_value)])
        projection = mock.Mock(side_effect=[projection_value, copy.deepcopy(projection_value)])
        body = mock.Mock(side_effect=lambda artifact_id, body_id: self.body)
        forbidden = mock.Mock(side_effect=AssertionError("default provider must not be reopened"))
        with mock.patch.object(independent, "_core_matrix", forbidden), mock.patch.object(
            independent.envelope, "build_envelope_contract", forbidden
        ), mock.patch.object(independent, "_frozen_format_registry_projection", forbidden):
            accepted = independent.accepted_core_extension_allocation_body_bytes(
                self.value,
                producer_expected_golden=package._expected_golden(),
                core_matrix_provider=matrix,
                envelope_provider=envelope_provider,
                format_registry_projection_provider=projection,
                body_provider=body,
            )
        self.assertEqual(accepted, self.body)
        self.assertEqual(matrix.call_count, 2)
        self.assertEqual(envelope_provider.call_count, 2)
        self.assertEqual(projection.call_count, 2)
        self.assertEqual(body.call_count, 2)
        forbidden.assert_not_called()

    def test_producer_validation_replays_its_three_fixed_input_providers_before_caching(self):
        """A cold public validation must not cause a second upstream wave."""

        original_matrix = package.build_core_family_count_matrix
        original_envelope = package.envelope.build_envelope_contract
        original_projection = package._frozen_format_registry_projection
        matrix = mock.Mock(side_effect=original_matrix)
        envelope_provider = mock.Mock(side_effect=original_envelope)
        projection = mock.Mock(side_effect=original_projection)
        package._canonical_state.cache_clear()
        try:
            with mock.patch.object(package, "build_core_family_count_matrix", matrix), mock.patch.object(
                package.envelope, "build_envelope_contract", envelope_provider
            ), mock.patch.object(package, "_frozen_format_registry_projection", projection):
                self.assertTrue(package.validate_core_extension_allocation_manifest(self.value))
            self.assertEqual(matrix.call_count, 2)
            self.assertEqual(envelope_provider.call_count, 2)
            self.assertEqual(projection.call_count, 2)
        finally:
            package._canonical_state.cache_clear()

    def test_second_input_provider_swap_is_rejected_before_body_read(self):
        good = __import__("eval.persona_v2_contract", fromlist=["build_envelope_contract"]).build_envelope_contract()
        bad = copy.deepcopy(good)
        bad["fixture_id"] = "changed"
        body = mock.Mock(side_effect=lambda artifact_id, body_id: self.body)
        envelope_provider = mock.Mock(side_effect=[good, bad])
        with self.assertRaises(independent.PersonaV2CoreExtensionAllocationManifestValidationError):
            independent.validate_core_extension_allocation_manifest(
                self.value,
                producer_expected_golden=package._expected_golden(),
                envelope_provider=envelope_provider,
                body_provider=body,
            )
        self.assertEqual(envelope_provider.call_count, 2)
        body.assert_not_called()

    def test_tampering_rejected_before_or_during_external_read(self):
        metadata = copy.deepcopy(self.value)
        metadata["row_count"] -= 1
        untouched = mock.Mock(side_effect=lambda artifact_id, body_id: self.body)
        with self.assertRaises(independent.PersonaV2CoreExtensionAllocationManifestValidationError):
            self._independent_validate(metadata, provider=untouched)
        untouched.assert_not_called()

        authority = copy.deepcopy(self.value)
        authority["authority"]["authorizes_g0_freeze"] = True
        untouched = mock.Mock(side_effect=lambda artifact_id, body_id: self.body)
        with self.assertRaises(independent.PersonaV2CoreExtensionAllocationManifestValidationError):
            self._independent_validate(authority, provider=untouched)
        untouched.assert_not_called()

        calls = 0
        def switching_provider(_artifact_id, _body_id):
            nonlocal calls
            calls += 1
            return self.body if calls == 1 else self.body[:-1]
        with self.assertRaises(independent.PersonaV2CoreExtensionAllocationManifestValidationError):
            self._independent_validate(self.value, provider=switching_provider)
        self.assertEqual(calls, 2)

    def test_unknown_and_too_deep_descriptor_rejected_before_input_provider(self):
        unknown = copy.deepcopy(self.value)
        unknown["unknown"] = 1
        provider = mock.Mock(side_effect=lambda: self.matrix)
        with self.assertRaises(independent.PersonaV2CoreExtensionAllocationManifestValidationError):
            independent.validate_core_extension_allocation_manifest(
                unknown,
                producer_expected_golden=package._expected_golden(),
                core_matrix_provider=provider,
            )
        provider.assert_not_called()

        nested = copy.deepcopy(self.value)
        deep = {}
        cursor = deep
        for _ in range(33):
            child = {}
            cursor["next"] = child
            cursor = child
        nested["canonical_limits"] = deep
        provider = mock.Mock(side_effect=lambda: self.matrix)
        with self.assertRaises(independent.PersonaV2CoreExtensionAllocationManifestValidationError):
            independent.validate_core_extension_allocation_manifest(
                nested,
                producer_expected_golden=package._expected_golden(),
                core_matrix_provider=provider,
            )
        provider.assert_not_called()

    def test_accepted_body_is_the_second_owned_read_without_third_open(self):
        provider = mock.Mock(side_effect=lambda artifact_id, body_id: self.body)
        accepted = independent.accepted_core_extension_allocation_body_bytes(
            self.value,
            producer_expected_golden=package._expected_golden(),
            core_matrix_value=self.matrix,
            body_provider=provider,
        )
        self.assertIs(type(accepted), bytes)
        self.assertEqual(accepted, self.body)
        self.assertEqual(provider.call_count, 2)

    def test_warm_cache_rechecks_matching_golden_configuration(self):
        package.build_core_extension_allocation_manifest()  # warm the LRU state.
        wrong = (1, "0" * 64)
        with mock.patch.object(package, "EXPECTED_CANONICAL_BYTES", wrong[0]), mock.patch.object(
            package, "EXPECTED_SHA256", wrong[1]
        ), mock.patch.object(independent, "EXPECTED_CANONICAL_BYTES", wrong[0]), mock.patch.object(
            independent, "EXPECTED_SHA256", wrong[1]
        ):
            with self.assertRaises(package.PersonaV2CoreExtensionAllocationManifestError):
                package.build_core_extension_allocation_manifest()

    def test_bytes_validator_rejects_duplicate_and_noncanonical_descriptor_json(self):
        duplicate = b'{"artifact_id":"x","artifact_id":"y"}'
        with self.assertRaises(independent.PersonaV2CoreExtensionAllocationManifestValidationError):
            independent.validate_core_extension_allocation_manifest_bytes(
                duplicate,
                producer_expected_golden=package._expected_golden(),
            )
        noncanonical = b" " + self.raw
        with self.assertRaises(independent.PersonaV2CoreExtensionAllocationManifestValidationError):
            independent.validate_core_extension_allocation_manifest_bytes(
                noncanonical,
                producer_expected_golden=package._expected_golden(),
            )

    def test_detached_outputs_no_producer_import_and_fail_closed_issuance(self):
        descriptor = package.build_core_extension_allocation_manifest()
        descriptor["artifact_id"] = "tampered"
        self.assertNotEqual(descriptor, package.build_core_extension_allocation_manifest())
        rows = package.build_core_extension_allocation_rows()
        rows[0]["full_count"] = 0
        self.assertNotEqual(rows, package.build_core_extension_allocation_rows())
        with self.assertRaises(package.PersonaV2CoreExtensionAllocationManifestError):
            package.require_frozen_core_extension_allocation_manifest()
        validator_path = Path(__file__).with_name("persona_v2_core_extension_allocation_manifest_validator.py")
        tree = ast.parse(validator_path.read_text(encoding="utf-8"), filename=str(validator_path))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.append(node.module)
                imported.extend(alias.name for alias in node.names)
        self.assertFalse(any("persona_v2_core_extension_allocation_manifest" in name for name in imported))
        producer_path = Path(__file__).with_name("persona_v2_core_extension_allocation_manifest.py")
        self.assertNotIn(
            "persona_v2_format_implementation_registry",
            producer_path.read_text(encoding="utf-8"),
        )
        self.assertNotIn(
            "persona_v2_format_implementation_registry",
            validator_path.read_text(encoding="utf-8"),
        )

    @unittest.skipUnless(
        os.environ.get("KCS_RUN_CORE_EXTENSION_ALLOCATION_FULL") == "1",
        "set KCS_RUN_CORE_EXTENSION_ALLOCATION_FULL=1 to run the pre-freeze full gate",
    )
    def test_opt_in_descriptor_full_gate(self):
        started = time.monotonic()
        provider = mock.Mock(side_effect=lambda artifact_id, body_id: self.body)
        self.assertTrue(self._independent_validate(self.value, provider=provider))
        self.assertEqual(provider.call_count, 2)
        self.assertEqual(
            (len(self.raw), hashlib.sha256(self.raw).hexdigest()),
            (5357, "ca7caa3813d8f359785cb4dc65e7155f6e36153ba651e1a4b3af0d3695780e9f"),
        )
        self.assertLess(time.monotonic() - started, 120)

    @unittest.skipUnless(
        os.environ.get("KCS_RUN_CORE_EXTENSION_ALLOCATION_COLD") == "1",
        "set KCS_RUN_CORE_EXTENSION_ALLOCATION_COLD=1 to run two hash-seed cold replays",
    )
    def test_opt_in_two_seed_cold_replay(self):
        root = Path(__file__).resolve().parents[1]
        script = """
import hashlib
import json
from eval import persona_v2_core_extension_allocation_manifest as m
value = m.build_core_extension_allocation_manifest()
body = m.core_extension_allocation_body_bytes()
m.validate_core_extension_allocation_manifest(value)
raw = m.canonical_json_bytes(value)
print(json.dumps({
    'descriptor_bytes': len(raw),
    'descriptor_sha256': hashlib.sha256(raw).hexdigest(),
    'body_bytes': len(body),
    'body_sha256': hashlib.sha256(body).hexdigest(),
}, sort_keys=True))
"""
        receipts = []
        for seed in ("0", "1"):
            environment = os.environ.copy()
            environment.update({"PYTHONHASHSEED": seed, "LANG": "C", "LC_ALL": "C", "TZ": "UTC"})
            completed = subprocess.run(
                [sys.executable, "-c", script],
                cwd=root,
                env=environment,
                text=True,
                capture_output=True,
                check=True,
                timeout=180,
            )
            receipts.append(json.loads(completed.stdout))
        self.assertEqual(receipts[0], receipts[1])
        self.assertEqual(receipts[0]["body_bytes"], 426_889)
        self.assertEqual(receipts[0]["body_sha256"], package.EXPECTED_BODY_SHA256)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
