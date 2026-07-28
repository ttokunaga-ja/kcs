"""Focused and opt-in tests for the pre-solve history-input closure slice."""

from __future__ import annotations

import ast
import collections
import contextlib
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
    from . import persona_v2_history_presolve_input_closure_slice as package
    from . import persona_v2_history_presolve_input_closure_slice_validator as independent
except ImportError:  # pragma: no cover - direct discovery compatibility
    import persona_v2_history_presolve_input_closure_slice as package
    import persona_v2_history_presolve_input_closure_slice_validator as independent


FROZEN_GOLDEN = (
    8_455,
    "34902a3663f2eeefb014696b38e761561e6f5e55060243ca71579f3400ac02d8",
)


def _producer_snapshot(*, full=False):
    if full:
        raise AssertionError("focused tests must not cross the full trust boundary")
    return package._frozen_dependency_snapshot()


def _independent_snapshot(*, full=False):
    if full:
        raise AssertionError("focused tests must not cross the full trust boundary")
    return independent._frozen_dependency_snapshot()


def _ast_imported_modules(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.append(node.module)
            imported.extend(alias.name for alias in node.names)
    return imported


@contextlib.contextmanager
def _focused_trust_boundaries():
    with mock.patch.object(
        package, "_live_dependency_snapshot", side_effect=_producer_snapshot
    ), mock.patch.object(
        independent,
        "_live_dependency_snapshot",
        side_effect=_independent_snapshot,
    ):
        yield


class PersonaV2HistoryPresolveInputClosureSliceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.producer_expected_golden = package._expected_golden()
        cls.validator_expected_golden = independent._expected_golden()
        with _focused_trust_boundaries():
            cls.value = package.build_history_presolve_input_closure_slice()
            cls.raw = package.canonical_json_bytes(cls.value)

    def _validate(self, value):
        with _focused_trust_boundaries():
            return independent.validate_history_presolve_input_closure_slice(value)

    def test_exact_identity_four_pins_and_frozen_golden(self):
        self.assertEqual(self.value["artifact_schema"], package.ARTIFACT_SCHEMA)
        self.assertEqual(self.value["artifact_schema_version"], 1)
        self.assertLess(len(self.raw), package.TARGET_MANIFEST_BYTES)
        self.assertLessEqual(len(self.raw), package.MAX_MANIFEST_BYTES)
        self.assertEqual(
            self.producer_expected_golden,
            FROZEN_GOLDEN,
        )
        self.assertEqual(self.validator_expected_golden, FROZEN_GOLDEN)
        self.assertEqual(
            (len(self.raw), hashlib.sha256(self.raw).hexdigest()),
            FROZEN_GOLDEN,
        )

        pins = self.value["dependency_pins"]
        self.assertEqual(
            [row["dependency_id"] for row in pins],
            list(package.DIRECT_DEPENDENCY_ORDER),
        )
        self.assertEqual(
            [(row["canonical_bytes"], row["sha256"]) for row in pins],
            [
                (
                    161_665,
                    "a8bc67e182ff57b64ae6df0f97bd5be31faf6e5f7b7cfbd0bc3f1ba7bc5cc509",
                ),
                (
                    697_466,
                    "6826fb14293e7147159fae1849f93533c35ae76f1beecbd093d190cd6ddd3e69",
                ),
                (
                    14_605,
                    "c4508ed61c88db80b003e9ce3b7c35ea153776442bd3224964897400633dd2c8",
                ),
                (
                    69_195,
                    "14ff220bf47656965d1ac1803a0dd0ccc6b8afa440b64f563e40e623a219bb7c",
                ),
            ],
        )
        self.assertEqual(
            self.value["summary"]["direct_dependency_canonical_bytes"],
            942_931,
        )
        self.assertFalse(
            self.value["canonical_limits"]["direct_dependency_bodies_embedded"]
        )
        self.assertEqual(
            self.value["canonical_limits"]["max_nesting_depth"], 16
        )

    def test_atomic_optional_golden_rejects_partial_and_invalid_pairs(self):
        valid_pair = (len(self.raw), hashlib.sha256(self.raw).hexdigest())
        invalid_pairs = (
            (valid_pair[0], None),
            (None, valid_pair[1]),
            (True, valid_pair[1]),
            (0, valid_pair[1]),
            (package.TARGET_MANIFEST_BYTES + 1, valid_pair[1]),
            (valid_pair[0], "A" * 64),
            (valid_pair[0], "0" * 63),
        )
        for module, error_type in (
            (package, package.PersonaV2HistoryPresolveInputClosureSliceError),
            (
                independent,
                independent.PersonaV2HistoryPresolveInputClosureSliceValidationError,
            ),
        ):
            for byte_count, digest in invalid_pairs:
                with self.subTest(
                    module=module.__name__, byte_count=byte_count, digest=digest
                ), mock.patch.object(
                    module, "EXPECTED_CANONICAL_BYTES", byte_count
                ), mock.patch.object(module, "EXPECTED_SHA256", digest):
                    with self.assertRaises(error_type):
                        module._expected_golden()

    def test_invalid_or_mismatched_goldens_fail_before_live_body_access(self):
        valid_pair = (len(self.raw), hashlib.sha256(self.raw).hexdigest())
        producer_calls = (
            package.build_history_presolve_input_closure_slice,
            lambda: package.canonical_json_bytes(self.value),
            lambda: package.validate_history_presolve_input_closure_slice(
                self.value
            ),
            lambda: package.history_presolve_input_closure_slice_sha256(
                self.value
            ),
            package.require_full_history_presolve_input_closure_slice,
        )
        heavy_targets = (
            (package.complete, "build_semantic_projection_complete_inventory"),
            (independent.complete, "build_semantic_projection_complete_inventory"),
        )

        for producer_pair, validator_pair in (
            ((valid_pair[0], None), None),
            (None, (None, valid_pair[1])),
            (valid_pair, None),
            (None, valid_pair),
            ((valid_pair[0] + 1, "0" * 64), (valid_pair[0] + 1, "0" * 64)),
        ):
            producer_bytes, producer_digest = (
                (None, None) if producer_pair is None else producer_pair
            )
            validator_bytes, validator_digest = (
                (None, None) if validator_pair is None else validator_pair
            )
            with mock.patch.object(
                package, "EXPECTED_CANONICAL_BYTES", producer_bytes
            ), mock.patch.object(
                package, "EXPECTED_SHA256", producer_digest
            ), mock.patch.object(
                independent, "EXPECTED_CANONICAL_BYTES", validator_bytes
            ), mock.patch.object(
                independent, "EXPECTED_SHA256", validator_digest
            ), mock.patch.object(
                *heavy_targets[0], side_effect=AssertionError("live body opened")
            ) as producer_heavy, mock.patch.object(
                *heavy_targets[1], side_effect=AssertionError("live body opened")
            ) as validator_heavy:
                for call in producer_calls:
                    with self.assertRaises(
                        package.PersonaV2HistoryPresolveInputClosureSliceError
                    ):
                        call()
                producer_heavy.assert_not_called()
                validator_heavy.assert_not_called()

                with self.assertRaises(
                    independent.PersonaV2HistoryPresolveInputClosureSliceValidationError
                ):
                    independent.validate_history_presolve_input_closure_slice_full(
                        self.value,
                        producer_expected_golden=producer_pair,
                    )
                producer_heavy.assert_not_called()
                validator_heavy.assert_not_called()

    def test_validator_public_paths_guard_golden_before_live_snapshot(self):
        valid_pair = (len(self.raw), hashlib.sha256(self.raw).hexdigest())
        for byte_count, digest in (
            (valid_pair[0], None),
            (None, valid_pair[1]),
        ):
            with mock.patch.object(
                independent, "EXPECTED_CANONICAL_BYTES", byte_count
            ), mock.patch.object(
                independent, "EXPECTED_SHA256", digest
            ), mock.patch.object(
                independent,
                "_live_dependency_snapshot",
                side_effect=AssertionError("live snapshot opened"),
            ) as live_snapshot:
                calls = (
                    lambda: independent.strict_load_canonical_json_bytes(
                        self.raw
                    ),
                    lambda: independent.validate_history_presolve_input_closure_slice(
                        self.value
                    ),
                    lambda: independent.validate_history_presolve_input_closure_slice_bytes(
                        self.raw
                    ),
                    lambda: independent.validate_history_presolve_input_closure_slice_full(
                        self.value,
                        producer_expected_golden=None,
                    ),
                )
                for call in calls:
                    with self.assertRaises(
                        independent.PersonaV2HistoryPresolveInputClosureSliceValidationError
                    ):
                        call()
                live_snapshot.assert_not_called()

        with mock.patch.object(
            independent,
            "_live_dependency_snapshot",
            side_effect=AssertionError("live snapshot opened"),
        ) as live_snapshot:
            with self.assertRaises(
                independent.PersonaV2HistoryPresolveInputClosureSliceValidationError
            ):
                independent.validate_history_presolve_input_closure_slice_full(
                    self.value
                )
        live_snapshot.assert_not_called()

    def test_exact_presolve_history_coverage_and_witness_boundary(self):
        coverage = self.value["history_coverage"]
        expected = {
            "persona_count": 20,
            "lifecycle_source_ref_count": 2_300,
            "primary_source_ref_count": 2_100,
            "companion_source_ref_count": 200,
            "pre_solve_lifecycle_event_intent_count": 7_630,
            "w0_source_intent_count": 203_000,
            "event_created_source_intent_count": 3_630,
            "purge_witness_count": 300,
            "inverted_witness_count": 300,
            "inverted_consumer_reference_count": 600,
            "witness_consumer_count_per_witness": 2,
            "w0_purge_witness_consumer_count": 300,
            "event_created_witness_carrying_count": 300,
            "event_created_witness_empty_count": 3_330,
            "present_fact_reference_count": 1_033_680,
        }
        for key, value in expected.items():
            self.assertEqual(coverage[key], value, key)
        self.assertEqual(
            sum(
                coverage[key]
                for key in (
                    "effective_w0_base_inheritance_count",
                    "effective_w0_companion_mirror_count",
                    "effective_w0_graph_normal_count",
                    "effective_w0_graph_normal_plus_witness_count",
                )
            ),
            203_000,
        )
        compact = self.value["compact_owner_summary"]
        self.assertEqual(compact["membership_compact_row_count"], 2_573)
        self.assertEqual(compact["effective_shard_receipt_count"], 73)
        self.assertEqual(compact["primary_override_row_count"], 2_000)
        self.assertEqual(compact["companion_mirror_row_count"], 200)
        self.assertEqual(compact["typed_purge_witness_row_count"], 300)
        self.assertFalse(compact["event_and_inverted_views_persisted"])

    def test_all_execution_authority_and_downstream_completion_remain_false(self):
        value = self.value
        self.assertEqual(set(value["authority"]), package.AUTHORITY_FIELDS)
        self.assertTrue(all(flag is False for flag in value["authority"].values()))
        self.assertFalse(value["g0_contract_frozen"])
        for key in (
            "authoritative_history_input_closure_ready",
            "compiled_history_plan_available",
            "final_identifiers_bound",
            "g0_approved",
            "history_runtime_receipts_bound",
            "physical_files_written",
            "planned_event_identifiers_bound",
            "post_w0_complete_membership_compiled",
            "post_w0_history_state_ready",
            "production_history_input_closure_complete",
            "query_bound_history_state_ready",
            "scope_path_quota_solution_bound",
            "solver_solution_and_proof_bound",
            "whole_corpus_post_w0_event_plan_complete",
        ):
            self.assertFalse(value["completion_claims"][key], key)
        self.assertTrue(
            value["completion_claims"]["w0_only_structural_presolve_slice_bound"]
        )
        direction = value["dependency_direction_contract"]
        self.assertTrue(
            direction["slice_is_query_independent_structural_w0_only"]
        )
        self.assertFalse(
            direction["slice_is_authoritative_history_input_closure"]
        )
        self.assertIn("w0-only", value["completion_scope"])
        self.assertIn("not-authoritative", value["hypothesis_status"])
        unresolved = value["unresolved_solution_compilation"]
        self.assertFalse(
            unresolved["presolve_lineage_is_complete_post_w0_membership"]
        )
        for key, count in unresolved.items():
            if key != "presolve_lineage_is_complete_post_w0_membership":
                self.assertEqual(count, 0, key)

    def test_authoritative_require_always_fails_without_provider_access(self):
        with mock.patch.object(
            package,
            "_live_dependency_snapshot",
            side_effect=AssertionError("provider opened"),
        ) as provider:
            with self.assertRaises(
                package.PersonaV2HistoryPresolveInputClosureSliceError
            ):
                package.require_authoritative_history_presolve_input_closure_slice()
        provider.assert_not_called()

    def test_excluded_dependency_families_are_not_direct_roots(self):
        exclusions = self.value["dependency_exclusion_contract"]
        self.assertTrue(all(flag is False for flag in exclusions.values()))
        dependency_ids = [
            row["dependency_id"] for row in self.value["dependency_pins"]
        ]
        for forbidden in ("query", "review", "ledger", "evaluation-closure"):
            self.assertFalse(
                any(forbidden in dependency_id for dependency_id in dependency_ids)
            )
        self.assertEqual(len(dependency_ids), 4)
        self.assertFalse(self.value["semantic_context"]["namespace_issued"])
        self.assertFalse(
            self.value["semantic_context"]["external_projection_bodies_embedded"]
        )

    def test_independent_validator_accepts_object_bytes_and_accepted_hash(self):
        validator_path = Path(independent.__file__).resolve()
        producer_module = "persona_v2_history_presolve_input_closure_slice"
        imported_modules = _ast_imported_modules(validator_path)
        self.assertFalse(
            any(
                name == producer_module or name.endswith(f".{producer_module}")
                for name in imported_modules
            ),
            "independent validator must not import the producer",
        )
        self.assertTrue(self._validate(self.value))
        with _focused_trust_boundaries():
            self.assertTrue(
                independent.validate_history_presolve_input_closure_slice_bytes(
                    self.raw
                )
            )
            self.assertEqual(
                package.history_presolve_input_closure_slice_sha256(self.value),
            hashlib.sha256(self.raw).hexdigest(),
        )

    def test_producer_and_validator_import_no_downstream_closure_families(self):
        forbidden_fragments = (
            "corpus_input_closure",
            "evaluation_target_resolution_closure",
            "g0_blocker_resolution_ledger",
            "query_history",
            "query_intent",
            "review_request",
            "review_receipt",
            "semantic_oracle",
        )
        for path in (
            Path(package.__file__).resolve(),
            Path(independent.__file__).resolve(),
        ):
            imported_modules = _ast_imported_modules(path)
            self.assertFalse(
                any(
                    fragment in name
                    for name in imported_modules
                    for fragment in forbidden_fragments
                ),
                f"history structural slice imports a downstream family: {path.name}",
            )

    def test_declared_upstreams_import_neither_history_slice_module(self):
        forbidden_modules = (
            "persona_v2_history_presolve_input_closure_slice",
            "persona_v2_history_presolve_input_closure_slice_validator",
        )
        eval_dir = Path(__file__).resolve().parent
        upstream_paths = {
            eval_dir / "persona_v2_corpus_semantic_namespace_v3.py",
            eval_dir / "persona_v2_corpus_semantic_namespace_v3_validator.py",
            eval_dir / "persona_v2_semantic_projection_complete_inventory.py",
            eval_dir
            / "persona_v2_semantic_projection_complete_inventory_validator.py",
            eval_dir / "persona_v2_source_matched_lifecycle_inventory.py",
            eval_dir
            / "persona_v2_source_matched_lifecycle_inventory_validator.py",
            eval_dir
            / "persona_v2_lifecycle_effective_membership_reconciliation.py",
            eval_dir
            / "persona_v2_lifecycle_effective_membership_reconciliation_validator.py",
        }
        self.assertTrue(all(path.is_file() for path in upstream_paths))
        for path in sorted(upstream_paths):
            imported_modules = _ast_imported_modules(path)
            self.assertFalse(
                any(
                    name == forbidden
                    or name.endswith(f".{forbidden}")
                    for name in imported_modules
                    for forbidden in forbidden_modules
                ),
                f"declared upstream imports a history slice module: {path.name}",
            )

    def test_default_validation_builds_live_dependency_snapshot_once(self):
        with mock.patch.object(
            independent,
            "_live_dependency_snapshot",
            side_effect=_independent_snapshot,
        ) as live_snapshot:
            self.assertTrue(
                independent.validate_history_presolve_input_closure_slice(
                    self.value
                )
            )
        live_snapshot.assert_called_once_with()

    def test_default_build_and_validation_never_open_live_dependency_bodies(self):
        with mock.patch.object(
            package.complete,
            "build_semantic_projection_complete_inventory",
            side_effect=AssertionError("producer opened a live body"),
        ) as producer_body, mock.patch.object(
            independent.complete,
            "build_semantic_projection_complete_inventory",
            side_effect=AssertionError("validator opened a live body"),
        ) as validator_body:
            value = package.build_history_presolve_input_closure_slice()
            self.assertTrue(
                package.validate_history_presolve_input_closure_slice(value)
            )
        producer_body.assert_not_called()
        validator_body.assert_not_called()

    def test_authority_completion_pin_coverage_and_unresolved_mutations_fail(self):
        mutations = []

        authority = copy.deepcopy(self.value)
        authority["authority"]["authorizes_history_mutation"] = True
        mutations.append(authority)

        completion = copy.deepcopy(self.value)
        completion["completion_claims"]["compiled_history_plan_available"] = True
        mutations.append(completion)

        pin = copy.deepcopy(self.value)
        pin["dependency_pins"][3]["sha256"] = "0" * 64
        mutations.append(pin)

        coverage = copy.deepcopy(self.value)
        coverage["history_coverage"]["event_created_source_intent_count"] = 3_629
        mutations.append(coverage)

        unresolved = copy.deepcopy(self.value)
        unresolved["unresolved_solution_compilation"][
            "planned_event_id_count"
        ] = 1
        mutations.append(unresolved)

        excluded = copy.deepcopy(self.value)
        excluded["dependency_exclusion_contract"]["query_or_oracle_bound"] = True
        mutations.append(excluded)

        for value in mutations:
            with self.subTest(keys=list(value)):
                with self.assertRaises(
                    independent.PersonaV2HistoryPresolveInputClosureSliceValidationError
                ):
                    self._validate(value)

    def test_static_contract_flips_fail_before_canonical_hash_or_providers(self):
        authority = copy.deepcopy(self.value)
        authority["authority"]["authorizes_history_input_closure"] = True

        readiness = copy.deepcopy(self.value)
        readiness["completion_claims"][
            "authoritative_history_input_closure_ready"
        ] = True

        namespace_issued = copy.deepcopy(self.value)
        namespace_issued["semantic_context"]["namespace_issued"] = True

        for label, value in (
            ("authority", authority),
            ("authoritative-readiness", readiness),
            ("namespace-issued", namespace_issued),
        ):
            raw = json.dumps(
                value,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            with self.subTest(label=label), mock.patch.object(
                package,
                "_live_dependency_snapshot",
                side_effect=AssertionError("producer provider opened"),
            ) as producer_provider, mock.patch.object(
                independent,
                "_live_dependency_snapshot",
                side_effect=AssertionError("validator provider opened"),
            ) as validator_provider:
                for call in (
                    lambda: package.canonical_json_bytes(value),
                    lambda: package.history_presolve_input_closure_slice_sha256(
                        value
                    ),
                    lambda: package.validate_history_presolve_input_closure_slice(
                        value
                    ),
                ):
                    with self.assertRaises(
                        package.PersonaV2HistoryPresolveInputClosureSliceError
                    ):
                        call()
                with self.assertRaises(
                    independent.PersonaV2HistoryPresolveInputClosureSliceValidationError
                ):
                    independent.validate_history_presolve_input_closure_slice_bytes(
                        raw
                    )
                producer_provider.assert_not_called()
                validator_provider.assert_not_called()

    def test_type_confusion_order_extra_and_noncanonical_scalars_fail_closed(self):
        mutations = []

        boolean_version = copy.deepcopy(self.value)
        boolean_version["artifact_schema_version"] = True
        mutations.append(boolean_version)

        boolean_count = copy.deepcopy(self.value)
        boolean_count["summary"]["persona_count"] = True
        mutations.append(boolean_count)

        reordered = copy.deepcopy(self.value)
        reordered["dependency_order"].reverse()
        mutations.append(reordered)

        extra = copy.deepcopy(self.value)
        extra["unexpected"] = False
        mutations.append(extra)

        null_value = copy.deepcopy(self.value)
        null_value["summary"]["persona_count"] = None
        mutations.append(null_value)

        float_value = copy.deepcopy(self.value)
        float_value["summary"]["persona_count"] = 20.0
        mutations.append(float_value)

        negative = copy.deepcopy(self.value)
        negative["summary"]["persona_count"] = -1
        mutations.append(negative)

        for value in mutations:
            with self.assertRaises(
                independent.PersonaV2HistoryPresolveInputClosureSliceValidationError
            ):
                self._validate(value)

    def test_strict_bytes_reject_duplicates_noncanonical_numbers_and_frames(self):
        invalid = (
            self.raw + b"\n",
            b'{"a":1,"a":1}',
            b'{"artifact_kind":1.0}',
            b'{"artifact_kind":NaN}',
            b'{"artifact_kind":9223372036854775808}',
            b'{"artifact_kind":123456789012345678901234567890}',
            b"\xff",
            b"{}",
            b"[1]",
        )
        for raw in invalid:
            with self.assertRaises(
                independent.PersonaV2HistoryPresolveInputClosureSliceValidationError
            ):
                with _focused_trust_boundaries():
                    independent.validate_history_presolve_input_closure_slice_bytes(
                        raw
                    )
        with self.assertRaises(
            independent.PersonaV2HistoryPresolveInputClosureSliceValidationError
        ):
            independent.strict_load_canonical_json_bytes("not-bytes")
        with self.assertRaises(
            independent.PersonaV2HistoryPresolveInputClosureSliceValidationError
        ):
            independent.strict_load_canonical_json_bytes(
                b"{" + b" " * independent.MAX_MANIFEST_BYTES
            )

    def test_alias_cycle_and_precopy_expansion_bombs_fail_closed(self):
        shared = []
        alias = copy.deepcopy(self.value)
        alias["dependency_order"] = shared
        alias["remaining_blockers"] = shared

        cycle = copy.deepcopy(self.value)
        cycle["remaining_blockers"].append(cycle)

        huge_object = copy.deepcopy(self.value)
        huge_object["authority"] = {
            f"extra-{ordinal:03d}": False
            for ordinal in range(independent.MAX_CONTAINER_ITEMS + 1)
        }

        for value in (alias, cycle, huge_object):
            with self.assertRaises(
                independent.PersonaV2HistoryPresolveInputClosureSliceValidationError
            ):
                independent._snapshot_candidate(value)

        repeated_scalar = "x" * 4_096
        expanded = copy.deepcopy(self.value)
        expanded["remaining_blockers"] = [
            [repeated_scalar] * independent.MAX_CONTAINER_ITEMS
            for _ in range(independent.MAX_CONTAINER_ITEMS)
        ]
        with mock.patch.object(
            independent.copy,
            "deepcopy",
            side_effect=AssertionError("expanded input reached deepcopy"),
        ):
            with self.assertRaises(
                independent.PersonaV2HistoryPresolveInputClosureSliceValidationError
            ):
                independent._snapshot_candidate(expanded)

    def test_huge_top_level_mapping_fails_before_set_or_deepcopy(self):
        huge = {f"attacker-field-{ordinal:06d}": False for ordinal in range(100_000)}
        with mock.patch.object(
            independent,
            "set",
            create=True,
            side_effect=AssertionError("attacker keys were materialized as a set"),
        ) as set_constructor, mock.patch.object(
            independent.copy,
            "deepcopy",
            side_effect=AssertionError("attacker mapping reached deepcopy"),
        ) as deepcopy:
            with self.assertRaises(
                independent.PersonaV2HistoryPresolveInputClosureSliceValidationError
            ):
                independent._snapshot_candidate(huge)
        set_constructor.assert_not_called()
        deepcopy.assert_not_called()

    def test_oversized_scalar_fails_before_its_encode_copy_or_provider(self):
        value = copy.deepcopy(self.value)
        oversized = "x" * (
            independent.artifact_common.MAX_CANONICAL_STRING_BYTES + 1
        )
        value["completion_scope"] = oversized
        original_encode = independent._encode_utf8
        oversized_encode_calls = []

        def guarded_encode(candidate, *, label):
            if len(candidate) > independent.artifact_common.MAX_CANONICAL_STRING_BYTES:
                oversized_encode_calls.append(label)
                raise AssertionError("oversized scalar reached UTF-8 encoding")
            return original_encode(candidate, label=label)

        with mock.patch.object(
            independent,
            "_encode_utf8",
            side_effect=guarded_encode,
        ), mock.patch.object(
            independent.copy,
            "deepcopy",
            side_effect=AssertionError("oversized scalar reached deepcopy"),
        ) as deepcopy, mock.patch.object(
            package,
            "_live_dependency_snapshot",
            side_effect=AssertionError("producer provider opened"),
        ) as producer_provider, mock.patch.object(
            independent,
            "_live_dependency_snapshot",
            side_effect=AssertionError("validator provider opened"),
        ) as validator_provider:
            with self.assertRaises(
                package.PersonaV2HistoryPresolveInputClosureSliceError
            ):
                package.canonical_json_bytes(value)
        self.assertEqual(oversized_encode_calls, [])
        deepcopy.assert_not_called()
        producer_provider.assert_not_called()
        validator_provider.assert_not_called()

    def test_candidate_dependency_and_hash_toctou_fail_closed(self):
        target = copy.deepcopy(self.value)
        real_deepcopy = copy.deepcopy

        def candidate_copy_then_mutate(value):
            detached = real_deepcopy(value)
            if value is target:
                value["summary"]["persona_count"] = 0
            return detached

        with mock.patch.object(
            independent.copy,
            "deepcopy",
            side_effect=candidate_copy_then_mutate,
        ):
            with self.assertRaises(
                independent.PersonaV2HistoryPresolveInputClosureSliceValidationError
            ):
                independent._snapshot_candidate(target)

        dependency = independent._frozen_dependency_snapshot()

        def mutate_dependency(value):
            value["history_coverage"]["persona_count"] = 0

        with self.assertRaises(
            independent.PersonaV2HistoryPresolveInputClosureSliceValidationError
        ):
            independent._snapshot_dependencies(
                lambda: dependency,
                dependency_observer=mutate_dependency,
            )

        hash_target = copy.deepcopy(self.value)

        def mutate_during_validation(_value):
            hash_target["summary"]["persona_count"] = 0
            return True

        with _focused_trust_boundaries(), mock.patch.object(
            package,
            "validate_history_presolve_input_closure_slice",
            side_effect=mutate_during_validation,
        ):
            with self.assertRaises(
                package.PersonaV2HistoryPresolveInputClosureSliceError
            ):
                package.history_presolve_input_closure_slice_sha256(hash_target)

    def test_dependency_constant_drift_and_missing_independent_validator_fail(self):
        with _focused_trust_boundaries(), mock.patch.object(
            package.lifecycle,
            "EXPECTED_SUITE_CANONICAL_BYTES",
            0,
        ):
            with self.assertRaises(
                package.PersonaV2HistoryPresolveInputClosureSliceError
            ):
                package.build_history_presolve_input_closure_slice()

        for module, dependency, error_type, call in (
            (
                package,
                package.lifecycle,
                package.PersonaV2HistoryPresolveInputClosureSliceError,
                package.build_history_presolve_input_closure_slice,
            ),
            (
                package,
                package.effective,
                package.PersonaV2HistoryPresolveInputClosureSliceError,
                package.build_history_presolve_input_closure_slice,
            ),
            (
                independent,
                independent.lifecycle,
                independent.PersonaV2HistoryPresolveInputClosureSliceValidationError,
                lambda: independent.validate_history_presolve_input_closure_slice_full(
                    self.value,
                    producer_expected_golden=package._expected_golden(),
                ),
            ),
            (
                independent,
                independent.effective,
                independent.PersonaV2HistoryPresolveInputClosureSliceValidationError,
                lambda: independent.validate_history_presolve_input_closure_slice_full(
                    self.value,
                    producer_expected_golden=package._expected_golden(),
                ),
            ),
        ):
            with self.subTest(module=module.__name__, dependency=dependency.__name__):
                with mock.patch.object(
                    dependency,
                    "ARTIFACT_SCHEMA_VERSION",
                    True,
                ), mock.patch.object(
                    module,
                    "_live_dependency_snapshot",
                    side_effect=AssertionError("dependency provider opened"),
                ) as provider:
                    with self.assertRaises(error_type):
                        call()
                provider.assert_not_called()

        with mock.patch.object(package, "_independent_validator", return_value=None):
            with self.assertRaises(
                package.PersonaV2HistoryPresolveInputClosureSliceError
            ):
                package.canonical_json_bytes(self.value)
            with self.assertRaises(
                package.PersonaV2HistoryPresolveInputClosureSliceError
            ):
                package.validate_history_presolve_input_closure_slice(self.value)

    def test_direct_descriptor_and_artifact_byte_caps_fail_closed(self):
        self.assertEqual(
            self.value["canonical_limits"]["max_direct_descriptor_bytes"],
            package.MAX_DIRECT_DESCRIPTOR_BYTES,
        )
        self.assertLessEqual(
            self.value["summary"]["direct_dependency_canonical_bytes"],
            package.MAX_DIRECT_DESCRIPTOR_BYTES,
        )
        for module, error_type, call in (
            (
                package,
                package.PersonaV2HistoryPresolveInputClosureSliceError,
                lambda: package._build_from_snapshot(
                    package._frozen_dependency_snapshot()
                ),
            ),
            (
                independent,
                independent.PersonaV2HistoryPresolveInputClosureSliceValidationError,
                lambda: independent._validate(
                    self.value,
                    dependency_snapshot_provider=(
                        lambda: independent._frozen_dependency_snapshot()
                    ),
                ),
            ),
        ):
            with mock.patch.object(
                module,
                "MAX_DIRECT_DESCRIPTOR_BYTES",
                module.DIRECT_DEPENDENCY_CANONICAL_BYTES - 1,
            ):
                with self.assertRaises(error_type):
                    call()
            with self.assertRaises(error_type):
                module._require_expected_raw(
                    b"x" * (module.MAX_MANIFEST_BYTES + 1)
                )

    def test_frozen_snapshot_and_built_values_are_detached(self):
        first = package._frozen_dependency_snapshot()
        first["history_coverage"]["persona_count"] = 0
        second = package._frozen_dependency_snapshot()
        self.assertEqual(second["history_coverage"]["persona_count"], 20)

        with _focused_trust_boundaries():
            built = package.build_history_presolve_input_closure_slice()
            built["summary"]["persona_count"] = 0
            rebuilt = package.build_history_presolve_input_closure_slice()
        self.assertEqual(rebuilt["summary"]["persona_count"], 20)


@unittest.skipUnless(
    os.environ.get("KIO_RUN_HISTORY_PRESOLVE_CLOSURE_SLICE_FULL") == "1",
    "set KIO_RUN_HISTORY_PRESOLVE_CLOSURE_SLICE_FULL=1 for all-dependency validation",
)
class PersonaV2HistoryPresolveInputClosureSliceFullTest(unittest.TestCase):
    def test_full_dependency_acceptance(self):
        import resource

        self.assertEqual(
            package._expected_golden(),
            independent._expected_golden(),
        )
        lifecycle_calls = collections.Counter()
        orchestration_calls = collections.Counter()
        projection_calls = collections.Counter()
        original_lifecycle_validator = (
            independent.lifecycle.validate_source_matched_lifecycle_suite_descriptor
        )
        original_namespace_validator = (
            independent.namespace_validator.validate_corpus_semantic_namespace_v3
        )
        original_effective_validator = (
            independent.effective.validate_lifecycle_effective_membership_suite_descriptor
        )
        original_projection_provider = independent.complete.projection_body_provider

        def counted_lifecycle_validator(value):
            lifecycle_calls["suite_validation"] += 1
            return original_lifecycle_validator(value)

        def counted_namespace_validator(*args, **kwargs):
            orchestration_calls["namespace_validation"] += 1
            return original_namespace_validator(*args, **kwargs)

        def counted_effective_validator(value):
            orchestration_calls["effective_validation"] += 1
            return original_effective_validator(value)

        def counted_projection_provider(receipt):
            projection_calls[receipt["receipt_id"]] += 1
            return original_projection_provider(receipt)

        package.effective._canonical_suite_descriptor.cache_clear()
        effective_validator = package.effective._require_independent_validator()
        effective_validator._expected_suite_descriptor.cache_clear()
        started = time.monotonic()
        with mock.patch.object(
            independent.lifecycle,
            "validate_source_matched_lifecycle_suite_descriptor",
            side_effect=counted_lifecycle_validator,
        ), mock.patch.object(
            independent.namespace_validator,
            "validate_corpus_semantic_namespace_v3",
            side_effect=counted_namespace_validator,
        ), mock.patch.object(
            independent.effective,
            "validate_lifecycle_effective_membership_suite_descriptor",
            side_effect=counted_effective_validator,
        ), mock.patch.object(
            independent.complete,
            "projection_body_provider",
            side_effect=counted_projection_provider,
        ):
            value = package.require_full_history_presolve_input_closure_slice()
        raw = package.canonical_json_bytes(value)
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform != "darwin":
            rss *= 1024
        measurement = {
            "canonical_bytes": len(raw),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "effective_validation_count": orchestration_calls[
                "effective_validation"
            ],
            "lifecycle_validation_count": lifecycle_calls["suite_validation"],
            "maximum_rss_bytes": rss,
            "namespace_validation_count": orchestration_calls[
                "namespace_validation"
            ],
            "projection_body_call_count": sum(projection_calls.values()),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "unique_projection_receipt_count": len(projection_calls),
        }
        print(json.dumps(measurement, sort_keys=True))
        self.assertEqual(measurement["namespace_validation_count"], 1)
        self.assertEqual(measurement["effective_validation_count"], 2)
        self.assertEqual(measurement["lifecycle_validation_count"], 3)
        self.assertEqual(measurement["projection_body_call_count"], 506)
        self.assertEqual(measurement["unique_projection_receipt_count"], 253)
        self.assertTrue(all(count == 2 for count in projection_calls.values()))
        self.assertLessEqual(measurement["elapsed_seconds"], 21_600)
        self.assertLessEqual(measurement["maximum_rss_bytes"], 1 * 2**30)
        self.assertLessEqual(len(raw), package.TARGET_MANIFEST_BYTES)
        self.assertEqual(
            (measurement["canonical_bytes"], measurement["sha256"]),
            FROZEN_GOLDEN,
        )


@unittest.skipUnless(
    os.environ.get("KIO_RUN_HISTORY_PRESOLVE_CLOSURE_SLICE_COLD") == "1",
    "set KIO_RUN_HISTORY_PRESOLVE_CLOSURE_SLICE_COLD=1 for two isolated full builds",
)
class PersonaV2HistoryPresolveInputClosureSliceColdTest(unittest.TestCase):
    def test_two_hashseed_full_builds_are_byte_identical(self):
        script = r'''
import collections
import hashlib
import json
import os
import resource
import sys
import time
from unittest import mock
from eval import persona_v2_history_presolve_input_closure_slice as package
from eval import persona_v2_history_presolve_input_closure_slice_validator as independent

if package._expected_golden() != independent._expected_golden():
    raise RuntimeError("producer and validator history pre-solve goldens differ")
started = time.monotonic()
lifecycle_calls = collections.Counter()
orchestration_calls = collections.Counter()
projection_calls = collections.Counter()
original_lifecycle_validator = (
    independent.lifecycle.validate_source_matched_lifecycle_suite_descriptor
)
original_namespace_validator = (
    independent.namespace_validator.validate_corpus_semantic_namespace_v3
)
original_effective_validator = (
    independent.effective.validate_lifecycle_effective_membership_suite_descriptor
)
original_projection_provider = independent.complete.projection_body_provider

def counted_lifecycle_validator(value):
    lifecycle_calls["suite_validation"] += 1
    return original_lifecycle_validator(value)

def counted_namespace_validator(*args, **kwargs):
    orchestration_calls["namespace_validation"] += 1
    return original_namespace_validator(*args, **kwargs)

def counted_effective_validator(value):
    orchestration_calls["effective_validation"] += 1
    return original_effective_validator(value)

def counted_projection_provider(receipt):
    projection_calls[receipt["receipt_id"]] += 1
    return original_projection_provider(receipt)

package.effective._canonical_suite_descriptor.cache_clear()
effective_validator = package.effective._require_independent_validator()
effective_validator._expected_suite_descriptor.cache_clear()
with mock.patch.object(
    independent.lifecycle,
    "validate_source_matched_lifecycle_suite_descriptor",
    side_effect=counted_lifecycle_validator,
), mock.patch.object(
    independent.namespace_validator,
    "validate_corpus_semantic_namespace_v3",
    side_effect=counted_namespace_validator,
), mock.patch.object(
    independent.effective,
    "validate_lifecycle_effective_membership_suite_descriptor",
    side_effect=counted_effective_validator,
), mock.patch.object(
    independent.complete,
    "projection_body_provider",
    side_effect=counted_projection_provider,
):
    value = package.require_full_history_presolve_input_closure_slice()
raw = package.canonical_json_bytes(value)
if lifecycle_calls != {"suite_validation": 3}:
    raise RuntimeError("lifecycle trust-pass cardinality drifted")
if orchestration_calls != {
    "effective_validation": 2,
    "namespace_validation": 1,
}:
    raise RuntimeError("full history dependency orchestration drifted")
if len(projection_calls) != 253 or sum(projection_calls.values()) != 506:
    raise RuntimeError("all-253 two-replay projection cardinality drifted")
if any(count != 2 for count in projection_calls.values()):
    raise RuntimeError("one or more projection bodies were not replayed twice")
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
if sys.platform != "darwin":
    rss *= 1024
print(json.dumps({
    "canonical_bytes": len(raw),
    "effective_validation_count": orchestration_calls["effective_validation"],
    "elapsed_seconds": time.monotonic() - started,
    "lifecycle_validation_count": lifecycle_calls["suite_validation"],
    "maximum_rss_bytes": rss,
    "namespace_validation_count": orchestration_calls["namespace_validation"],
    "projection_body_call_count": sum(projection_calls.values()),
    "python_hash_seed": os.environ.get("PYTHONHASHSEED"),
    "sha256": hashlib.sha256(raw).hexdigest(),
    "unique_projection_receipt_count": len(projection_calls),
}, sort_keys=True))
'''
        measurements = []
        for seed in ("0", "1"):
            environment = dict(os.environ)
            environment.update(
                {
                    "LANG": "C",
                    "LC_ALL": "C",
                    "PYTHONHASHSEED": seed,
                    "TZ": "UTC",
                }
            )
            environment.pop("KIO_RUN_HISTORY_PRESOLVE_CLOSURE_SLICE_COLD", None)
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                env=environment,
                check=True,
                capture_output=True,
                text=True,
                timeout=21_600,
            )
            measurement = json.loads(result.stdout.splitlines()[-1])
            self.assertEqual(measurement["python_hash_seed"], seed)
            self.assertEqual(measurement["namespace_validation_count"], 1)
            self.assertEqual(measurement["effective_validation_count"], 2)
            self.assertEqual(measurement["lifecycle_validation_count"], 3)
            self.assertEqual(measurement["projection_body_call_count"], 506)
            self.assertEqual(measurement["unique_projection_receipt_count"], 253)
            self.assertLessEqual(measurement["elapsed_seconds"], 21_600)
            self.assertLessEqual(measurement["maximum_rss_bytes"], 1 * 2**30)
            self.assertLessEqual(
                measurement["canonical_bytes"], package.TARGET_MANIFEST_BYTES
            )
            measurements.append(measurement)
        print(
            json.dumps(
                {"history_presolve_closure_slice_cold_measurements": measurements},
                sort_keys=True,
            )
        )
        stable_fields = ("canonical_bytes", "sha256")
        self.assertEqual(
            {field: measurements[0][field] for field in stable_fields},
            {field: measurements[1][field] for field in stable_fields},
        )
        for measurement in measurements:
            self.assertEqual(
                (measurement["canonical_bytes"], measurement["sha256"]),
                FROZEN_GOLDEN,
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
