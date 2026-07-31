"""Focused and adversarial gates for lifecycle coverage catalog v1."""

from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

from eval import persona_v2_artifact_common as artifact_common
from eval import persona_v2_lifecycle_coverage_catalog as catalog
from eval import persona_v2_lifecycle_coverage_catalog_validator as independent


EXPECTED_CANONICAL_BYTES = 1_385_596
EXPECTED_SHA256 = (
    "1760eeed4bde8c7a1c2c720a437fb4c3d62971af3f2159e768696e938389b9d4"
)


class PersonaV2LifecycleCoverageCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = catalog.build_lifecycle_coverage_catalog()
        inputs = catalog._cached_shared_inputs()
        cls.dependencies = {
            "envelope": copy.deepcopy(inputs["envelope"]),
            "accounting": copy.deepcopy(inputs["accounting"]),
            "lifecycle": copy.deepcopy(inputs["lifecycle"]),
            "overlay": copy.deepcopy(inputs["overlay"]),
            "semantic_catalog": copy.deepcopy(inputs["semantic_catalog"]),
        }

    def _validate_independent(self, value, dependencies=None, **kwargs):
        values = self.dependencies if dependencies is None else dependencies
        return independent.validate_lifecycle_coverage_catalog(
            value,
            envelope_value=values["envelope"],
            chunk_accounting_value=values["accounting"],
            lifecycle_demand_value=values["lifecycle"],
            overlay_contract_value=values["overlay"],
            source_semantic_catalog_value=values["semantic_catalog"],
            **kwargs,
        )

    def _assert_rehashed_rejected(self, value):
        raw = catalog.canonical_json_bytes(value)
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
                independent.PersonaV2LifecycleCoverageCatalogValidationError
            ),
        ):
            self._validate_independent(value)

    def test_canonical_pin_dependencies_and_negative_authority(self):
        raw = catalog.canonical_json_bytes(self.value)
        self.assertEqual(len(raw), EXPECTED_CANONICAL_BYTES)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), EXPECTED_SHA256)
        self.assertEqual(
            independent.EXPECTED_CATALOG_CANONICAL_BYTES,
            EXPECTED_CANONICAL_BYTES,
        )
        self.assertEqual(independent.EXPECTED_CATALOG_SHA256, EXPECTED_SHA256)
        self.assertTrue(self._validate_independent(self.value))
        self.assertTrue(catalog.validate_lifecycle_coverage_catalog(self.value))
        self.assertEqual(catalog.lifecycle_coverage_catalog_sha256(self.value), EXPECTED_SHA256)
        self.assertEqual(set(self.value["authority"]), catalog.AUTHORITY_FIELDS)
        self.assertTrue(
            all(type(flag) is bool and flag is False for flag in self.value["authority"].values())
        )
        self.assertIs(self.value["g0_contract_frozen"], False)
        self.assertEqual(
            self.value["input_binding_order"],
            [
                "persona-v2-envelope",
                "persona-v2-chunk-accounting",
                "persona-v2-lifecycle-demand",
                "persona-v2-overlay-contract",
                "persona-v2-source-semantic-membership-catalog",
            ],
        )

    def test_exact_primary_allocation_and_source_ref_math(self):
        expected = {"P": 15, "X": 20, "Y": 33, "N": 0, "U": 32, "I": 5}
        for persona_id in catalog.PERSONA_IDS:
            primary = [
                row
                for row in self.value["primary_capabilities"]
                if row["persona_id"] == persona_id
            ]
            companions = [
                row
                for row in self.value["cross_format_companion_requirements"]
                if row["persona_id"] == persona_id
            ]
            counts = {key: 0 for key in catalog.ALLOCATION_CLASS_ORDER}
            for row in primary:
                counts[row["allocation_class"]] += 1
            self.assertEqual(len(primary), 105)
            self.assertEqual(counts, expected)
            self.assertEqual(len(companions), 10)
            self.assertEqual(
                {key: sum(row["allocation_class"] == key for row in companions) for key in ("U", "Y")},
                {"U": 9, "Y": 1},
            )
            self.assertEqual(sum(row["w1_typed_edit_required"] for row in primary), 69)
            self.assertEqual(sum(row["w1_typed_edit_required"] for row in companions), 1)
        self.assertEqual(
            self.value["suite_summary"],
            {
                "allocation_class_primary_counts": {"P": 300, "X": 400, "Y": 660, "N": 0, "U": 640, "I": 100},
                "cross_format_companion_requirement_count": 200,
                "matched_w0_source_ref_requirement_count": 2_300,
                "persona_count": 20,
                "primary_capability_count": 2_100,
                "primary_capability_count_per_persona": 105,
                "purge_witness_requirement_count": 300,
                "reserved_unused_semantic_anchor_slot_count": 100,
                "w1_edited_source_ref_requirement_count": 1_400,
            },
        )
        self.assertEqual(
            self.value["source_matching_domain"][
                "w0_source_ref_requirement_count_per_persona"
            ],
            115,
        )
        self.assertNotIn(
            "matched_w0_source_ref_count_per_persona",
            self.value["source_matching_domain"],
        )

    def test_purge_witnesses_are_unique_and_forbid_every_other_consumer(self):
        witnesses = self.value["purge_witness_requirements"]
        self.assertEqual(len(witnesses), 300)
        self.assertEqual(len({row["purge_witness_key"] for row in witnesses}), 300)
        expected_forbidden = [
            "P-prime-capacity-replacement",
            "any-other-source-or-rendition",
            "distractor-content",
            "padding-or-ambient-content",
        ]
        for persona_id in catalog.PERSONA_IDS:
            rows = [row for row in witnesses if row["persona_id"] == persona_id]
            self.assertEqual(len(rows), 15)
            self.assertTrue(all(row["forbidden_consumers"] == expected_forbidden for row in rows))
            self.assertTrue(all(row["suite_global_uniqueness_required"] is True for row in rows))

    def test_move_receipt_is_four_stable_plus_one_edited_and_fail_closed(self):
        for policy in self.value["move_receipt_policies"]:
            self.assertEqual(len(policy["stable_move_capability_keys"]), 4)
            self.assertEqual(policy["stable_move_observation_count"], 4)
            self.assertEqual(policy["bundle_resolution_stage"], "post-W1-attestation-before-W2-event-compilation")
            self.assertEqual((policy["qIE_inclusive_minimum"], policy["qIE_inclusive_maximum"]), (1, 70))
            self.assertEqual((policy["qIM_inclusive_minimum"], policy["qIM_inclusive_maximum"]), (5, 350))
            self.assertEqual(policy["nIM_exact"], 5)
            self.assertIs(policy["edited_move_old_history_equals_new_current_count"], True)
            self.assertIs(policy["edited_move_old_history_endpoint_set_disjoint_from_new_current"], True)
            self.assertIs(policy["edited_w1_current_count_must_equal_move_count"], True)
            self.assertIs(policy["receipt_attested"], False)
            self.assertIn("old-history-and-new-current-endpoint-overlap", policy["failure_modes_block_w2"])
            self.assertEqual(
                policy["w5_pre_incidental_cap_proof"],
                {
                    "full_cap": 20_400,
                    "full_headroom": 9_780,
                    "full_upper": 10_620,
                    "pilot_cap": 2_040,
                    "pilot_headroom": 600,
                    "pilot_upper": 1_440,
                    "upper_formula": "incidental-current-upper-plus-qIE-upper-plus-qIM-upper",
                },
            )

    def test_operation_scope_path_and_symbol_algebra_is_closed(self):
        operations = self.value["operation_algebra"]
        self.assertEqual(len(operations), 19)
        self.assertEqual(len(self.value["scope_relation_rules"]), 9)
        self.assertEqual(len(self.value["path_transition_rules"]), 13)
        projections = [
            (term["metric_id"], term["projection"])
            for term in operations[0]["delta_terms"]
        ]
        self.assertEqual(len(projections), 12)
        self.assertEqual(len(set(projections)), 12)
        symbols = {row["symbol"] for row in self.value["symbol_contracts"]}
        self.assertEqual(len(symbols), 12)
        for operation in operations:
            self.assertEqual(
                [(term["metric_id"], term["projection"]) for term in operation["delta_terms"]],
                projections,
            )
            self.assertTrue(all(term["symbol"] in symbols for term in operation["delta_terms"]))
        by_key = {row["operation_key"]: row for row in operations}
        move = {row["projection"]: row for row in by_key["w2-move"]["delta_terms"]}
        self.assertEqual(move["incidental-history-only"]["symbol"], "qIM")
        self.assertEqual(move["raw-cas-regular-objects"]["symbol"], "nIM")
        for key, symbol in (("w4-create-x-prime", "qX"), ("w5-create-p-prime", "qP")):
            term = next(
                row
                for row in by_key[key]["delta_terms"]
                if row["projection"] == "reachable-path-bindings"
            )
            self.assertEqual((term["direction"], term["symbol"]), ("increase", symbol))
        self.assertIn("w3-duplicate-diagnostic-same-scope", by_key)
        self.assertIn("w3-duplicate-diagnostic-cross-scope", by_key)

    def test_historical_receipt_is_authenticated_but_not_source_attestation(self):
        receipt = self.value["historical_lifecycle_source_matchability_receipt"]
        self.assertEqual(receipt["available_w1_prior_semantic_anchor_count_per_persona"], 12)
        self.assertEqual(receipt["singleton_prior_profile_positions_one_based"], [17, 18, 19, 20])
        self.assertEqual(receipt["historical_w1_revision_anchor_deficit_per_persona"], 53)
        self.assertIs(receipt["semantic_catalog_singleton_cycle_authenticated"], True)
        self.assertIs(receipt["semantic_anchor_assignment_root_bound"], False)
        self.assertIs(receipt["semantic_anchor_source_instance_assignment_attested"], False)
        self.assertIs(receipt["source_matchable_authority"], False)
        self.assertEqual(
            receipt["receipt_scope"],
            "deterministic-design-reconciliation-not-source-instance-attestation",
        )

    def test_query_oracle_backedge_and_solved_identifiers_are_absent(self):
        for module in (catalog, independent):
            tree = ast.parse(inspect.getsource(module))
            imported = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imported.append(node.module or "")
            self.assertFalse(any("query" in name or "oracle" in name for name in imported))
        self.assertIs(self.value["completion_claims"]["query_or_oracle_dependency_present"], False)
        self.assertIs(self.value["completion_claims"]["solved_scope_path_quota_or_final_ids_present"], False)
        self.assertIs(self.value["dependency_direction_contract"]["corpus_source_matching_may_import_query_or_oracle"], False)

        forbidden = {
            "absolute_path", "assigned_scope_key", "chunk_id", "final_materialization_id",
            "final_source_id", "materialization_id", "oracle_key", "query_id",
            "query_key", "query_text", "relative_path", "solved_scope_key", "source_id",
        }

        def walk(item):
            if type(item) is dict:
                self.assertFalse(set(item) & forbidden)
                for child in item.values():
                    walk(child)
            elif type(item) is list:
                for child in item:
                    walk(child)

        walk(self.value)
        with self.assertRaises(catalog.PersonaV2LifecycleCoverageCatalogError):
            catalog.require_source_matching()

    def test_independent_validator_rejects_rehashed_semantic_and_type_tampering(self):
        mutations = []
        changed = copy.deepcopy(self.value)
        changed["primary_capabilities"][0]["allocation_class"] = "Y"
        mutations.append(changed)
        changed = copy.deepcopy(self.value)
        changed["move_receipt_policies"][0]["qIM_inclusive_maximum"] = 351
        mutations.append(changed)
        changed = copy.deepcopy(self.value)
        changed["operation_algebra"][0]["delta_terms"][0]["coefficient"] = True
        mutations.append(changed)
        changed = copy.deepcopy(self.value)
        changed["authority"]["authorizes_source_instance_matching"] = 0
        mutations.append(changed)
        for changed in mutations:
            with self.subTest(change=changed):
                self._assert_rehashed_rejected(changed)

    def test_dependency_tampering_and_backedge_binding_are_rejected(self):
        dependencies = copy.deepcopy(self.dependencies)
        dependencies["semantic_catalog"]["assignment_contract"][
            "singleton_anchor_profile_cycle"
        ] = "forged-cycle"
        with self.assertRaises(
            independent.PersonaV2LifecycleCoverageCatalogValidationError
        ):
            self._validate_independent(self.value, dependencies)

        changed = copy.deepcopy(self.value)
        changed["input_bindings"].append(
            {
                "artifact_kind": "semantic-oracle",
                "artifact_schema": "semantic-oracle/v1",
                "artifact_schema_version": 1,
                "canonical_bytes": 1,
                "dependency_role": "forbidden",
                "fixture_id": "kio-persona-pc-v2",
                "fixture_schema_version": 2,
                "name": "semantic-oracle",
                "sha256": "0" * 64,
            }
        )
        self._assert_rehashed_rejected(changed)

    def test_builds_are_detached_and_producer_detects_dependency_toctou(self):
        first = catalog.build_lifecycle_coverage_catalog()
        first["primary_capabilities"][0]["allocation_class"] = "X"
        second = catalog.build_lifecycle_coverage_catalog()
        self.assertEqual(second, self.value)

        cached = catalog._cached_shared_inputs()
        original = cached["bindings"][0]["sha256"]

        def observer(inputs):
            inputs["bindings"][0]["sha256"] = "0" * 64

        try:
            with self.assertRaises(catalog.PersonaV2LifecycleCoverageCatalogError):
                catalog._canonical_catalog(dependency_observer=observer)
        finally:
            cached["bindings"][0]["sha256"] = original

    def test_independent_validator_detects_target_and_dependency_toctou(self):
        target = copy.deepcopy(self.value)
        dependencies = copy.deepcopy(self.dependencies)

        def mutate_target(original, _dependencies):
            original["authority"]["authorizes_source_instance_matching"] = True

        with self.assertRaises(
            independent.PersonaV2LifecycleCoverageCatalogValidationError
        ):
            self._validate_independent(
                target,
                dependencies,
                validation_observer=mutate_target,
            )

        target = copy.deepcopy(self.value)
        dependencies = copy.deepcopy(self.dependencies)

        def mutate_dependency(_original, originals):
            originals["lifecycle"]["g0_contract_frozen"] = True

        with self.assertRaises(
            independent.PersonaV2LifecycleCoverageCatalogValidationError
        ):
            self._validate_independent(
                target,
                dependencies,
                validation_observer=mutate_dependency,
            )

    def test_independent_validator_does_not_import_producer(self):
        tree = ast.parse(inspect.getsource(independent))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        self.assertFalse(
            any(name.endswith("persona_v2_lifecycle_coverage_catalog") for name in imported)
        )

    def test_hashseed_determinism(self):
        code = (
            "import hashlib; "
            "from eval import persona_v2_lifecycle_coverage_catalog as c; "
            "v=c.build_lifecycle_coverage_catalog(); r=c.canonical_json_bytes(v); "
            "print(len(r), hashlib.sha256(r).hexdigest())"
        )
        root = Path(__file__).resolve().parents[1]
        observed = []
        for seed in ("1", "777"):
            environment = dict(os.environ, PYTHONHASHSEED=seed)
            completed = subprocess.run(
                [sys.executable, "-c", code],
                cwd=root,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
                timeout=360,
            )
            observed.append(completed.stdout.strip())
        self.assertEqual(
            observed,
            [f"{EXPECTED_CANONICAL_BYTES} {EXPECTED_SHA256}"] * 2,
        )


if __name__ == "__main__":
    unittest.main()
