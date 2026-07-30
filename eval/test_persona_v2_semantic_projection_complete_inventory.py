"""Contract, full replay, and cold gates for the complete v2 inventory."""

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
from collections import Counter
from unittest import mock

from eval import persona_v2_semantic_projection_complete_inventory as package
from eval import (
    persona_v2_semantic_projection_complete_inventory_validator as independent,
)


EXPECTED_CLASS_ORDER = (
    "topology-path-load",
    "realism-locale-security",
    "route-scores",
    "primary-use-case-corpus-half",
    "recipe-content-filename-policy",
    "fact-graph",
    "base-source-content-context",
    "effective-source-membership",
    "concrete-overlay-relations",
    "source-instance-parameters",
    "query-independent-lifecycle-fact-rendition-rules",
    "payload-equivalence-rules",
)
EXPECTED_RECEIPT_COUNTS = {
    "topology-path-load": 1,
    "realism-locale-security": 1,
    "route-scores": 1,
    "primary-use-case-corpus-half": 1,
    "recipe-content-filename-policy": 1,
    "fact-graph": 20,
    "base-source-content-context": 73,
    "effective-source-membership": 20,
    "concrete-overlay-relations": 40,
    "source-instance-parameters": 74,
    "query-independent-lifecycle-fact-rendition-rules": 20,
    "payload-equivalence-rules": 1,
}
EXPECTED_AUTHORITY_FIELDS = frozenset(
    {
        "actual_chunks_attested",
        "actual_lifecycle_receipts_attested",
        "authorizes_compiled_history_plan",
        "authorizes_corpus_semantic_namespace",
        "authorizes_final_identifiers",
        "authorizes_g0_freeze",
        "authorizes_history_mutation",
        "authorizes_kio_execution",
        "authorizes_namespace_completion",
        "authorizes_physical_write",
        "authorizes_query_rendering",
        "authorizes_renderer_execution",
        "authorizes_solver_execution",
        "authorizes_source_identity_derivation",
        "authorizes_source_plan",
        "compiled_history_plan_available",
        "corpus_semantic_namespace_available",
        "filesystem_writer_available",
        "formal_capacity_gate_satisfied",
        "history_executor_available",
        "kio_execution_available",
        "physical_materialization_observed",
        "solver_solution_available",
        "source_identity_namespace_authoritative",
    }
)
EXPECTED_RECEIPT_COUNT = 253
EXPECTED_JSON_BODY_COUNT = 67
EXPECTED_JSONL_BODY_COUNT = 186
EXPECTED_SUITE_CANONICAL_BYTES = 697_466
EXPECTED_SUITE_SHA256 = (
    "820c976a930c3f2ed0a54e44c08b01cad8a0879513f1b06012e353fb9bd3fd91"
)
EXPECTED_EXTERNAL_BODY_BYTES = 155_741_381
EXPECTED_ORDERED_PROJECTION_PINS_SHA256 = (
    "d9ffe202e88bff01c3238e0b4749e4c9cd1e8a759b420d2e12dcf27d8b25b7c8"
)
EXPECTED_CLASS_BYTES = {
    "base-source-content-context": 121_020_941,
    "concrete-overlay-relations": 8_988_409,
    "effective-source-membership": 2_066_688,
    "fact-graph": 461_816,
    "payload-equivalence-rules": 4_288,
    "primary-use-case-corpus-half": 6_790,
    "query-independent-lifecycle-fact-rendition-rules": 5_057_286,
    "realism-locale-security": 32_762,
    "recipe-content-filename-policy": 250_388,
    "route-scores": 88_085,
    "source-instance-parameters": 17_630_829,
    "topology-path-load": 133_187,
}
EXPECTED_CLASS_MAXIMUM_BODY_BYTES = {
    "base-source-content-context": 2_484_590,
    "concrete-overlay-relations": 658_944,
    "effective-source-membership": 103_840,
    "fact-graph": 23_252,
    "payload-equivalence-rules": 4_288,
    "primary-use-case-corpus-half": 6_790,
    "query-independent-lifecycle-fact-rendition-rules": 256_800,
    "realism-locale-security": 32_762,
    "recipe-content-filename-policy": 250_388,
    "route-scores": 88_085,
    "source-instance-parameters": 367_471,
    "topology-path-load": 133_187,
}
EXPECTED_CLASS_ROW_COUNTS = {
    "base-source-content-context": 203_000,
    "concrete-overlay-relations": 25_560,
    "source-instance-parameters": 203_000,
}
EXPECTED_CLASS_MAXIMUM_ROW_BYTES = {
    "base-source-content-context": 633,
    "concrete-overlay-relations": 388,
    "source-instance-parameters": 110,
}
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
MAX_COLD_BUILD_SECONDS = 120 * 60
MAX_COLD_BUILD_RSS_BYTES = 1 * 2**30


def _imports_complete_producer(source):
    target = "persona_v2_semantic_projection_complete_inventory"
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            if any(alias.name.rsplit(".", 1)[-1] == target for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").rsplit(".", 1)[-1] == target:
                return True
            if any(alias.name == target for alias in node.names):
                return True
    return False


def _minimal_complete_preflight_value():
    full_owner = {
        "artifact_kind": "test-owner",
        "artifact_schema": "test.owner/v1",
        "artifact_schema_version": 1,
        "body_framing": "canonical-json",
        "canonical_bytes": 2,
        "coordinates": {},
        "owner_id": "test-owner",
        "owner_role": "test-owner-role",
        "sha256": "0" * 64,
    }
    direct = {
        "body_framing": "canonical-json",
        "canonical_bytes": 2,
        "direct_pin_id": "test-fragment",
        "direct_pin_role": "test-fragment-role",
        "sha256": "1" * 64,
    }
    projection_pin = {
        "artifact_kind": "test-projection",
        "artifact_schema": "test.projection/v1",
        "artifact_schema_version": 1,
        "body_framing": "canonical-json",
        "canonical_bytes": 2,
        "sha256": "2" * 64,
    }
    receipt = {
        "coordinates": {},
        "direct_body_pins": [direct],
        "full_owner_pins": [full_owner],
        "projection_class_id": "topology-path-load",
        "projection_pin": projection_pin,
        "projector": {
            "projector_id": "topology-path-load-content-projector",
            "projector_version": 1,
        },
        "receipt_id": "projection-derivation-topology-path-load",
        "row_kind": "semantic-projection-derivation-receipt",
        "row_schema": package.RECEIPT_SCHEMA,
        "validation": {
            "independent_derivation_validation_required": True,
            "projection_pin_matches_external_body": True,
            "upstream_owner_validation_result": True,
            "upstream_projection_validation_result": True,
        },
    }
    return {
        "artifact_kind": package.SUITE_KIND,
        "artifact_schema": package.SUITE_SCHEMA,
        "artifact_schema_version": 2,
        "authority": {field: False for field in package.AUTHORITY_FIELDS},
        "canonical_limits": {},
        "completion_claims": {},
        "derivation_receipts": [copy.deepcopy(receipt) for _ in range(253)],
        "fixture_id": package.envelope.FIXTURE_ID,
        "fixture_schema_version": package.envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "hypothesis_status": "synthetic-preflight-test-only",
        "missing_projection_class_ledger": [],
        "orders": {
            "derivation_receipts": "test-order",
            "minimum_projection_classes": list(EXPECTED_CLASS_ORDER),
            "persona": list(package.envelope.PERSONA_IDS),
        },
        "predecessor_inventory_binding": {
            "artifact_kind": "test-predecessor",
            "artifact_schema": "test.predecessor/v1",
            "artifact_schema_version": 1,
            "body_framing": "canonical-json",
            "canonical_bytes": 2,
            "sha256": "3" * 64,
        },
        "projection_class_registry": [
            {
                "coverage_status": "test-covered",
                "derivation_receipt_count": EXPECTED_RECEIPT_COUNTS[class_id],
                "inventory_ordinal": ordinal,
                "projection_class_id": class_id,
            }
            for ordinal, class_id in enumerate(EXPECTED_CLASS_ORDER, start=1)
        ],
        "remaining_blockers": [],
        "summary": {},
    }


class SemanticProjectionCompleteInventoryContractTest(unittest.TestCase):
    """Fast schema/version/cap/non-authority gates without building 253 bodies."""

    def test_exact_public_contract_and_independent_module_boundary(self):
        self.assertEqual(
            package.SUITE_SCHEMA,
            "kio.persona.pc-semantic-projection-derivation-inventory/v2",
        )
        self.assertEqual(
            package.RECEIPT_SCHEMA,
            "kio.persona.pc-semantic-projection-derivation-receipt/v2",
        )
        self.assertEqual(tuple(package.PROJECTION_CLASS_ORDER), EXPECTED_CLASS_ORDER)
        self.assertEqual(tuple(independent.PROJECTION_CLASS_ORDER), EXPECTED_CLASS_ORDER)
        self.assertEqual(package.EXPECTED_RECEIPT_COUNTS, EXPECTED_RECEIPT_COUNTS)
        self.assertEqual(independent.EXPECTED_RECEIPT_COUNTS, EXPECTED_RECEIPT_COUNTS)
        self.assertEqual(sum(EXPECTED_RECEIPT_COUNTS.values()), 253)
        self.assertEqual(package.MAX_RECEIPT_COUNT, 253)
        self.assertEqual(package.MAX_SUITE_BYTES, 2 * 2**20)
        self.assertEqual(package.TARGET_SUITE_BYTES, 1 * 2**20)
        self.assertEqual(package.MAX_CUMULATIVE_PROJECTION_BYTES, 256 * 2**20)
        self.assertEqual(
            package.EXPECTED_SUITE_CANONICAL_BYTES,
            EXPECTED_SUITE_CANONICAL_BYTES,
        )
        self.assertEqual(package.EXPECTED_SUITE_SHA256, EXPECTED_SUITE_SHA256)
        self.assertEqual(
            package.EXPECTED_CUMULATIVE_EXTERNAL_BODY_BYTES,
            EXPECTED_EXTERNAL_BODY_BYTES,
        )
        self.assertEqual(
            package.EXPECTED_ORDERED_PROJECTION_PINS_SHA256,
            EXPECTED_ORDERED_PROJECTION_PINS_SHA256,
        )
        self.assertEqual(
            independent.EXPECTED_SUITE_CANONICAL_BYTES,
            EXPECTED_SUITE_CANONICAL_BYTES,
        )
        self.assertEqual(independent.EXPECTED_SUITE_SHA256, EXPECTED_SUITE_SHA256)
        self.assertEqual(
            independent.EXPECTED_CUMULATIVE_EXTERNAL_BODY_BYTES_FROZEN,
            EXPECTED_EXTERNAL_BODY_BYTES,
        )
        self.assertEqual(
            independent.EXPECTED_ORDERED_PROJECTION_PINS_SHA256,
            EXPECTED_ORDERED_PROJECTION_PINS_SHA256,
        )
        self.assertEqual(
            independent.EXPECTED_UNUSED_PARAMETER_CELL_KEYS,
            EXPECTED_UNUSED_PARAMETER_CELL_KEYS,
        )
        self.assertEqual(package.AUTHORITY_FIELDS, EXPECTED_AUTHORITY_FIELDS)
        self.assertEqual(independent.AUTHORITY_FIELDS, EXPECTED_AUTHORITY_FIELDS)
        self.assertEqual(
            package.NEW_PROJECTOR_IDS,
            independent.EXPECTED_NEW_PROJECTOR_IDS,
        )
        self.assertEqual(
            independent._expected_new_receipt_id(
                "payload-equivalence-rules", {}
            ),
            "payload-equivalence-rules-global",
        )
        v2_receipt = {"row_schema": package.RECEIPT_SCHEMA}
        self.assertEqual(
            independent._partial_v1_receipt(v2_receipt),
            {
                "row_schema": (
                    "kio.persona.pc-semantic-projection-derivation-receipt/v1"
                )
            },
        )
        self.assertEqual(v2_receipt, {"row_schema": package.RECEIPT_SCHEMA})
        for name in (
            "build_semantic_projection_complete_inventory",
            "canonical_json_bytes",
            "projection_body_provider",
            "require_complete_semantic_projection_inventory",
            "semantic_projection_complete_inventory_sha256",
            "validate_semantic_projection_complete_inventory",
        ):
            self.assertTrue(callable(getattr(package, name, None)), name)
        self.assertTrue(
            callable(independent.validate_semantic_projection_complete_inventory)
        )
        self.assertFalse(_imports_complete_producer(inspect.getsource(independent)))

    def test_invalid_metadata_and_receipts_stop_before_external_body_reads(self):
        calls = []

        def forbidden(_receipt):
            calls.append(True)
            raise AssertionError("provider must not run")

        for value in ({}, {"artifact_schema": package.SUITE_SCHEMA}):
            with self.assertRaises(
                independent.PersonaV2SemanticProjectionCompleteInventoryValidationError
            ):
                independent.validate_semantic_projection_complete_inventory(
                    value,
                    projection_body_provider=forbidden,
                )
        self.assertEqual(calls, [])
        for receipt in (None, {}, {field: None for field in package.RECEIPT_FIELDS}):
            with self.assertRaises(
                package.PersonaV2SemanticProjectionCompleteInventoryError
            ):
                package.projection_body_provider(receipt)

    def test_integration_material_reads_and_copies_are_preflight_bounded(self):
        full_owner = {
            "artifact_kind": "test-owner",
            "artifact_schema": "test.owner/v1",
            "artifact_schema_version": 1,
            "body_framing": "canonical-json",
            "canonical_bytes": 2,
            "coordinates": {},
            "owner_id": "test-owner",
            "owner_role": "test-owner-role",
            "sha256": "0" * 64,
        }
        direct = {
            "body_framing": "canonical-json",
            "canonical_bytes": 2,
            "direct_pin_id": "test-fragment",
            "direct_pin_role": "test-fragment-role",
            "sha256": "1" * 64,
        }
        material = {
            "artifact_kind": "test-projection",
            "artifact_schema": "test.projection/v1",
            "artifact_schema_version": 1,
            "body": b"{}",
            "body_framing": "canonical-json",
            "coordinates": {},
            "direct_body_pins": [direct],
            "full_owner_pins": [full_owner],
            "projection_class_id": "payload-equivalence-rules",
            "projector_id": "payload-equivalence-rules-content-projector",
            "receipt_id": "payload-equivalence-rules-global",
        }

        calls = []

        class InfiniteModule:
            @staticmethod
            def values():
                while True:
                    calls.append(True)
                    yield copy.deepcopy(material)

        with self.assertRaises(
            package.PersonaV2SemanticProjectionCompleteInventoryError
        ):
            package._material_iterator(
                InfiniteModule,
                ("values",),
                expected_count=3,
                allowed_classes={"payload-equivalence-rules"},
            )
        self.assertEqual(len(calls), 4)

        oversized = copy.deepcopy(material)
        oversized["body_framing"] = "canonical-jsonl-lf"
        oversized["body"] = b"x" * (package.MAX_JSONL_PROJECTION_BYTES + 1)
        for module in (package, independent):
            with self.subTest(module=module.__name__), self.assertRaises(ValueError):
                module._normalize_material(oversized)

        wrong_identity = copy.deepcopy(material)
        wrong_identity["projector_id"] = "shared-fallback-projector"
        missing_explicit_projector = copy.deepcopy(material)
        missing_explicit_projector["projector_id"] = None
        missing_explicit_receipt = copy.deepcopy(material)
        missing_explicit_receipt["receipt_id"] = None
        boolean_global_projector = {
            "artifact_kind": material["artifact_kind"],
            "artifact_schema": material["artifact_schema"],
            "artifact_schema_version": material["artifact_schema_version"],
            "body": material["body"],
            "body_framing": material["body_framing"],
            "class_id": material["projection_class_id"],
            "coordinates": material["coordinates"],
            "direct_body_pins": material["direct_body_pins"],
            "full_owner_pins": material["full_owner_pins"],
            "projector": {
                "projector_id": material["projector_id"],
                "projector_version": True,
            },
        }
        for candidate in (
            wrong_identity,
            missing_explicit_projector,
            missing_explicit_receipt,
            boolean_global_projector,
        ):
            for module in (package, independent):
                with self.subTest(
                    module=module.__name__,
                    candidate=tuple(sorted(candidate)),
                ), self.assertRaises(ValueError):
                    module._normalize_material(candidate)

    def test_invalid_top_level_shape_fails_before_nested_value_traversal(self):
        class Bomb:
            def __iter__(self):
                raise AssertionError("invalid nested value must not be traversed")

        candidate = {"artifact_schema": package.SUITE_SCHEMA, "junk": Bomb()}
        with self.assertRaises(
            package.PersonaV2SemanticProjectionCompleteInventoryError
        ):
            package.canonical_json_bytes(candidate)
        with self.assertRaises(
            independent.PersonaV2SemanticProjectionCompleteInventoryValidationError
        ):
            independent.validate_semantic_projection_complete_inventory(
                candidate,
                projection_body_provider=lambda _receipt: b"",
            )

    def test_valid_shallow_preflight_and_nested_width_regressions(self):
        baseline = _minimal_complete_preflight_value()
        for module in (package, independent):
            with self.subTest(module=module.__name__):
                self.assertIsNone(module._preflight_inventory_shape(baseline))

        class Bomb:
            def __iter__(self):
                raise AssertionError("shallow-invalid section must not be traversed")

        shallow_cases = []
        for field in (
            "missing_projection_class_ledger",
            "projection_class_registry",
            "remaining_blockers",
        ):
            wrong_type = copy.deepcopy(baseline)
            wrong_type[field] = Bomb()
            shallow_cases.append((f"{field}-wrong-type", wrong_type))
        overwide_registry = copy.deepcopy(baseline)
        overwide_registry["projection_class_registry"] = [Bomb()] * 13
        shallow_cases.append(("registry-overwide", overwide_registry))
        overwide_blockers = copy.deepcopy(baseline)
        overwide_blockers["remaining_blockers"] = [Bomb()] * 9
        shallow_cases.append(("blockers-overwide", overwide_blockers))
        overwide_missing = copy.deepcopy(baseline)
        overwide_missing["missing_projection_class_ledger"] = [Bomb()]
        shallow_cases.append(("missing-overwide", overwide_missing))
        for label, candidate in shallow_cases:
            for module in (package, independent):
                with self.subTest(label=label, module=module.__name__), self.assertRaises(
                    ValueError
                ):
                    module._preflight_inventory_shape(candidate)

        mutations = []
        order = copy.deepcopy(baseline)
        order["orders"]["minimum_projection_classes"][0] = "x" * 100_000
        mutations.append(order)
        validation = copy.deepcopy(baseline)
        validation["derivation_receipts"][0]["validation"][
            "upstream_owner_validation_result"
        ] = [True] * 100_000
        mutations.append(validation)
        predecessor = copy.deepcopy(baseline)
        predecessor["predecessor_inventory_binding"]["artifact_kind"] = (
            "x" * 100_000
        )
        mutations.append(predecessor)
        registry = copy.deepcopy(baseline)
        registry["projection_class_registry"][0]["coverage_status"] = "x" * 100_000
        mutations.append(registry)

        for index, candidate in enumerate(mutations):
            for module in (package, independent):
                with self.subTest(index=index, module=module.__name__), self.assertRaises(
                    ValueError
                ):
                    module._preflight_inventory_shape(candidate)

        foreign_material = {f"field-{index}": None for index in range(10_000)}
        for module in (package, independent):
            with self.subTest(module=module.__name__), self.assertRaises(ValueError):
                module._normalize_material(foreign_material)

    def test_parameter_cell_usage_requires_exact_inactive_partition(self):
        active = {f"active-{index:03d}" for index in range(354)}
        baseline = {
            "assignment_cell_keys": set(active),
            "cell_keys": set(active) | set(EXPECTED_UNUSED_PARAMETER_CELL_KEYS),
        }
        self.assertIsNone(independent._validate_parameter_cell_usage(baseline))

        foreign = copy.deepcopy(baseline)
        foreign["assignment_cell_keys"].add("foreign-cell")
        missing_active = copy.deepcopy(baseline)
        missing_active["assignment_cell_keys"].remove("active-000")
        consumed_inactive = copy.deepcopy(baseline)
        consumed_inactive["assignment_cell_keys"].add(
            next(iter(EXPECTED_UNUSED_PARAMETER_CELL_KEYS))
        )
        for label, candidate in (
            ("foreign", foreign),
            ("missing-active", missing_active),
            ("consumed-inactive", consumed_inactive),
        ):
            with self.subTest(label=label), self.assertRaises(
                independent.PersonaV2SemanticProjectionCompleteInventoryValidationError
            ):
                independent._validate_parameter_cell_usage(candidate)


class SemanticProjectionCompleteInventoryLongAll253Test(unittest.TestCase):
    """One shared full build, exact two-replay acceptance, and metadata tamper."""

    inventory = None

    @classmethod
    def _ensure_inventory(cls):
        if cls.inventory is None:
            cls.inventory = package.build_semantic_projection_complete_inventory()

    def test_exact_inventory_shape_counts_order_completion_and_non_authority(self):
        self._ensure_inventory()
        value = self.inventory
        raw = package.canonical_json_bytes(value)
        self.assertEqual(len(raw), EXPECTED_SUITE_CANONICAL_BYTES)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), EXPECTED_SUITE_SHA256)
        self.assertEqual(set(value), package.TOP_LEVEL_FIELDS)
        self.assertEqual(value["artifact_schema"], package.SUITE_SCHEMA)
        self.assertEqual(set(value["authority"]), EXPECTED_AUTHORITY_FIELDS)
        self.assertTrue(all(item is False for item in value["authority"].values()))
        self.assertIs(value["g0_contract_frozen"], False)
        self.assertEqual(value["missing_projection_class_ledger"], [])
        self.assertEqual(
            value["completion_claims"],
            {
                "all_253_receipts_bound": True,
                "corpus_semantic_namespace_issued": False,
                "future_source_id_namespace_eligible": True,
                "local_twelve_class_derivation_complete": True,
                "minimum_projection_inventory_complete": True,
                "query_semantics_absence_proved": True,
                "semantic_payload_projection_bound": True,
            },
        )
        receipts = value["derivation_receipts"]
        self.assertEqual(len(receipts), 253)
        self.assertEqual(
            Counter(row["projection_class_id"] for row in receipts),
            Counter(EXPECTED_RECEIPT_COUNTS),
        )
        self.assertEqual(
            [row["projection_class_id"] for row in receipts],
            [
                class_id
                for class_id in EXPECTED_CLASS_ORDER
                for _ in range(EXPECTED_RECEIPT_COUNTS[class_id])
            ],
        )
        self.assertEqual(value["summary"]["json_projection_body_count"], 67)
        self.assertEqual(value["summary"]["jsonl_projection_body_count"], 186)
        self.assertEqual(
            value["summary"]["cumulative_external_projection_bytes"],
            EXPECTED_EXTERNAL_BODY_BYTES,
        )

    def test_independent_all_253_acceptance_and_exact_two_replay_order(self):
        self._ensure_inventory()
        calls = []

        def recording_provider(receipt):
            calls.append(copy.deepcopy(receipt))
            return package.projection_body_provider(receipt)

        self.assertIs(
            independent.validate_semantic_projection_complete_inventory(
                self.inventory,
                projection_body_provider=recording_provider,
            ),
            True,
        )
        expected = [
            copy.deepcopy(receipt)
            for receipt in self.inventory["derivation_receipts"]
            for _ in range(2)
        ]
        self.assertEqual(calls, expected)

    def test_metadata_tamper_stops_before_provider(self):
        self._ensure_inventory()
        target = copy.deepcopy(self.inventory)
        target["completion_claims"]["corpus_semantic_namespace_issued"] = True
        calls = []

        def forbidden(_receipt):
            calls.append(True)
            raise AssertionError("provider must not run")

        with self.assertRaises(
            independent.PersonaV2SemanticProjectionCompleteInventoryValidationError
        ):
            independent.validate_semantic_projection_complete_inventory(
                target,
                projection_body_provider=forbidden,
            )
        self.assertEqual(calls, [])

    def test_provider_failure_and_body_boundaries_stop_at_exact_call_count(self):
        self._ensure_inventory()
        receipt = self.inventory["derivation_receipts"][0]
        correct_body = package.projection_body_provider(receipt)

        cases = (
            ("first-exception", lambda _call: (_ for _ in ()).throw(RuntimeError())),
            (
                "replay-exception",
                lambda call: correct_body
                if call == 1
                else (_ for _ in ()).throw(RuntimeError()),
            ),
            ("wrong-type", lambda _call: bytearray(correct_body)),
            ("bit-flip", lambda _call: bytes([correct_body[0] ^ 1]) + correct_body[1:]),
            (
                "oversize",
                lambda _call: b"x" * (independent.MAX_JSON_BODY_BYTES + 1),
            ),
        )
        for label, result in cases:
            calls = []

            def provider(_receipt, result=result):
                calls.append(True)
                return result(len(calls))

            with self.subTest(label=label), mock.patch.object(
                independent,
                "_reauthenticate_all_owners",
                return_value=True,
            ) as postflight, self.assertRaises(
                independent.PersonaV2SemanticProjectionCompleteInventoryValidationError
            ):
                independent.validate_semantic_projection_complete_inventory(
                    self.inventory,
                    projection_body_provider=provider,
                )
            self.assertEqual(len(calls), 2 if label == "replay-exception" else 1)
            self.assertEqual(postflight.call_count, 2)

    def test_receipt_and_caller_target_mutation_fail_closed(self):
        self._ensure_inventory()
        receipt = self.inventory["derivation_receipts"][0]
        for field, value in (
            ("receipt_id", "foreign-receipt"),
            (
                "projector",
                {"projector_id": "foreign-projector", "projector_version": 1},
            ),
            (
                "projection_pin",
                {
                    **receipt["projection_pin"],
                    "sha256": "0" * 64,
                },
            ),
        ):
            tampered = copy.deepcopy(receipt)
            tampered[field] = value
            with self.subTest(field=field), self.assertRaises(
                package.PersonaV2SemanticProjectionCompleteInventoryError
            ):
                package.projection_body_provider(tampered)

        calls = []
        original_status = self.inventory["hypothesis_status"]

        def mutating_provider(selected):
            calls.append(True)
            self.inventory["hypothesis_status"] = "mutated-during-provider"
            return package.projection_body_provider(selected)

        try:
            with mock.patch.object(
                independent,
                "_reauthenticate_all_owners",
                return_value=True,
            ) as postflight, self.assertRaises(
                independent.PersonaV2SemanticProjectionCompleteInventoryValidationError
            ):
                independent.validate_semantic_projection_complete_inventory(
                    self.inventory,
                    projection_body_provider=mutating_provider,
                )
            self.assertEqual(calls, [True])
            self.assertEqual(postflight.call_count, 2)
        finally:
            self.inventory["hypothesis_status"] = original_status


class SemanticProjectionCompleteInventoryLongColdHashSeedTest(unittest.TestCase):
    """Two isolated producer cold builds with exact deterministic measurements."""

    def test_two_hashseeds_are_canonical_and_resource_bounded(self):
        script = r'''
import collections
import hashlib
import json
import resource
import sys
import time

from eval import persona_v2_semantic_projection_complete_inventory as package

started = time.monotonic()
inventory = package.build_semantic_projection_complete_inventory()
suite_raw = package.canonical_json_bytes(inventory)
class_counts = collections.Counter()
class_bytes = collections.Counter()
class_maximum_body_bytes = collections.defaultdict(int)
class_row_counts = collections.Counter()
class_maximum_row_bytes = collections.defaultdict(int)
ordered_projection_pins = []

for receipt in inventory["derivation_receipts"]:
    body = package.projection_body_provider(receipt)
    class_id = receipt["projection_class_id"]
    pin = receipt["projection_pin"]
    assert type(body) is bytes
    assert len(body) == pin["canonical_bytes"]
    assert hashlib.sha256(body).hexdigest() == pin["sha256"]
    class_counts[class_id] += 1
    class_bytes[class_id] += len(body)
    class_maximum_body_bytes[class_id] = max(
        class_maximum_body_bytes[class_id], len(body)
    )
    if pin["body_framing"] == "canonical-jsonl-lf":
        rows = body.splitlines(keepends=True)
        class_row_counts[class_id] += len(rows)
        class_maximum_row_bytes[class_id] = max(
            class_maximum_row_bytes[class_id], max(map(len, rows))
        )
    ordered_projection_pins.append({
        "receipt_id": receipt["receipt_id"],
        "canonical_bytes": pin["canonical_bytes"],
        "sha256": pin["sha256"],
    })

pin_raw = json.dumps(
    ordered_projection_pins,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")
maximum_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
if sys.platform != "darwin":
    maximum_rss *= 1024
print(json.dumps({
    "class_bytes": dict(sorted(class_bytes.items())),
    "class_counts": dict(sorted(class_counts.items())),
    "class_maximum_body_bytes": dict(sorted(class_maximum_body_bytes.items())),
    "class_maximum_row_bytes": dict(sorted(class_maximum_row_bytes.items())),
    "class_row_counts": dict(sorted(class_row_counts.items())),
    "elapsed_seconds": time.monotonic() - started,
    "external_body_bytes": sum(class_bytes.values()),
    "maximum_rss_bytes": maximum_rss,
    "ordered_projection_pins_sha256": hashlib.sha256(pin_raw).hexdigest(),
    "suite_bytes": len(suite_raw),
    "suite_sha256": hashlib.sha256(suite_raw).hexdigest(),
}, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
'''
        measurements = []
        for seed in ("0", "1"):
            environment = os.environ.copy()
            environment.update(
                {
                    "LANG": "C",
                    "LC_ALL": "C",
                    "PYTHONHASHSEED": seed,
                    "TZ": "UTC",
                }
            )
            completed = subprocess.run(
                [sys.executable, "-c", script],
                cwd=os.path.dirname(os.path.dirname(__file__)),
                env=environment,
                capture_output=True,
                check=True,
                text=True,
                timeout=MAX_COLD_BUILD_SECONDS,
            )
            measurement = json.loads(completed.stdout.splitlines()[-1])
            self.assertLessEqual(
                measurement["elapsed_seconds"], MAX_COLD_BUILD_SECONDS
            )
            self.assertLessEqual(
                measurement["maximum_rss_bytes"], MAX_COLD_BUILD_RSS_BYTES
            )
            self.assertEqual(measurement["class_counts"], EXPECTED_RECEIPT_COUNTS)
            self.assertEqual(sum(measurement["class_counts"].values()), 253)
            self.assertEqual(measurement["class_bytes"], EXPECTED_CLASS_BYTES)
            self.assertEqual(
                measurement["class_maximum_body_bytes"],
                EXPECTED_CLASS_MAXIMUM_BODY_BYTES,
            )
            self.assertEqual(
                measurement["class_row_counts"], EXPECTED_CLASS_ROW_COUNTS
            )
            self.assertEqual(
                measurement["class_maximum_row_bytes"],
                EXPECTED_CLASS_MAXIMUM_ROW_BYTES,
            )
            self.assertEqual(
                measurement["external_body_bytes"], EXPECTED_EXTERNAL_BODY_BYTES
            )
            self.assertEqual(
                measurement["ordered_projection_pins_sha256"],
                EXPECTED_ORDERED_PROJECTION_PINS_SHA256,
            )
            self.assertEqual(
                measurement["suite_bytes"], EXPECTED_SUITE_CANONICAL_BYTES
            )
            self.assertEqual(measurement["suite_sha256"], EXPECTED_SUITE_SHA256)
            measurements.append(measurement)
        stable_keys = {
            key
            for key in measurements[0]
            if key not in {"elapsed_seconds", "maximum_rss_bytes"}
        }
        self.assertEqual(
            {key: measurements[0][key] for key in stable_keys},
            {key: measurements[1][key] for key in stable_keys},
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
