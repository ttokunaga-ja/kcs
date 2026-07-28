"""Gates for the partial semantic-projection derivation inventory.

The artifact under test binds 113 independently replayable external bodies,
but deliberately covers only three of the twelve projection classes required
for the future corpus semantic namespace.  The inexpensive public-contract
checks stay in the first class.  Full 113-body validation and cold hash-seed
rebuilds have explicit ``Long`` class names so CI can budget them separately
without weakening the default unittest module.
"""

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

from eval import persona_v2_contract as envelope
from eval import persona_v2_semantic_projection_derivation_inventory as package
from eval import persona_v2_source_semantic_membership_package as source_semantic
from eval import (
    persona_v2_semantic_projection_derivation_inventory_validator as independent,
)


EXPECTED_PROJECTION_CLASS_ORDER = (
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
EXPECTED_COVERED_CLASS_ORDER = (
    "base-source-content-context",
    "effective-source-membership",
    "query-independent-lifecycle-fact-rendition-rules",
)
EXPECTED_MISSING_CLASS_ORDER = tuple(
    class_id
    for class_id in EXPECTED_PROJECTION_CLASS_ORDER
    if class_id not in EXPECTED_COVERED_CLASS_ORDER
)
EXPECTED_RECEIPT_COUNTS = {
    "base-source-content-context": 73,
    "effective-source-membership": 20,
    "query-independent-lifecycle-fact-rendition-rules": 20,
}
EXPECTED_RECEIPT_COUNT = 113
EXPECTED_BASE_ROW_COUNT = 203_000
EXPECTED_BASE_BODY_BYTES = 121_020_941
EXPECTED_BASE_MAXIMUM_ROW_BYTES_INCLUDING_LF = 633
EXPECTED_SUITE_CANONICAL_BYTES = 293_285
EXPECTED_SUITE_SHA256 = (
    "e06e66901e24fda63a097dd2a5625cc562ea80008e8e6f5b961ce3c7a792dcdb"
)
EXPECTED_CUMULATIVE_PROJECTION_BYTES = 128_144_915
EXPECTED_ORDERED_PROJECTION_PINS_SHA256 = (
    "a909168390dbc7426d5ac21a36a5720c378e0d3281f852dcd90e40344e8cb83d"
)
EXPECTED_CLASS_MAXIMUM_BODY_BYTES = {
    "base-source-content-context": 2_484_590,
    "effective-source-membership": 103_840,
    "query-independent-lifecycle-fact-rendition-rules": 256_790,
}

EXPECTED_TOP_LEVEL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "canonical_limits",
        "completion_claims",
        "derivation_receipts",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
        "hypothesis_status",
        "missing_projection_class_ledger",
        "orders",
        "projection_class_registry",
        "remaining_blockers",
        "summary",
        "upstream_suite_bindings",
    }
)
EXPECTED_RECEIPT_FIELDS = frozenset(
    {
        "coordinates",
        "direct_body_pins",
        "full_owner_pins",
        "projection_class_id",
        "projection_pin",
        "projector",
        "receipt_id",
        "row_kind",
        "row_schema",
        "validation",
    }
)
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

MAX_COLD_BUILD_SECONDS = 120 * 60
MAX_COLD_BUILD_RSS_BYTES = 768 * 2**20


def _canonical(value):
    return package.canonical_json_bytes(value)


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


def _receipt_by_class(inventory):
    result = {}
    for receipt in inventory["derivation_receipts"]:
        result.setdefault(receipt["projection_class_id"], []).append(receipt)
    return result


def _imports_producer_module(source):
    target = "persona_v2_semantic_projection_derivation_inventory"
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


class SemanticProjectionDerivationInventoryContractTest(unittest.TestCase):
    """Light public schema, API, cap, and metadata-first gates."""

    def test_public_api_schema_classes_counts_caps_and_independence(self):
        for name in (
            "build_semantic_projection_derivation_inventory",
            "canonical_json_bytes",
            "projection_body_provider",
            "semantic_projection_derivation_inventory_sha256",
            "validate_semantic_projection_derivation_inventory",
        ):
            self.assertTrue(callable(getattr(package, name, None)), name)
        self.assertTrue(
            callable(independent.validate_semantic_projection_derivation_inventory)
        )

        self.assertEqual(
            package.SUITE_SCHEMA,
            "kio.persona.pc-semantic-projection-derivation-inventory/v1",
        )
        self.assertEqual(
            package.RECEIPT_SCHEMA,
            "kio.persona.pc-semantic-projection-derivation-receipt/v1",
        )
        self.assertEqual(
            tuple(package.PROJECTION_CLASS_ORDER), EXPECTED_PROJECTION_CLASS_ORDER
        )
        self.assertEqual(
            tuple(package.COVERED_CLASS_ORDER), EXPECTED_COVERED_CLASS_ORDER
        )
        self.assertEqual(
            tuple(package.MISSING_CLASS_ORDER), EXPECTED_MISSING_CLASS_ORDER
        )
        self.assertEqual(package.EXPECTED_RECEIPT_COUNTS, EXPECTED_RECEIPT_COUNTS)
        self.assertEqual(sum(package.EXPECTED_RECEIPT_COUNTS.values()), 113)
        self.assertEqual(
            package.EXPECTED_SUITE_CANONICAL_BYTES,
            EXPECTED_SUITE_CANONICAL_BYTES,
        )
        self.assertEqual(package.EXPECTED_SUITE_SHA256, EXPECTED_SUITE_SHA256)
        self.assertEqual(
            package.EXPECTED_CUMULATIVE_PROJECTION_BYTES,
            EXPECTED_CUMULATIVE_PROJECTION_BYTES,
        )
        self.assertEqual(
            package.EXPECTED_ORDERED_PROJECTION_PINS_SHA256,
            EXPECTED_ORDERED_PROJECTION_PINS_SHA256,
        )
        self.assertEqual(
            package.EXPECTED_CLASS_MAXIMUM_BODY_BYTES,
            EXPECTED_CLASS_MAXIMUM_BODY_BYTES,
        )
        self.assertEqual(
            independent.EXPECTED_SUITE_CANONICAL_BYTES,
            EXPECTED_SUITE_CANONICAL_BYTES,
        )
        self.assertEqual(
            independent.EXPECTED_SUITE_SHA256,
            EXPECTED_SUITE_SHA256,
        )
        self.assertEqual(
            independent.EXPECTED_CUMULATIVE_EXTERNAL_BODY_BYTES,
            EXPECTED_CUMULATIVE_PROJECTION_BYTES,
        )
        self.assertEqual(
            independent.EXPECTED_ORDERED_PROJECTION_PINS_SHA256,
            EXPECTED_ORDERED_PROJECTION_PINS_SHA256,
        )
        self.assertEqual(
            dict(independent._EXPECTED_CLASS_MAXIMUM_BODY_BYTES),
            EXPECTED_CLASS_MAXIMUM_BODY_BYTES,
        )

        self.assertEqual(package.MAX_SUITE_BYTES, 1 * 2**20)
        self.assertEqual(package.MAX_RECEIPT_COUNT, 113)
        self.assertEqual(package.MAX_JSONL_PROJECTION_BYTES, 4 * 2**20)
        self.assertEqual(package.MAX_JSON_PROJECTION_BYTES, 384 * 2**10)
        self.assertEqual(package.TARGET_JSON_PROJECTION_BYTES, 256 * 2**10)
        self.assertEqual(package.MAX_JSONL_ROWS, 4_096)
        self.assertEqual(package.MAX_JSONL_ROW_BYTES_INCLUDING_LF, 768)
        self.assertEqual(package.MAX_CUMULATIVE_PROJECTION_BYTES, 144 * 2**20)

        self.assertEqual(package.TOP_LEVEL_FIELDS, EXPECTED_TOP_LEVEL_FIELDS)
        self.assertEqual(package.RECEIPT_FIELDS, EXPECTED_RECEIPT_FIELDS)
        self.assertEqual(independent.TOP_LEVEL_FIELDS, EXPECTED_TOP_LEVEL_FIELDS)
        self.assertEqual(independent.RECEIPT_FIELDS, EXPECTED_RECEIPT_FIELDS)
        self.assertEqual(package.AUTHORITY_FIELDS, EXPECTED_AUTHORITY_FIELDS)
        self.assertEqual(independent.AUTHORITY_FIELDS, EXPECTED_AUTHORITY_FIELDS)
        self.assertEqual(
            tuple(independent.PROJECTION_CLASS_ORDER),
            EXPECTED_PROJECTION_CLASS_ORDER,
        )

        validator_source = inspect.getsource(independent)
        self.assertFalse(
            _imports_producer_module(validator_source),
            "independent validator imported the sibling producer module",
        )

    def test_invalid_opening_metadata_stops_before_body_provider(self):
        calls = []

        def forbidden(_receipt):
            calls.append(True)
            raise AssertionError("provider must not run for invalid metadata")

        malformed_values = (
            {},
            {"artifact_schema": package.SUITE_SCHEMA},
            {field: None for field in EXPECTED_TOP_LEVEL_FIELDS},
        )
        for value in malformed_values:
            with (
                self.subTest(fields=set(value)),
                self.assertRaises(
                    independent.PersonaV2SemanticProjectionDerivationInventoryValidationError
                ),
            ):
                independent.validate_semantic_projection_derivation_inventory(
                    value,
                    projection_body_provider=forbidden,
                )
        self.assertEqual(calls, [])

    def test_provider_boundary_rejects_invalid_receipt_without_upstream_reads(self):
        for value in (None, {}, {field: None for field in EXPECTED_RECEIPT_FIELDS}):
            with (
                self.subTest(value_type=type(value).__name__),
                self.assertRaises(package.PersonaV2SemanticProjectionDerivationInventoryError),
            ):
                package.projection_body_provider(value)


class SemanticProjectionDerivationInventoryLongAll113Test(unittest.TestCase):
    """Long shared full-inventory, all-body, tamper, and TOCTOU gates."""

    inventory = None
    @classmethod
    def _ensure_inventory(cls):
        if cls.inventory is not None:
            return
        cls.inventory = package.build_semantic_projection_derivation_inventory()

    def _must_not_run(self, _receipt):
        raise AssertionError("provider ran before invalid metadata was rejected")

    def test_exact_inventory_shape_counts_order_and_negative_authority(self):
        self._ensure_inventory()
        inventory = self.inventory
        raw = _canonical(inventory)
        self.assertEqual(len(raw), EXPECTED_SUITE_CANONICAL_BYTES)
        self.assertEqual(_sha256(raw), EXPECTED_SUITE_SHA256)
        self.assertEqual(set(inventory), EXPECTED_TOP_LEVEL_FIELDS)
        self.assertEqual(inventory["artifact_schema"], package.SUITE_SCHEMA)
        self.assertEqual(inventory["artifact_kind"], package.SUITE_KIND)
        self.assertEqual(inventory["artifact_schema_version"], 1)
        self.assertEqual(inventory["fixture_id"], envelope.FIXTURE_ID)
        self.assertEqual(
            inventory["fixture_schema_version"], envelope.FIXTURE_SCHEMA_VERSION
        )
        self.assertIs(inventory["g0_contract_frozen"], False)

        self.assertEqual(set(inventory["authority"]), EXPECTED_AUTHORITY_FIELDS)
        self.assertTrue(
            all(value is False for value in inventory["authority"].values())
        )
        for field in (
            "authorizes_corpus_semantic_namespace",
            "authorizes_g0_freeze",
            "authorizes_namespace_completion",
            "authorizes_physical_write",
            "authorizes_query_rendering",
            "authorizes_renderer_execution",
            "authorizes_solver_execution",
            "authorizes_source_identity_derivation",
            "corpus_semantic_namespace_available",
            "source_identity_namespace_authoritative",
        ):
            self.assertIs(inventory["authority"][field], False, field)

        completion = inventory["completion_claims"]
        self.assertEqual(
            completion,
            {
                "all_113_receipts_bound": True,
                "corpus_semantic_namespace_issued": False,
                "future_source_id_namespace_eligible": False,
                "local_three_class_derivation_complete": True,
                "minimum_projection_inventory_complete": False,
                "query_semantics_absence_proved": False,
                "semantic_payload_projection_bound": False,
            },
        )
        self.assertEqual(
            inventory["hypothesis_status"],
            "authored-benchmark-projection-derivation-evidence-not-observed-user-data",
        )
        self.assertEqual(
            inventory["canonical_limits"],
            {
                "external_projection_bodies_embedded": False,
                "max_cumulative_external_projection_bytes": 144 * 2**20,
                "max_json_projection_bytes": 384 * 2**10,
                "max_jsonl_projection_bytes": 4 * 2**20,
                "max_jsonl_projection_row_bytes_including_lf": 768,
                "max_jsonl_projection_rows": 4_096,
                "max_nesting_depth": 64,
                "max_receipt_count": 113,
                "max_string_bytes": 4_096,
                "max_suite_bytes": 1 * 2**20,
                "self_hash_embedded": False,
                "target_json_projection_bytes": 256 * 2**10,
                "unicode_normalization": "NFC",
            },
        )
        self.assertEqual(
            inventory["upstream_suite_bindings"],
            [
                package.SOURCE_SEMANTIC_SUITE_PIN,
                package.EFFECTIVE_SUITE_PIN,
                package.MATCHED_SUITE_PIN,
            ],
        )
        self.assertEqual(
            inventory["remaining_blockers"],
            [
                "nine-minimum-semantic-projection-classes-not-derived",
                "complete-independent-projection-derivation-validation-not-yet-authoritative",
                "corpus-semantic-namespace-not-issued",
                "corpus-input-closure-and-blocker-resolution-ledger-not-complete",
                "joint-solver-solution-proof-and-final-source-plan-not-built",
                "compiled-history-physical-materialization-capacity-kio-and-g0-not-observed",
            ],
        )

        self.assertEqual(
            inventory["orders"]["minimum_projection_classes"],
            list(EXPECTED_PROJECTION_CLASS_ORDER),
        )
        self.assertEqual(
            inventory["orders"]["covered_projection_classes"],
            list(EXPECTED_COVERED_CLASS_ORDER),
        )
        self.assertEqual(inventory["orders"]["persona"], list(envelope.PERSONA_IDS))

        registry = inventory["projection_class_registry"]
        self.assertEqual(len(registry), 12)
        self.assertEqual(
            [row["projection_class_id"] for row in registry],
            list(EXPECTED_PROJECTION_CLASS_ORDER),
        )
        self.assertTrue(
            all(set(row) == independent.REGISTRY_FIELDS for row in registry)
        )
        for ordinal, row in enumerate(registry, start=1):
            self.assertEqual(row["inventory_ordinal"], ordinal)
            expected_count = EXPECTED_RECEIPT_COUNTS.get(
                row["projection_class_id"], 0
            )
            self.assertEqual(row["derivation_receipt_count"], expected_count)
            self.assertEqual(
                row["coverage_status"],
                (
                    "covered-local-derivation"
                    if expected_count
                    else "missing-required-projection"
                ),
            )

        missing = inventory["missing_projection_class_ledger"]
        self.assertEqual(len(missing), 9)
        self.assertEqual(
            [row["projection_class_id"] for row in missing],
            list(EXPECTED_MISSING_CLASS_ORDER),
        )
        self.assertTrue(
            all(set(row) == independent.MISSING_LEDGER_FIELDS for row in missing)
        )
        self.assertTrue(
            all(
                row["required_for_minimum_inventory"] is True
                and row["status"] == "active-g0"
                and row["blocker_id"]
                == f"missing-semantic-projection-{row['projection_class_id']}"
                for row in missing
            )
        )

        receipts = inventory["derivation_receipts"]
        self.assertEqual(len(receipts), EXPECTED_RECEIPT_COUNT)
        self.assertEqual(
            Counter(row["projection_class_id"] for row in receipts),
            Counter(EXPECTED_RECEIPT_COUNTS),
        )
        self.assertEqual(
            [row["projection_class_id"] for row in receipts],
            ["base-source-content-context"] * 73
            + ["effective-source-membership"] * 20
            + ["query-independent-lifecycle-fact-rendition-rules"] * 20,
        )
        receipt_ids = [row["receipt_id"] for row in receipts]
        self.assertEqual(len(set(receipt_ids)), EXPECTED_RECEIPT_COUNT)
        self.assertTrue(all(set(row) == EXPECTED_RECEIPT_FIELDS for row in receipts))
        self.assertTrue(
            all(
                set(row["projection_pin"]) == independent.GENERIC_PIN_FIELDS
                and set(row["projector"]) == independent.PROJECTOR_FIELDS
                and row["projector"]["projector_version"] == 1
                and set(row["validation"]) == independent.VALIDATION_FIELDS
                and all(value is True for value in row["validation"].values())
                for row in receipts
            )
        )
        self.assertTrue(
            all(
                set(pin) == independent.FULL_OWNER_PIN_FIELDS
                for receipt in receipts
                for pin in receipt["full_owner_pins"]
            )
        )
        self.assertTrue(
            all(
                set(pin) == independent.DIRECT_PIN_FIELDS
                for receipt in receipts
                for pin in receipt["direct_body_pins"]
            )
        )

        by_class = _receipt_by_class(inventory)
        base = by_class["base-source-content-context"]
        self.assertEqual(
            set().union(*(set(row["coordinates"]) for row in base)),
            {"origin", "persona_id", "source_shard_id", "source_shard_ordinal"},
        )
        self.assertTrue(
            all(
                set(row["coordinates"])
                == {"origin", "persona_id", "source_shard_id", "source_shard_ordinal"}
                for row in base
            )
        )
        self.assertEqual(
            {row["coordinates"]["persona_id"] for row in base},
            set(envelope.PERSONA_IDS),
        )
        self.assertEqual(
            {row["coordinates"]["origin"] for row in base},
            {"pilot", "full-residual"},
        )
        for class_id in EXPECTED_COVERED_CLASS_ORDER[1:]:
            rows = by_class[class_id]
            self.assertEqual(
                [row["coordinates"] for row in rows],
                [{"persona_id": persona_id} for persona_id in envelope.PERSONA_IDS],
            )

        expected_chain_shapes = {
            "base-source-content-context": (
                2,
                3,
                {
                    "full-origin-owner-pin",
                    "full-suite-owner-pin",
                },
                {
                    "compact-origin-owner-body",
                    "matching-shard-total-projection-receipt",
                    "suite-origin-binding-row",
                },
            ),
            "effective-source-membership": (
                1,
                1,
                {"full-suite-and-direct-projection-owner-pin"},
                {"suite-direct-projection-binding-row"},
            ),
            "query-independent-lifecycle-fact-rendition-rules": (
                2,
                3,
                {
                    "full-persona-projection-and-event-receipt-owner-pin",
                    "full-suite-containing-persona-binding-pin",
                },
                {
                    "persona-event-receipt-row",
                    "receipt-authenticated-event-jsonl-body",
                    "suite-persona-binding-row",
                },
            ),
        }
        for class_id, (owner_count, direct_count, owner_roles, direct_roles) in (
            expected_chain_shapes.items()
        ):
            for receipt in by_class[class_id]:
                self.assertEqual(len(receipt["full_owner_pins"]), owner_count)
                self.assertEqual(len(receipt["direct_body_pins"]), direct_count)
                self.assertEqual(
                    {row["owner_role"] for row in receipt["full_owner_pins"]},
                    owner_roles,
                )
                self.assertEqual(
                    {row["direct_pin_role"] for row in receipt["direct_body_pins"]},
                    direct_roles,
                )

        summary = inventory["summary"]
        self.assertEqual(summary["derivation_receipt_count"], 113)
        self.assertEqual(summary["external_projection_body_count"], 113)
        self.assertEqual(summary["jsonl_projection_body_count"], 73)
        self.assertEqual(summary["json_projection_body_count"], 40)
        self.assertEqual(summary["covered_projection_class_count"], 3)
        self.assertEqual(summary["missing_projection_class_count"], 9)
        self.assertEqual(summary["minimum_projection_class_count"], 12)
        self.assertEqual(summary["persona_count"], 20)
        self.assertEqual(
            summary["receipt_counts_by_projection_class"], EXPECTED_RECEIPT_COUNTS
        )
        self.assertEqual(
            summary["cumulative_external_projection_bytes"],
            sum(row["projection_pin"]["canonical_bytes"] for row in receipts),
        )
        self.assertEqual(
            summary["cumulative_external_projection_bytes"],
            EXPECTED_CUMULATIVE_PROJECTION_BYTES,
        )
        self.assertLessEqual(
            summary["cumulative_external_projection_bytes"],
            package.MAX_CUMULATIVE_PROJECTION_BYTES,
        )

    def test_builds_are_detached_and_sha_uses_authenticated_opening_bytes(self):
        self._ensure_inventory()
        canonical = copy.deepcopy(self.inventory)
        rebuilt = package.build_semantic_projection_derivation_inventory()
        rebuilt["derivation_receipts"][0]["coordinates"]["persona_id"] = "p99"
        self.assertEqual(
            package.build_semantic_projection_derivation_inventory(), canonical
        )

        caller_owned = copy.deepcopy(canonical)
        opening_raw = _canonical(caller_owned)

        def mutate_after_snapshot(snapshot, projection_body_provider=None):
            self.assertIsNot(snapshot, caller_owned)
            self.assertEqual(_canonical(snapshot), opening_raw)
            caller_owned["summary"]["derivation_receipt_count"] = 0
            return True

        with mock.patch.object(
            package,
            "validate_semantic_projection_derivation_inventory",
            side_effect=mutate_after_snapshot,
        ), self.assertRaises(package.PersonaV2SemanticProjectionDerivationInventoryError):
            package.semantic_projection_derivation_inventory_sha256(caller_owned)

        stable = copy.deepcopy(canonical)
        stable_raw = _canonical(stable)
        with mock.patch.object(
            package,
            "validate_semantic_projection_derivation_inventory",
            return_value=True,
        ):
            digest = package.semantic_projection_derivation_inventory_sha256(stable)
        self.assertEqual(digest, _sha256(stable_raw))

    def test_producer_validation_delegates_detached_and_requires_exact_true(self):
        self._ensure_inventory()
        target = copy.deepcopy(self.inventory)
        provider = lambda _receipt: b"unused"

        with mock.patch.object(
            independent,
            "validate_semantic_projection_derivation_inventory",
            return_value=True,
        ) as validate:
            self.assertIs(
                package.validate_semantic_projection_derivation_inventory(
                    target,
                    projection_body_provider=provider,
                ),
                True,
            )
        validate.assert_called_once()
        delegated, = validate.call_args.args
        self.assertIsNot(delegated, target)
        self.assertEqual(delegated, target)
        self.assertIs(validate.call_args.kwargs["projection_body_provider"], provider)

        for invalid_result in (False, None, 1):
            with (
                self.subTest(independent_result=invalid_result),
                mock.patch.object(
                    independent,
                    "validate_semantic_projection_derivation_inventory",
                    return_value=invalid_result,
                ),
                self.assertRaises(
                    package.PersonaV2SemanticProjectionDerivationInventoryError
                ),
            ):
                package.validate_semantic_projection_derivation_inventory(
                    target,
                    projection_body_provider=provider,
                )

        with (
            mock.patch.object(package, "_independent_validator", return_value=None),
            self.assertRaises(package.PersonaV2SemanticProjectionDerivationInventoryError),
        ):
            package.validate_semantic_projection_derivation_inventory(
                target,
                projection_body_provider=provider,
            )

        with self.assertRaises(package.PersonaV2SemanticProjectionDerivationInventoryError):
            package.require_complete_semantic_projection_inventory()

    def test_representative_body_pins_and_canonical_caps(self):
        self._ensure_inventory()
        by_class = _receipt_by_class(self.inventory)
        representatives = [rows[0] for rows in by_class.values()]
        for receipt in representatives:
            with self.subTest(class_id=receipt["projection_class_id"]):
                body = package.projection_body_provider(receipt)
                pin = receipt["projection_pin"]
                self.assertIs(type(body), bytes)
                self.assertEqual(len(body), pin["canonical_bytes"])
                self.assertEqual(_sha256(body), pin["sha256"])
                if receipt["projection_class_id"] == "base-source-content-context":
                    self.assertTrue(body.endswith(b"\n"))
                    rows = body.splitlines(keepends=True)
                    self.assertLessEqual(len(body), package.MAX_JSONL_PROJECTION_BYTES)
                    self.assertLessEqual(len(rows), package.MAX_JSONL_ROWS)
                    self.assertLessEqual(
                        max(map(len, rows)),
                        package.MAX_JSONL_ROW_BYTES_INCLUDING_LF,
                    )
                else:
                    self.assertLessEqual(len(body), package.MAX_JSON_PROJECTION_BYTES)
                    self.assertLessEqual(len(body), package.TARGET_JSON_PROJECTION_BYTES)
                    self.assertEqual(
                        body,
                        json.dumps(
                            json.loads(body),
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("utf-8"),
                    )

        effective_receipt = by_class["effective-source-membership"][0]
        self.assertEqual(effective_receipt["coordinates"], {"persona_id": "p01"})
        self.assertEqual(
            effective_receipt["projection_pin"]["canonical_bytes"], 103_439
        )
        self.assertEqual(
            effective_receipt["projection_pin"]["sha256"],
            "d620a63b9762cf6119d795845c5b1533207ced29ae97fbb6ab3765a966d07f5e",
        )

    def test_public_body_provider_requires_the_exact_inventory_receipt(self):
        self._ensure_inventory()
        by_class = _receipt_by_class(self.inventory)
        effective_receipt = by_class["effective-source-membership"][0]
        forged = copy.deepcopy(self.inventory["derivation_receipts"][73])
        forged["projector"]["projector_version"] = 2
        with self.assertRaisesRegex(
            package.PersonaV2SemanticProjectionDerivationInventoryError,
            "differs from the exact inventory",
        ):
            package.projection_body_provider(forged)

        invalid_receipts = []
        foreign_shard = copy.deepcopy(by_class["base-source-content-context"][0])
        foreign_shard["coordinates"]["source_shard_id"] = "foreign-shard"
        invalid_receipts.append(foreign_shard)
        foreign_persona = copy.deepcopy(effective_receipt)
        foreign_persona["coordinates"]["persona_id"] = "p99"
        invalid_receipts.append(foreign_persona)
        foreign_class = copy.deepcopy(effective_receipt)
        foreign_class["projection_class_id"] = "topology-path-load"
        invalid_receipts.append(foreign_class)
        for receipt in invalid_receipts:
            with (
                self.subTest(invalid_coordinates=receipt["coordinates"]),
                self.assertRaises(
                    package.PersonaV2SemanticProjectionDerivationInventoryError
                ),
            ):
                package.projection_body_provider(receipt)

    def test_metadata_and_rehashed_tamper_stop_before_provider(self):
        self._ensure_inventory()

        def drop_receipt(value):
            value["derivation_receipts"].pop()

        def duplicate_receipt(value):
            value["derivation_receipts"][-1] = copy.deepcopy(
                value["derivation_receipts"][0]
            )

        def reorder_receipts(value):
            value["derivation_receipts"][0], value["derivation_receipts"][1] = (
                value["derivation_receipts"][1],
                value["derivation_receipts"][0],
            )

        def extra_receipt(value):
            value["derivation_receipts"].append(
                copy.deepcopy(value["derivation_receipts"][-1])
            )

        def cumulative_cap(value):
            for receipt in value["derivation_receipts"][:73]:
                receipt["projection_pin"]["canonical_bytes"] = 4 * 2**20

        def coordinated_repin(value):
            forged_sha = "0" * 64
            value["upstream_suite_bindings"][0]["sha256"] = forged_sha
            for receipt in value["derivation_receipts"][:73]:
                receipt["full_owner_pins"][0]["sha256"] = forged_sha
            value["derivation_receipts"][0]["projection_pin"]["sha256"] = (
                forged_sha
            )

        mutations = {
            "extra-top-level": lambda value: value.update(unexpected=True),
            "suite-schema": lambda value: value.update(artifact_schema="v2"),
            "authority": lambda value: value["authority"].update(
                authorizes_g0_freeze=True
            ),
            "namespace-completion": lambda value: value["completion_claims"].update(
                semantic_payload_projection_bound=True
            ),
            "g0": lambda value: value.update(g0_contract_frozen=True),
            "drop-receipt": drop_receipt,
            "extra-receipt": extra_receipt,
            "duplicate-receipt": duplicate_receipt,
            "reorder-receipts": reorder_receipts,
            "foreign-persona": lambda value: value["derivation_receipts"][0][
                "coordinates"
            ].update(persona_id="p99"),
            "foreign-origin": lambda value: value["derivation_receipts"][0][
                "coordinates"
            ].update(origin="full"),
            "foreign-shard": lambda value: value["derivation_receipts"][0][
                "coordinates"
            ].update(source_shard_id="foreign-shard"),
            "projector": lambda value: value["derivation_receipts"][0][
                "projector"
            ].update(projector_version=2),
            "projection-pin": lambda value: value["derivation_receipts"][0][
                "projection_pin"
            ].update(sha256="0" * 64),
            "projection-pin-bool": lambda value: value["derivation_receipts"][0][
                "projection_pin"
            ].update(canonical_bytes=True),
            "full-owner": lambda value: value["derivation_receipts"][0][
                "full_owner_pins"
            ][0].update(sha256="0" * 64),
            "direct-pin": lambda value: value["derivation_receipts"][0][
                "direct_body_pins"
            ][0].update(canonical_bytes=0),
            "truthy-validation": lambda value: value["derivation_receipts"][0][
                "validation"
            ].update(upstream_owner_validation_result=1),
            "registry": lambda value: value["projection_class_registry"][0].update(
                derivation_receipt_count=1
            ),
            "missing-ledger": lambda value: value[
                "missing_projection_class_ledger"
            ][0].update(status="resolved-by-downstream-pin"),
            "orders": lambda value: value["orders"].update(persona=["p01"]),
            "summary": lambda value: value["summary"].update(
                derivation_receipt_count=112
            ),
            "canonical-limit": lambda value: value["canonical_limits"].update(
                max_receipt_count=114
            ),
            "upstream-suite": lambda value: value["upstream_suite_bindings"][
                0
            ].update(sha256="0" * 64),
            "cumulative-cap": cumulative_cap,
            "coordinated-repin": coordinated_repin,
        }
        for label, mutate in mutations.items():
            candidate = copy.deepcopy(self.inventory)
            mutate(candidate)
            calls = []

            def forbidden(_receipt):
                calls.append(True)
                raise AssertionError("metadata tamper reached provider")

            with (
                self.subTest(label=label),
                self.assertRaises(
                    independent.PersonaV2SemanticProjectionDerivationInventoryValidationError
                ),
            ):
                independent.validate_semantic_projection_derivation_inventory(
                    candidate,
                    projection_body_provider=forbidden,
                )
            self.assertEqual(calls, [], label)

    def test_provider_type_pin_cap_exception_replay_and_detachment(self):
        self._ensure_inventory()
        receipt = self.inventory["derivation_receipts"][0]
        baseline = package.projection_body_provider(receipt)

        class DerivedBytes(bytes):
            pass

        for body in (bytearray(baseline), DerivedBytes(baseline), "not-bytes"):
            calls = []

            def wrong_type(_receipt, _body=body):
                calls.append(True)
                return _body

            with (
                self.subTest(body_type=type(body).__name__),
                self.assertRaises(
                    independent.PersonaV2SemanticProjectionDerivationInventoryValidationError
                ),
            ):
                independent._authenticate_projection_body(
                    wrong_type, receipt, reauthenticate_target=lambda: None
                )
            self.assertEqual(calls, [True])

        calls = []

        def oversized(_receipt):
            calls.append(True)
            return b"x" * (package.MAX_JSONL_PROJECTION_BYTES + 1)

        with self.assertRaises(
            independent.PersonaV2SemanticProjectionDerivationInventoryValidationError
        ):
            independent._authenticate_projection_body(
                oversized, receipt, reauthenticate_target=lambda: None
            )
        self.assertEqual(calls, [True])

        calls = []

        def wrong_pin(_receipt):
            calls.append(True)
            return baseline[:-1] + (b" " if baseline[-1:] != b" " else b"x")

        with self.assertRaises(
            independent.PersonaV2SemanticProjectionDerivationInventoryValidationError
        ):
            independent._authenticate_projection_body(
                wrong_pin, receipt, reauthenticate_target=lambda: None
            )
        self.assertEqual(calls, [True])

        calls = []

        def raises(_receipt):
            calls.append(True)
            raise RuntimeError("synthetic provider failure")

        with self.assertRaises(
            independent.PersonaV2SemanticProjectionDerivationInventoryValidationError
        ):
            independent._authenticate_projection_body(
                raises, receipt, reauthenticate_target=lambda: None
            )
        self.assertEqual(calls, [True])

        calls = []
        arguments = []

        def second_wrong_type(argument):
            calls.append(True)
            arguments.append(copy.deepcopy(argument))
            argument["coordinates"]["persona_id"] = "p99"
            return baseline if len(calls) == 1 else DerivedBytes(baseline)

        with self.assertRaises(
            independent.PersonaV2SemanticProjectionDerivationInventoryValidationError
        ):
            independent._authenticate_projection_body(
                second_wrong_type,
                receipt,
                reauthenticate_target=lambda: None,
            )
        self.assertEqual(calls, [True, True])
        self.assertEqual(arguments, [receipt, receipt])
        self.assertEqual(receipt["coordinates"]["persona_id"], "p01")

        calls = []

        def nondeterministic(argument):
            calls.append(copy.deepcopy(argument))
            return baseline if len(calls) == 1 else baseline[:-1]

        with self.assertRaises(
            independent.PersonaV2SemanticProjectionDerivationInventoryValidationError
        ):
            independent._authenticate_projection_body(
                nondeterministic,
                receipt,
                reauthenticate_target=lambda: None,
            )
        self.assertEqual(calls, [receipt, receipt])

        for label, second in (
            (
                "oversized-replay",
                b"x" * (package.MAX_JSONL_PROJECTION_BYTES + 1),
            ),
            ("exception-replay", RuntimeError("synthetic replay failure")),
        ):
            replay_calls = []

            def unstable(argument, _second=second):
                replay_calls.append(copy.deepcopy(argument))
                if len(replay_calls) == 1:
                    return baseline
                if isinstance(_second, Exception):
                    raise _second
                return _second

            with (
                self.subTest(label=label),
                self.assertRaises(
                    independent.PersonaV2SemanticProjectionDerivationInventoryValidationError
                ),
            ):
                independent._authenticate_projection_body(
                    unstable,
                    receipt,
                    reauthenticate_target=lambda: None,
                )
            self.assertEqual(replay_calls, [receipt, receipt])

    def test_projection_parsers_reject_membership_query_and_runtime_leaks(self):
        self._ensure_inventory()
        by_class = _receipt_by_class(self.inventory)
        base_receipt = by_class["base-source-content-context"][0]
        base = package.projection_body_provider(base_receipt)
        first_line, remainder = base.split(b"\n", 1)
        first_row = json.loads(first_line)
        first_row["present_fact_ids"] = []
        polluted_line = json.dumps(
            first_row,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        polluted_base = polluted_line + b"\n" + remainder
        with self.assertRaises(
            independent.PersonaV2SemanticProjectionDerivationInventoryValidationError
        ):
            independent._validate_projection_body(polluted_base, base_receipt)

        malformed_base_bodies = (
            b"",
            base.rstrip(b"\n"),
            base.replace(b"\n", b"\r\n", 1),
            base + b"\n",
            first_line + b" \n" + remainder,
            first_line + b"\n" + first_line + b"\n" + remainder,
            (first_line + b"\n") * (package.MAX_JSONL_ROWS + 1),
            b'{"padding":"' + b"x" * 768 + b'"}\n',
        )
        for body in malformed_base_bodies:
            with (
                self.subTest(base_bytes=len(body)),
                self.assertRaises(
                    independent.PersonaV2SemanticProjectionDerivationInventoryValidationError
                ),
            ):
                independent._validate_projection_body(body, base_receipt)

        for raw in (
            b'{"duplicate":1,"duplicate":2}',
            b'{"float":1.5}',
            b'{"nonfinite":NaN}',
            b"\xff",
        ):
            with (
                self.subTest(strict_json=raw[:40]),
                self.assertRaises(
                    independent.PersonaV2SemanticProjectionDerivationInventoryValidationError
                ),
            ):
                independent._strict_json_loads(raw, label="focused malformed JSON")

        foreign_row = json.loads(first_line)
        foreign_row["persona_id"] = "p99"
        missing_row = json.loads(first_line)
        missing_row.pop("content_context_id")
        for row in (foreign_row, missing_row):
            raw = json.dumps(
                row,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8") + b"\n"
            with self.assertRaises(
                independent.PersonaV2SemanticProjectionDerivationInventoryValidationError
            ):
                independent._parse_base_jsonl(raw, base_receipt)

        for class_id in EXPECTED_COVERED_CLASS_ORDER[1:]:
            receipt = by_class[class_id][0]
            body = package.projection_body_provider(receipt)
            value = json.loads(body)
            for malformed in (b"[]", body + b" ", b'{"x":1,"x":2}'):
                with (
                    self.subTest(class_id=class_id, malformed=malformed[:20]),
                    self.assertRaises(
                        independent.PersonaV2SemanticProjectionDerivationInventoryValidationError
                    ),
                ):
                    independent._validate_projection_body(malformed, receipt)
            for forbidden_key in (
                "query_intent",
                "oracle_answer",
                "review_status",
                "rogue_sha256",
                "runtime_receipt",
                "solution_id",
            ):
                candidate = copy.deepcopy(value)
                candidate[forbidden_key] = "forbidden"
                raw = json.dumps(
                    candidate,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                with (
                    self.subTest(class_id=class_id, key=forbidden_key),
                    self.assertRaises(
                        independent.PersonaV2SemanticProjectionDerivationInventoryValidationError
                    ),
                ):
                    independent._validate_projection_body(raw, receipt)

            validator = (
                independent.effective_validator.validate_lifecycle_effective_membership_content_projection
                if class_id == "effective-source-membership"
                else independent.matched_validator.validate_source_matched_lifecycle_content_projection
            )
            with (
                mock.patch.object(
                    independent.effective_validator
                    if class_id == "effective-source-membership"
                    else independent.matched_validator,
                    validator.__name__,
                    return_value=1,
                ),
                self.assertRaises(
                    independent.PersonaV2SemanticProjectionDerivationInventoryValidationError
                ),
            ):
                independent._validate_projection_body(body, receipt)

    def test_noncallable_provider_is_rejected_before_body_callbacks(self):
        self._ensure_inventory()
        with self.assertRaises(
            independent.PersonaV2SemanticProjectionDerivationInventoryValidationError
        ):
            independent.validate_semantic_projection_derivation_inventory(
                self.inventory,
                projection_body_provider="not-callable",
            )

    def test_independent_all_113_acceptance_and_exact_provider_call_order(self):
        self._ensure_inventory()
        calls = []
        observed = {}

        def recording_provider(receipt):
            calls.append(copy.deepcopy(receipt))
            body = package.projection_body_provider(receipt)
            receipt_id = receipt["receipt_id"]
            if receipt_id not in observed:
                class_id = receipt["projection_class_id"]
                self.assertNotIn(receipt_id.encode("utf-8"), body)
                for owner_pin in receipt["full_owner_pins"]:
                    self.assertNotIn(owner_pin["sha256"].encode("ascii"), body)
                record = {
                    "body_bytes": len(body),
                    "maximum_row_bytes_including_lf": None,
                    "row_count": None,
                    "sha256": _sha256(body),
                }
                if class_id == "base-source-content-context":
                    rows = body.splitlines(keepends=True)
                    record["row_count"] = len(rows)
                    record["maximum_row_bytes_including_lf"] = max(map(len, rows))
                    for framed in rows:
                        row = json.loads(framed)
                        self.assertEqual(set(row), independent.BASE_ROW_FIELDS)
                        self.assertTrue(
                            set(row).isdisjoint(independent.BASE_FORBIDDEN_FIELDS)
                        )
                else:
                    value = json.loads(body)
                    self.assertIs(type(value), dict)
                    for key in _walk_keys(value):
                        folded = key.replace("_", "-").lower()
                        tokens = frozenset(folded.split("-"))
                        self.assertTrue(
                            tokens.isdisjoint(independent.FORBIDDEN_KEY_TOKENS),
                            (class_id, key),
                        )
                observed[receipt_id] = record
            return body

        self.assertIs(
            independent.validate_semantic_projection_derivation_inventory(
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
        self.assertEqual(len(observed), 113)
        receipts = self.inventory["derivation_receipts"]
        for receipt in receipts:
            record = observed[receipt["receipt_id"]]
            self.assertEqual(
                record["body_bytes"], receipt["projection_pin"]["canonical_bytes"]
            )
            self.assertEqual(
                record["sha256"], receipt["projection_pin"]["sha256"]
            )
        base_records = [
            observed[row["receipt_id"]]
            for row in receipts
            if row["projection_class_id"] == "base-source-content-context"
        ]
        self.assertEqual(
            sum(row["row_count"] for row in base_records),
            EXPECTED_BASE_ROW_COUNT,
        )
        self.assertEqual(
            sum(row["body_bytes"] for row in base_records),
            EXPECTED_BASE_BODY_BYTES,
        )
        self.assertEqual(
            max(row["body_bytes"] for row in base_records),
            EXPECTED_CLASS_MAXIMUM_BODY_BYTES["base-source-content-context"],
        )
        self.assertLessEqual(
            max(row["row_count"] for row in base_records), package.MAX_JSONL_ROWS
        )
        self.assertEqual(
            max(row["maximum_row_bytes_including_lf"] for row in base_records),
            EXPECTED_BASE_MAXIMUM_ROW_BYTES_INCLUDING_LF,
        )
        lifecycle_records = [
            observed[row["receipt_id"]]
            for row in receipts
            if row["projection_class_id"] != "base-source-content-context"
        ]
        self.assertEqual(len(lifecycle_records), 40)
        for class_id in EXPECTED_COVERED_CLASS_ORDER[1:]:
            self.assertEqual(
                max(
                    observed[row["receipt_id"]]["body_bytes"]
                    for row in receipts
                    if row["projection_class_id"] == class_id
                ),
                EXPECTED_CLASS_MAXIMUM_BODY_BYTES[class_id],
            )
        self.assertEqual(
            sum(row["body_bytes"] for row in observed.values()),
            EXPECTED_CUMULATIVE_PROJECTION_BYTES,
        )

    def test_target_mutation_during_provider_callback_is_rejected(self):
        self._ensure_inventory()
        target = copy.deepcopy(self.inventory)
        calls = []

        def mutating_wrong_type(receipt):
            calls.append(copy.deepcopy(receipt))
            target["summary"]["derivation_receipt_count"] = 0
            return bytearray(package.projection_body_provider(receipt))

        with self.assertRaisesRegex(
            independent.PersonaV2SemanticProjectionDerivationInventoryValidationError,
            "mutated during validation",
        ):
            independent.validate_semantic_projection_derivation_inventory(
                target,
                projection_body_provider=mutating_wrong_type,
            )
        self.assertEqual(len(calls), 1)

    def test_full_owner_mutation_during_provider_callback_is_rejected(self):
        self._ensure_inventory()
        target = copy.deepcopy(self.inventory)
        first_receipt = target["derivation_receipts"][0]
        first_body = package.projection_body_provider(first_receipt)
        original_builder = (
            source_semantic.build_source_semantic_membership_origin_manifest
        )
        calls = []

        def mutating_provider(receipt):
            calls.append(receipt["receipt_id"])
            source_semantic.build_source_semantic_membership_origin_manifest = (
                lambda *_args, **_kwargs: {
                    "artifact_kind": source_semantic.ORIGIN_ARTIFACT_KIND,
                    "artifact_schema": source_semantic.ORIGIN_ARTIFACT_SCHEMA,
                    "artifact_schema_version": source_semantic.ARTIFACT_SCHEMA_VERSION,
                }
            )
            return first_body

        try:
            with self.assertRaisesRegex(
                independent.PersonaV2SemanticProjectionDerivationInventoryValidationError,
                "full owner",
            ):
                independent.validate_semantic_projection_derivation_inventory(
                    target,
                    projection_body_provider=mutating_provider,
                )
        finally:
            source_semantic.build_source_semantic_membership_origin_manifest = (
                original_builder
            )
        self.assertEqual(calls, [first_receipt["receipt_id"]])

    def test_direct_body_mutation_during_provider_callback_is_rejected(self):
        self._ensure_inventory()
        target = copy.deepcopy(self.inventory)
        first_receipt = target["derivation_receipts"][0]
        first_body = package.projection_body_provider(first_receipt)
        original_provider = source_semantic.source_semantic_membership_origin_body_bytes
        calls = []

        def mutating_provider(receipt):
            calls.append(receipt["receipt_id"])
            source_semantic.source_semantic_membership_origin_body_bytes = (
                lambda *_args, **_kwargs: b"evil\n"
            )
            return first_body

        try:
            with self.assertRaisesRegex(
                independent.PersonaV2SemanticProjectionDerivationInventoryValidationError,
                "direct owner",
            ):
                independent.validate_semantic_projection_derivation_inventory(
                    target,
                    projection_body_provider=mutating_provider,
                )
        finally:
            source_semantic.source_semantic_membership_origin_body_bytes = (
                original_provider
            )
        self.assertEqual(calls, [first_receipt["receipt_id"]])

        canonical_count = self.inventory["summary"]["derivation_receipt_count"]
        opening_tamper = copy.deepcopy(self.inventory)
        opening_tamper["summary"]["derivation_receipt_count"] = 0
        relay_calls = []

        def attempted_aba_relay(receipt):
            relay_calls.append(copy.deepcopy(receipt))
            opening_tamper["summary"][
                "derivation_receipt_count"
            ] = canonical_count
            return package.projection_body_provider(receipt)

        with self.assertRaises(
            independent.PersonaV2SemanticProjectionDerivationInventoryValidationError
        ):
            independent.validate_semantic_projection_derivation_inventory(
                opening_tamper,
                projection_body_provider=attempted_aba_relay,
            )
        self.assertEqual(relay_calls, [])
        self.assertEqual(
            opening_tamper["summary"]["derivation_receipt_count"], 0
        )


class SemanticProjectionDerivationInventoryLongColdHashSeedTest(unittest.TestCase):
    """Cold two-seed canonical/resource gate kept explicit for CI budgeting."""

    def test_two_hashseeds_are_canonical_and_resource_bounded(self):
        script = r'''
import collections
import hashlib
import json
import resource
import sys
import time

from eval import persona_v2_semantic_projection_derivation_inventory as package

started = time.monotonic()
inventory = package.build_semantic_projection_derivation_inventory()
suite_raw = package.canonical_json_bytes(inventory)
class_counts = collections.Counter()
class_maximum_body_bytes = collections.defaultdict(int)
base_body_bytes = 0
base_maximum_row_bytes_including_lf = 0
base_row_count = 0
ordered_projection_pins = []
external_body_bytes = 0

for receipt in inventory["derivation_receipts"]:
    body = package.projection_body_provider(receipt)
    projection_class_id = receipt["projection_class_id"]
    projection_pin = receipt["projection_pin"]
    assert type(body) is bytes
    assert len(body) == projection_pin["canonical_bytes"]
    assert hashlib.sha256(body).hexdigest() == projection_pin["sha256"]
    class_counts[projection_class_id] += 1
    class_maximum_body_bytes[projection_class_id] = max(
        class_maximum_body_bytes[projection_class_id], len(body)
    )
    external_body_bytes += len(body)
    ordered_projection_pins.append(
        {
            "receipt_id": receipt["receipt_id"],
            "canonical_bytes": projection_pin["canonical_bytes"],
            "sha256": projection_pin["sha256"],
        }
    )
    if projection_class_id == "base-source-content-context":
        rows = body.splitlines(keepends=True)
        base_body_bytes += len(body)
        base_row_count += len(rows)
        base_maximum_row_bytes_including_lf = max(
            base_maximum_row_bytes_including_lf,
            max(map(len, rows)),
        )

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
    "base_body_bytes": base_body_bytes,
    "base_maximum_row_bytes_including_lf": base_maximum_row_bytes_including_lf,
    "base_row_count": base_row_count,
    "class_counts": dict(sorted(class_counts.items())),
    "class_maximum_body_bytes": dict(sorted(class_maximum_body_bytes.items())),
    "elapsed_seconds": time.monotonic() - started,
    "external_body_bytes": external_body_bytes,
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
            self.assertEqual(measurement["base_row_count"], EXPECTED_BASE_ROW_COUNT)
            self.assertEqual(
                measurement["base_body_bytes"], EXPECTED_BASE_BODY_BYTES
            )
            self.assertEqual(
                measurement["base_maximum_row_bytes_including_lf"],
                EXPECTED_BASE_MAXIMUM_ROW_BYTES_INCLUDING_LF,
            )
            self.assertEqual(
                measurement["class_counts"], EXPECTED_RECEIPT_COUNTS
            )
            self.assertEqual(sum(measurement["class_counts"].values()), 113)
            self.assertEqual(
                measurement["class_maximum_body_bytes"],
                EXPECTED_CLASS_MAXIMUM_BODY_BYTES,
            )
            self.assertEqual(
                measurement["external_body_bytes"],
                EXPECTED_CUMULATIVE_PROJECTION_BYTES,
            )
            self.assertEqual(
                measurement["suite_bytes"], EXPECTED_SUITE_CANONICAL_BYTES
            )
            self.assertEqual(measurement["suite_sha256"], EXPECTED_SUITE_SHA256)
            self.assertEqual(
                measurement["ordered_projection_pins_sha256"],
                EXPECTED_ORDERED_PROJECTION_PINS_SHA256,
            )
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
