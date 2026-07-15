"""Focused and adversarial gates for the primary-use-case catalog."""

from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import unittest
from unittest import mock

from eval import persona_v2_artifact_common as artifact_common
from eval import persona_v2_contract as envelope
from eval import persona_v2_primary_use_case_catalog as catalog
from eval import persona_v2_primary_use_case_catalog_validator as independent
from eval import persona_v2_topology as topology


EXPECTED_CANONICAL_BYTES = 30_008
EXPECTED_SHA256 = (
    "024916c0d79d30ce859d102ae0e30f34f5209f0665b587151f2c0b410df77624"
)


class PersonaV2PrimaryUseCaseCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.envelope_value = envelope.build_envelope_contract()
        cls.topology_value = topology.build_topology_contract()
        cls.value = catalog.build_primary_use_case_catalog()

    def _independent_validate(self, value):
        return independent.validate_primary_use_case_catalog(
            value,
            envelope_value=self.envelope_value,
            topology_value=self.topology_value,
        )

    def _assert_independent_rejects_rehashed(self, value):
        raw = artifact_common.canonical_json_bytes(
            value,
            label="rehashed primary use case catalog",
            max_bytes=catalog.MAX_CATALOG_BYTES,
        )
        with (
            mock.patch.object(
                independent, "EXPECTED_CATALOG_CANONICAL_BYTES", len(raw)
            ),
            mock.patch.object(
                independent,
                "EXPECTED_CATALOG_SHA256",
                hashlib.sha256(raw).hexdigest(),
            ),
            self.assertRaises(
                independent.PersonaV2PrimaryUseCaseCatalogValidationError
            ),
        ):
            self._independent_validate(value)

    def test_canonical_pin_and_both_validators(self):
        raw = catalog.canonical_json_bytes(self.value)
        self.assertEqual(len(raw), EXPECTED_CANONICAL_BYTES)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), EXPECTED_SHA256)
        self.assertEqual(catalog.primary_use_case_catalog_sha256(), EXPECTED_SHA256)
        self.assertTrue(catalog.validate_primary_use_case_catalog(self.value))
        self.assertTrue(self._independent_validate(self.value))

    def test_exact_one_to_one_role_topology_and_positive_family_joins(self):
        rows = self.value["primary_use_cases"]
        self.assertEqual(len(rows), 20)
        self.assertEqual(
            [row["persona_id"] for row in rows], list(catalog.PERSONA_IDS)
        )
        self.assertEqual(len({row["primary_use_case_id"] for row in rows}), 20)
        self.assertEqual(len({row["persona_role"] for row in rows}), 20)

        envelope_by_persona = {
            row["persona_id"]: row for row in self.envelope_value["personas"]
        }
        topology_by_persona = {
            row["persona_id"]: row for row in self.topology_value["personas"]
        }
        for row in rows:
            persona_id = row["persona_id"]
            self.assertEqual(
                row["persona_role"], envelope_by_persona[persona_id]["role"]
            )
            self.assertEqual(row["required_scope_role"], "primary")
            self.assertEqual(
                row["representative_relative_path"],
                envelope_by_persona[persona_id]["representative_primary_scope"],
            )
            matching = [
                scope
                for scope in topology_by_persona[persona_id]["scopes"]
                if scope["relative_path"] == row["representative_relative_path"]
            ]
            self.assertEqual(len(matching), 1)
            self.assertEqual(matching[0]["kind"], "primary")
            self.assertEqual(
                matching[0]["functional_slot"],
                row["representative_functional_slot"],
            )
            self.assertEqual(
                row["required_families"],
                [item["family_id"] for item in row["required_family_marginal_join"]],
            )
            for join in row["required_family_marginal_join"]:
                self.assertGreater(join["full_physical_ratio_pct"], 0)
                self.assertGreater(join["full_physical_file_count"], 0)
                self.assertEqual(
                    join["full_physical_ratio_pct"],
                    envelope_by_persona[persona_id]["format_percentages"][
                        join["family_id"]
                    ],
                )

    def test_proposal_format_meaning_and_ellipsis_resolution_are_explicit(self):
        by_persona = {
            row["persona_id"]: row for row in self.value["primary_use_cases"]
        }
        self.assertEqual(
            by_persona["p05"]["proposal_format_terms"],
            ["csv", "xlsx", "structured", "sql"],
        )
        self.assertEqual(
            by_persona["p05"]["required_families"],
            ["csv_tsv", "xlsx", "structured_text"],
        )
        self.assertEqual(
            by_persona["p07"]["required_families"],
            ["pdf_scan", "pdf_text", "txt_log", "docx"],
        )
        self.assertEqual(
            by_persona["p16"]["required_families"],
            ["pdf_text", "pdf_scan", "csv_tsv", "docx", "xlsx", "domain_binary"],
        )
        self.assertIn(
            "ellipses are shorthand only",
            self.value["policy"]["proposal_ellipsis_resolution"],
        )
        self.assertTrue(
            all(
                "..." not in row["representative_relative_path"]
                for row in self.value["primary_use_cases"]
            )
        )

    def test_lifecycle_and_query_requirements_are_allowlisted(self):
        lifecycle = set(catalog.LIFECYCLE_CAPABILITY_ALLOWLIST)
        query = set(catalog.QUERY_STRATUM_ALLOWLIST)
        for row in self.value["primary_use_cases"]:
            self.assertTrue(set(row["required_lifecycle_capabilities"]) <= lifecycle)
            self.assertTrue(set(row["required_query_strata"]) <= query)
        by_persona = {
            row["persona_id"]: row for row in self.value["primary_use_cases"]
        }
        self.assertEqual(
            by_persona["p03"]["required_query_strata"],
            ["current-fact", "deleted", "purged-negative"],
        )
        self.assertEqual(
            by_persona["p04"]["required_lifecycle_capabilities"],
            ["edit", "derive", "duplicate"],
        )

    def test_synthetic_non_pii_negative_authority_and_later_ids_absent(self):
        self.assertEqual(set(self.value["authority"]), catalog.AUTHORITY_FIELDS)
        self.assertTrue(
            all(type(flag) is bool and flag is False for flag in self.value["authority"].values())
        )
        self.assertIs(self.value["g0_contract_frozen"], False)
        self.assertIs(self.value["policy"]["synthetic_data_only"], True)
        self.assertIs(self.value["policy"]["synthetic_personal_data_present"], False)
        self.assertTrue(
            all(
                row["data_classification"] == "synthetic-non-pii"
                for row in self.value["primary_use_cases"]
            )
        )
        raw = catalog.canonical_json_bytes(self.value)
        for forbidden in (
            b'"absolute_path"',
            b'"final_id"',
            b'"final_materialization_id"',
            b'"final_source_id"',
            b'"materialization_id"',
            b'"query_id"',
            b'"query_text"',
            b'"rendered_query_text"',
            b'"source_id"',
        ):
            self.assertNotIn(forbidden, raw)
        self.assertTrue(
            all(
                not row["representative_relative_path"].startswith(("/", "\\"))
                for row in self.value["primary_use_cases"]
            )
        )

    def test_validator_is_builder_independent_and_builder_is_deep_detached(self):
        tree = ast.parse(inspect.getsource(independent))
        imported_modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported_modules.add(node.module or "")
        self.assertFalse(
            any(
                name.endswith("persona_v2_primary_use_case_catalog")
                for name in imported_modules
            )
        )

        changed = catalog.build_primary_use_case_catalog()
        changed["primary_use_cases"][0]["required_families"].pop()
        changed["policy"]["format_term_to_family"][0]["family_id"] = "txt_log"
        fresh = catalog.build_primary_use_case_catalog()
        self.assertEqual(
            fresh["primary_use_cases"][0]["required_families"],
            ["md", "code", "structured_text"],
        )
        self.assertEqual(
            fresh["policy"]["format_term_to_family"][0],
            {"family_id": "md", "proposal_format_term": "md"},
        )
        with self.assertRaises(catalog.PersonaV2PrimaryUseCaseCatalogError):
            catalog.validate_primary_use_case_catalog(changed)

    def test_rehashed_semantic_tampering_extra_keys_and_absolute_paths_are_rejected(self):
        mutations = []

        changed = copy.deepcopy(self.value)
        changed["primary_use_cases"][1]["primary_use_case_id"] = changed[
            "primary_use_cases"
        ][0]["primary_use_case_id"]
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["primary_use_cases"][0]["persona_role"] = "site-reliability-engineer"
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["primary_use_cases"][0]["required_family_marginal_join"][0][
            "full_physical_ratio_pct"
        ] = 0
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["primary_use_cases"][0]["representative_relative_path"] = (
            "/tmp/absolute"
        )
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["primary_use_cases"][0]["required_lifecycle_capabilities"][0] = (
            "unknown"
        )
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["primary_use_cases"][0]["required_query_strata"][0] = "unknown"
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["primary_use_cases"][0]["query_text"] = "forbidden"
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["authority"]["authorizes_physical_write"] = True
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["remaining_blockers"] = ["all-blockers-cleared"]
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["unexpected"] = False
        mutations.append(changed)

        for changed in mutations:
            self._assert_independent_rejects_rehashed(changed)

    def test_null_float_negative_and_hostile_repr_are_rejected(self):
        for replacement in (None, 1.0, -1):
            changed = copy.deepcopy(self.value)
            changed["summary"]["persona_count"] = replacement
            with self.assertRaises(catalog.PersonaV2PrimaryUseCaseCatalogError):
                catalog.validate_primary_use_case_catalog(changed)

        class Hostile:
            def __repr__(self):
                raise AssertionError("repr must not be called")

        changed = copy.deepcopy(self.value)
        changed["summary"]["persona_count"] = Hostile()
        with self.assertRaises(catalog.PersonaV2PrimaryUseCaseCatalogError):
            catalog.validate_primary_use_case_catalog(changed)

    def test_snapshot_and_closing_reauthentication_detect_mutation(self):
        value = catalog.build_primary_use_case_catalog()
        envelope_value = envelope.build_envelope_contract()
        topology_value = topology.build_topology_contract()
        original = independent._validate_primary_use_case_catalog_snapshot

        def mutate_after_snapshot(snapshot, *, envelope_value, topology_value):
            result = original(
                snapshot,
                envelope_value=envelope_value,
                topology_value=topology_value,
            )
            value["completion_claims"]["source_instance_membership_bound"] = True
            return result

        with (
            mock.patch.object(
                independent,
                "_validate_primary_use_case_catalog_snapshot",
                side_effect=mutate_after_snapshot,
            ),
            self.assertRaises(
                independent.PersonaV2PrimaryUseCaseCatalogValidationError
            ),
        ):
            independent.validate_primary_use_case_catalog(
                value,
                envelope_value=envelope_value,
                topology_value=topology_value,
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
