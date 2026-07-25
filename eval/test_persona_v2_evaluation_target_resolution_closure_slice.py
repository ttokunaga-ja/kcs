"""Focused and opt-in acceptance tests for the evaluation closure slice."""

from __future__ import annotations

import ast
import contextlib
import collections
import copy
import hashlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest import mock

try:  # Support package and direct discovery modes.
    from . import persona_v2_evaluation_target_resolution_closure_slice as package
    from . import persona_v2_evaluation_target_resolution_closure_slice_validator as independent
except ImportError:  # pragma: no cover - direct discovery compatibility
    import persona_v2_evaluation_target_resolution_closure_slice as package
    import persona_v2_evaluation_target_resolution_closure_slice_validator as independent


def _producer_snapshot(*, full=False):
    if full:
        raise AssertionError("focused tests must not cross the full trust boundary")
    return package._frozen_dependency_snapshot()


def _independent_snapshot(*, full=False):
    if full:
        raise AssertionError("focused tests must not cross the full trust boundary")
    return independent._frozen_dependency_snapshot()


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


class PersonaV2EvaluationTargetResolutionClosureSliceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.producer_expected_golden = package._expected_golden()
        cls.validator_expected_golden = independent._expected_golden()
        with _focused_trust_boundaries():
            cls.value = package.build_evaluation_target_resolution_closure_slice()
            cls.raw = package.canonical_json_bytes(cls.value)

    def _validate(self, value):
        with _focused_trust_boundaries():
            return independent.validate_evaluation_target_resolution_closure_slice(
                value
            )

    def test_exact_identity_pins_and_compact_commitment(self):
        value = self.value
        self.assertEqual(value["artifact_schema"], package.ARTIFACT_SCHEMA)
        self.assertEqual(value["artifact_schema_version"], 1)
        self.assertLess(len(self.raw), package.TARGET_MANIFEST_BYTES)
        self.assertEqual(
            self.producer_expected_golden,
            self.validator_expected_golden,
        )
        if self.producer_expected_golden is not None:
            self.assertEqual(len(self.raw), self.producer_expected_golden[0])
            self.assertEqual(
                hashlib.sha256(self.raw).hexdigest(),
                self.producer_expected_golden[1],
            )

        pins = value["dependency_pins"]
        self.assertEqual(
            [row["dependency_id"] for row in pins],
            list(package.DIRECT_DEPENDENCY_ORDER),
        )
        self.assertEqual(
            (pins[0]["canonical_bytes"], pins[0]["sha256"]),
            (
                161_665,
                "a8bc67e182ff57b64ae6df0f97bd5be31faf6e5f7b7cfbd0bc3f1ba7bc5cc509",
            ),
        )
        self.assertEqual(
            (pins[1]["canonical_bytes"], pins[1]["sha256"]),
            (
                697_466,
                "6826fb14293e7147159fae1849f93533c35ae76f1beecbd093d190cd6ddd3e69",
            ),
        )
        self.assertEqual(
            (pins[2]["canonical_bytes"], pins[2]["sha256"]),
            (
                4_478_576,
                "4ddf5c98f489586f4cff976de4bea651e07a594f8dd9ac7b96e5ec617a5a88bc",
            ),
        )
        self.assertEqual(
            (pins[3]["canonical_bytes"], pins[3]["sha256"]),
            (
                7_590,
                "47b75b37ceb811e78473bd4f51013f85a95d64167c89e180c417d94620737126",
            ),
        )
        self.assertEqual(
            (pins[4]["canonical_bytes"], pins[4]["sha256"]),
            (
                40_947,
                "890ce6510d9baa4b5faf533cb927bd296f12e289247bb63f88ee2303565af136",
            ),
        )

        transitive = value["transitive_resolution_input_commitment"]
        self.assertEqual(transitive["binding_count"], 60)
        self.assertEqual(transitive["binding_rows_canonical_bytes"], 24_961)
        self.assertEqual(
            transitive["binding_rows_sha256"],
            "d611ac23722a087cefc4051f1b290e6f7cd18dd699ff657a7f92eed05ac9289e",
        )
        self.assertEqual(transitive["cumulative_canonical_bytes"], 7_385_300)
        self.assertFalse(transitive["bodies_embedded"])
        self.assertNotIn("resolution_rows", value)

    def test_atomic_golden_configuration_rejects_partial_and_invalid_pairs(self):
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
            (
                package,
                package.PersonaV2EvaluationTargetResolutionClosureSliceError,
            ),
            (
                independent,
                independent.PersonaV2EvaluationTargetResolutionClosureSliceValidationError,
            ),
        ):
            for byte_count, digest in invalid_pairs:
                with self.subTest(
                    module=module.__name__,
                    byte_count=byte_count,
                    digest=digest,
                ), mock.patch.object(
                    module,
                    "EXPECTED_CANONICAL_BYTES",
                    byte_count,
                ), mock.patch.object(module, "EXPECTED_SHA256", digest):
                    with self.assertRaises(error_type):
                        module._expected_golden()

    def test_partial_golden_fails_all_public_paths_before_heavy_provider(self):
        valid_pair = (len(self.raw), hashlib.sha256(self.raw).hexdigest())
        producer_calls = (
            package.build_evaluation_target_resolution_closure_slice,
            lambda: package.canonical_json_bytes(self.value),
            lambda: package.validate_evaluation_target_resolution_closure_slice(
                self.value
            ),
            lambda: package.evaluation_target_resolution_closure_slice_sha256(
                self.value
            ),
            package.require_full_evaluation_target_resolution_closure_slice,
        )
        validator_calls = (
            lambda: independent.preflight_evaluation_target_resolution_closure_slice(
                self.value
            ),
            lambda: independent.strict_load_canonical_json_bytes(self.raw),
            lambda: independent.validate_evaluation_target_resolution_closure_slice(
                self.value
            ),
            lambda: independent.validate_evaluation_target_resolution_closure_slice_bytes(
                self.raw
            ),
            lambda: independent.validate_evaluation_target_resolution_closure_slice_full(
                self.value,
                producer_expected_golden=None,
            ),
        )
        for byte_count, digest in (
            (valid_pair[0], None),
            (None, valid_pair[1]),
        ):
            with mock.patch.object(
                package,
                "EXPECTED_CANONICAL_BYTES",
                byte_count,
            ), mock.patch.object(
                package,
                "EXPECTED_SHA256",
                digest,
            ), mock.patch.object(
                independent,
                "_live_dependency_snapshot",
                side_effect=AssertionError("heavy provider opened"),
            ) as heavy:
                for call in producer_calls:
                    with self.assertRaises(
                        package.PersonaV2EvaluationTargetResolutionClosureSliceError
                    ):
                        call()
                heavy.assert_not_called()

            with mock.patch.object(
                independent,
                "EXPECTED_CANONICAL_BYTES",
                byte_count,
            ), mock.patch.object(
                independent,
                "EXPECTED_SHA256",
                digest,
            ), mock.patch.object(
                independent,
                "_live_dependency_snapshot",
                side_effect=AssertionError("heavy provider opened"),
            ) as heavy:
                for call in validator_calls:
                    with self.assertRaises(
                        independent.PersonaV2EvaluationTargetResolutionClosureSliceValidationError
                    ):
                        call()
                heavy.assert_not_called()

    def test_valid_but_drifted_golden_fails_public_paths_before_full_provider(self):
        drifted_pair = (len(self.raw) + 1, "0" * 64)
        with mock.patch.object(
            package,
            "EXPECTED_CANONICAL_BYTES",
            drifted_pair[0],
        ), mock.patch.object(
            package,
            "EXPECTED_SHA256",
            drifted_pair[1],
        ), mock.patch.object(
            independent,
            "EXPECTED_CANONICAL_BYTES",
            drifted_pair[0],
        ), mock.patch.object(
            independent,
            "EXPECTED_SHA256",
            drifted_pair[1],
        ), mock.patch.object(
            independent,
            "_live_dependency_snapshot",
            side_effect=AssertionError("heavy provider opened"),
        ) as heavy:
            producer_calls = (
                package.build_evaluation_target_resolution_closure_slice,
                lambda: package.canonical_json_bytes(self.value),
                lambda: package.validate_evaluation_target_resolution_closure_slice(
                    self.value
                ),
                lambda: package.evaluation_target_resolution_closure_slice_sha256(
                    self.value
                ),
                package.require_full_evaluation_target_resolution_closure_slice,
            )
            for call in producer_calls:
                with self.assertRaises(
                    package.PersonaV2EvaluationTargetResolutionClosureSliceError
                ):
                    call()
            validator_calls = (
                lambda: independent.preflight_evaluation_target_resolution_closure_slice(
                    self.value
                ),
                lambda: independent.strict_load_canonical_json_bytes(self.raw),
                lambda: independent.validate_evaluation_target_resolution_closure_slice(
                    self.value
                ),
                lambda: independent.validate_evaluation_target_resolution_closure_slice_bytes(
                    self.raw
                ),
                lambda: independent.validate_evaluation_target_resolution_closure_slice_full(
                    self.value,
                    producer_expected_golden=drifted_pair,
                ),
            )
            for call in validator_calls:
                with self.assertRaises(
                    independent.PersonaV2EvaluationTargetResolutionClosureSliceValidationError
                ):
                    call()
            heavy.assert_not_called()

    def test_mismatched_module_goldens_fail_package_paths_before_provider(self):
        valid_pair = (len(self.raw), hashlib.sha256(self.raw).hexdigest())
        producer_calls = (
            package.build_evaluation_target_resolution_closure_slice,
            lambda: package.canonical_json_bytes(self.value),
            lambda: package.validate_evaluation_target_resolution_closure_slice(
                self.value
            ),
            lambda: package.evaluation_target_resolution_closure_slice_sha256(
                self.value
            ),
            package.require_full_evaluation_target_resolution_closure_slice,
        )
        for producer_pair, validator_pair in (
            (valid_pair, None),
            (None, valid_pair),
        ):
            producer_bytes, producer_digest = (
                (None, None) if producer_pair is None else producer_pair
            )
            validator_bytes, validator_digest = (
                (None, None) if validator_pair is None else validator_pair
            )
            with mock.patch.object(
                package,
                "EXPECTED_CANONICAL_BYTES",
                producer_bytes,
            ), mock.patch.object(
                package,
                "EXPECTED_SHA256",
                producer_digest,
            ), mock.patch.object(
                independent,
                "EXPECTED_CANONICAL_BYTES",
                validator_bytes,
            ), mock.patch.object(
                independent,
                "EXPECTED_SHA256",
                validator_digest,
            ), mock.patch.object(
                independent,
                "_live_dependency_snapshot",
                side_effect=AssertionError("heavy provider opened"),
            ) as heavy:
                for call in producer_calls:
                    with self.assertRaises(
                        package.PersonaV2EvaluationTargetResolutionClosureSliceError
                    ):
                        call()
                with self.assertRaises(
                    independent.PersonaV2EvaluationTargetResolutionClosureSliceValidationError
                ):
                    independent.validate_evaluation_target_resolution_closure_slice_full(
                        self.value,
                        producer_expected_golden=producer_pair,
                    )
                heavy.assert_not_called()

    def test_exact_20_by_105_coverage_and_explicit_unresolved_counts(self):
        value = self.value
        self.assertEqual(len(value["persona_coverage"]), 20)
        self.assertEqual(
            [row["persona_id"] for row in value["persona_coverage"]],
            [f"p{ordinal:02d}" for ordinal in range(1, 21)],
        )
        for row in value["persona_coverage"]:
            self.assertEqual(row["query_capability_mapping_count"], 105)
            self.assertEqual(row["positive_query_count"], 90)
            self.assertEqual(row["negative_query_count"], 15)
            self.assertEqual(row["abstract_distractor_reference_count"], 270)
            self.assertEqual(
                row["required_distinct_distractor_source_count"], 270
            )
            self.assertEqual(row["mapped_distinct_distractor_source_count"], 0)

        target = value["unresolved_target_semantics"]
        self.assertEqual(
            target["baseline_live_join_examined_contributor_target_count"],
            2_000,
        )
        self.assertEqual(
            target["baseline_aligned_contributor_target_count"], 327
        )
        self.assertEqual(
            target["baseline_mismatched_contributor_target_count"], 1_673
        )
        self.assertEqual(
            target["all_condition_exact_resolution_proved_count"], 0
        )
        self.assertEqual(
            target["all_condition_exact_resolution_status"],
            "unknown-not-proved",
        )
        self.assertEqual(
            target["revision_join_unknown_contributor_target_count"],
            2_000,
        )
        self.assertEqual(
            target["checkpoint_selector_effective_membership_compiled_count"],
            0,
        )
        self.assertEqual(target["resolution_target_count"], 2_100)
        self.assertEqual(target["contributor_target_count"], 2_000)
        self.assertEqual(target["incidental_target_count"], 100)
        self.assertFalse(target["query_history_target_resolution_v2_issued"])
        self.assertNotIn("abstract_target_count", target)
        self.assertNotIn(
            "revision_exact_join_unknown_contributor_target_count",
            target,
        )
        self.assertEqual(target["final_source_id_binding_count"], 0)
        self.assertEqual(target["final_materialization_id_binding_count"], 0)
        self.assertEqual(target["compiled_event_id_binding_count"], 0)
        self.assertEqual(target["raw_hash_section_binding_count"], 0)

        distractors = value["unresolved_distractor_sources"]
        self.assertEqual(distractors["abstract_distractor_reference_count"], 5_400)
        self.assertEqual(
            distractors["required_distinct_distractor_source_count_suite"],
            5_400,
        )
        self.assertEqual(distractors["mapped_distinct_distractor_source_count"], 0)
        self.assertEqual(
            distractors[
                "maximum_distinct_distractor_source_candidate_count_before_language_filter"
            ],
            1_060,
        )
        self.assertEqual(
            distractors["maximum_distractor_mapping_shortfall_count"],
            4_340,
        )
        self.assertFalse(distractors["source_mapping_resolved"])
        self.assertFalse(
            distractors[
                "target_primary_companion_distractor_source_domains_disjoint"
            ]
        )

    def test_all_authority_and_done_sensitive_claims_remain_false(self):
        value = self.value
        self.assertTrue(all(flag is False for flag in value["authority"].values()))
        self.assertIn(
            "exact_source_semantic_resolution_available",
            value["authority"],
        )
        self.assertNotIn(
            "effective_source_semantic_mapping_available",
            value["authority"],
        )
        self.assertFalse(value["g0_contract_frozen"])
        for key in (
            "authoritative_corpus_input_closure_bound",
            "compiled_history_event_bindings_present",
            "distractor_source_mapping_resolved",
            "exact_source_semantic_query_history_resolution_bound",
            "final_identity_relevance_present",
            "positive_independent_review_receipt_bound",
            "production_evaluation_input_closure_complete",
            "query_instances_rendered",
            "query_spec_hashed_by_g0",
            "source_fact_equality_proved",
            "source_language_equality_proved",
            "source_topic_equality_proved",
            "target_primary_companion_distractor_disjointness_proved",
        ):
            self.assertFalse(value["completion_claims"][key])
        self.assertTrue(
            value["completion_claims"][
                "request_only_corpus_input_closure_bound"
            ]
        )
        self.assertTrue(
            value["completion_claims"][
                "semantic_resolution_feasibility_audit_bound"
            ]
        )
        self.assertFalse(value["corpus_context_summary"]["namespace_issued"])
        context = value["corpus_context_summary"]
        self.assertTrue(
            context["request_only_corpus_input_closure_candidate_available"]
        )
        self.assertTrue(context["request_only_corpus_input_closure_bound"])
        self.assertFalse(context["request_only_corpus_input_closure_complete"])
        self.assertFalse(
            context["request_only_corpus_input_closure_authoritative"]
        )
        self.assertFalse(context["authoritative_corpus_input_closure_available"])
        self.assertFalse(context["authoritative_corpus_input_closure_bound"])
        self.assertEqual(context["positive_review_receipt_count"], 0)
        self.assertEqual(context["required_positive_review_receipt_count"], 7)
        self.assertEqual(context["active_g0_unresolved_count"], 36)
        self.assertEqual(
            value["missing_required_full_closure_dependencies"],
            [
                "authoritative-corpus-input-closure",
                "query-intent",
                "semantic-oracle",
                "complete-fact-oracle-query-history-manifest",
                "exact-source-semantic-query-history-resolution",
            ],
        )
        self.assertNotIn(
            "positive-independent-review-receipt",
            value["missing_required_full_closure_dependencies"],
        )
        self.assertTrue(
            value["dependency_direction_contract"][
                "positive_review_receipts_are_transitive_authoritative_closure_inputs"
            ]
        )

    def test_independent_validator_accepts_object_bytes_and_hash(self):
        source = inspect.getsource(independent)
        producer_module = (
            "persona_v2_evaluation_target_resolution_closure_slice"
        )
        imported_modules = []
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported_modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_modules.append(node.module)
                imported_modules.extend(alias.name for alias in node.names)
        self.assertFalse(
            any(
                name == producer_module
                or name.endswith(f".{producer_module}")
                for name in imported_modules
            ),
            "independent validator must not import the producer module",
        )
        self.assertTrue(self._validate(self.value))
        with _focused_trust_boundaries():
            self.assertTrue(
                independent.validate_evaluation_target_resolution_closure_slice_bytes(
                    self.raw
                )
            )
            self.assertEqual(
                package.evaluation_target_resolution_closure_slice_sha256(
                    self.value
                ),
                hashlib.sha256(self.raw).hexdigest(),
            )

    def test_declared_upstreams_import_neither_slice_module(self):
        forbidden_modules = (
            "persona_v2_evaluation_target_resolution_closure_slice",
            "persona_v2_evaluation_target_resolution_closure_slice_validator",
        )
        eval_dir = Path(__file__).resolve().parent
        upstream_paths = {
            eval_dir / "persona_v2_corpus_input_closure_v3.py",
            eval_dir / "persona_v2_corpus_input_closure_v3_validator.py",
            eval_dir / "persona_v2_corpus_semantic_namespace_v3.py",
            eval_dir / "persona_v2_corpus_semantic_namespace_v3_validator.py",
            eval_dir / "persona_v2_query_history_target_resolution.py",
            eval_dir / "persona_v2_query_history_target_resolution_validator.py",
            eval_dir
            / "persona_v2_query_history_semantic_resolution_feasibility.py",
            eval_dir
            / "persona_v2_query_history_semantic_resolution_feasibility_validator.py",
            eval_dir / "persona_v2_semantic_projection_complete_inventory.py",
            eval_dir
            / "persona_v2_semantic_projection_complete_inventory_validator.py",
            *eval_dir.glob("persona_v2_*renderer*.py"),
        }
        self.assertTrue(upstream_paths)
        for path in sorted(upstream_paths):
            imported_modules = []
            for node in ast.walk(
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            ):
                if isinstance(node, ast.Import):
                    imported_modules.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imported_modules.append(node.module)
                    imported_modules.extend(alias.name for alias in node.names)
            self.assertFalse(
                any(
                    name == forbidden
                    or name.endswith(f".{forbidden}")
                    for name in imported_modules
                    for forbidden in forbidden_modules
                ),
                f"declared upstream imports an evaluation slice module: {path.name}",
            )

    def test_redundant_nested_dependency_constant_pins_fail_closed_on_drift(self):
        closure_pin = package.corpus_closure.DEPENDENCY_SPECS[
            "corpus-semantic-namespace-v3"
        ]["pin"]
        original = closure_pin["sha256"]
        try:
            closure_pin["sha256"] = "0" * 64
            with self.assertRaises(
                package.PersonaV2EvaluationTargetResolutionClosureSliceError
            ):
                package._frozen_dependency_snapshot()
            with self.assertRaises(
                independent.PersonaV2EvaluationTargetResolutionClosureSliceValidationError
            ):
                independent._frozen_dependency_snapshot()
        finally:
            closure_pin["sha256"] = original

        framing = closure_pin.pop("body_framing")
        try:
            with self.assertRaises(
                package.PersonaV2EvaluationTargetResolutionClosureSliceError
            ):
                package._frozen_dependency_snapshot()
            with self.assertRaises(
                independent.PersonaV2EvaluationTargetResolutionClosureSliceValidationError
            ):
                independent._frozen_dependency_snapshot()
        finally:
            closure_pin["body_framing"] = framing

        feasibility_pin = package.feasibility.DEPENDENCY_PINS[
            "query-history-target-resolution-v1"
        ]
        original = feasibility_pin["canonical_bytes"]
        try:
            feasibility_pin["canonical_bytes"] = original + 1
            with self.assertRaises(
                package.PersonaV2EvaluationTargetResolutionClosureSliceError
            ):
                package._frozen_dependency_snapshot()
            with self.assertRaises(
                independent.PersonaV2EvaluationTargetResolutionClosureSliceValidationError
            ):
                independent._frozen_dependency_snapshot()
        finally:
            feasibility_pin["canonical_bytes"] = original

    def test_transitive_provider_logical_byte_cap_is_enforced(self):
        too_small = package.TRANSITIVE_CUMULATIVE_CANONICAL_BYTES - 1
        with mock.patch.object(
            package,
            "MAX_TRANSITIVE_PROVIDER_BYTES",
            too_small,
        ):
            with self.assertRaises(
                package.PersonaV2EvaluationTargetResolutionClosureSliceError
            ):
                package._transitive_commitment()
        with mock.patch.object(
            independent,
            "MAX_TRANSITIVE_PROVIDER_BYTES",
            too_small,
        ):
            with self.assertRaises(
                independent.PersonaV2EvaluationTargetResolutionClosureSliceValidationError
            ):
                independent._transitive_commitment()

    def test_default_validation_builds_live_dependency_snapshot_once(self):
        with mock.patch.object(
            independent,
            "_live_dependency_snapshot",
            side_effect=_independent_snapshot,
        ) as live_snapshot:
            self.assertTrue(
                independent.validate_evaluation_target_resolution_closure_slice(
                    self.value
                )
            )
        live_snapshot.assert_called_once_with()

    def test_fast_pin_boundary_does_not_open_heavy_dependency_bodies(self):
        with mock.patch.object(
            package.feasibility,
            "build_query_history_semantic_resolution_feasibility_audit",
            side_effect=AssertionError("fast path opened feasibility body"),
        ), mock.patch.object(
            package.corpus_closure,
            "validate_corpus_input_closure_v3",
            side_effect=AssertionError("fast path traversed corpus closure"),
        ):
            self.assertEqual(
                package._live_dependency_snapshot(),
                package._frozen_dependency_snapshot(),
            )
            self.assertEqual(
                independent._live_dependency_snapshot(),
                independent._frozen_dependency_snapshot(),
            )

    def test_authority_completion_pin_and_gap_mutations_fail_closed(self):
        mutations = []

        authority = copy.deepcopy(self.value)
        authority["authority"]["authorizes_g0_freeze"] = True
        mutations.append(authority)

        completion = copy.deepcopy(self.value)
        completion["completion_claims"][
            "production_evaluation_input_closure_complete"
        ] = True
        mutations.append(completion)

        pin = copy.deepcopy(self.value)
        pin["dependency_pins"][2]["sha256"] = "0" * 64
        mutations.append(pin)

        closure_pin = copy.deepcopy(self.value)
        closure_pin["dependency_pins"][3]["canonical_bytes"] += 1
        mutations.append(closure_pin)

        feasibility_pin = copy.deepcopy(self.value)
        feasibility_pin["dependency_pins"][4]["sha256"] = "0" * 64
        mutations.append(feasibility_pin)

        request_only_authority = copy.deepcopy(self.value)
        request_only_authority["corpus_context_summary"][
            "request_only_corpus_input_closure_authoritative"
        ] = True
        mutations.append(request_only_authority)

        authoritative_available = copy.deepcopy(self.value)
        authoritative_available["corpus_context_summary"][
            "authoritative_corpus_input_closure_available"
        ] = True
        mutations.append(authoritative_available)

        measured = copy.deepcopy(self.value)
        measured["unresolved_target_semantics"][
            "baseline_aligned_contributor_target_count"
        ] = 328
        mutations.append(measured)

        feasibility_status = copy.deepcopy(self.value)
        feasibility_status["unresolved_target_semantics"][
            "all_condition_exact_resolution_status"
        ] = "proved"
        mutations.append(feasibility_status)

        mapped = copy.deepcopy(self.value)
        mapped["unresolved_distractor_sources"][
            "mapped_distinct_distractor_source_count"
        ] = 1
        mutations.append(mapped)

        topic = copy.deepcopy(self.value)
        topic["unresolved_target_semantics"][
            "source_topic_equality_proved_count"
        ] = 1
        mutations.append(topic)

        for mutation in mutations:
            with self.assertRaises(
                independent.PersonaV2EvaluationTargetResolutionClosureSliceValidationError
            ):
                self._validate(mutation)
            with self.assertRaises(
                package.PersonaV2EvaluationTargetResolutionClosureSliceError
            ):
                package.canonical_json_bytes(mutation)

    def test_strict_loader_rejects_duplicate_noncanonical_and_oversized_bytes(self):
        with self.assertRaises(
            independent.PersonaV2EvaluationTargetResolutionClosureSliceValidationError
        ):
            independent.strict_load_canonical_json_bytes(
                b'{"artifact_kind":"a","artifact_kind":"b"}'
            )

        noncanonical = self.raw.replace(b'":', b'": ', 1)
        with self.assertRaises(
            independent.PersonaV2EvaluationTargetResolutionClosureSliceValidationError
        ):
            independent.strict_load_canonical_json_bytes(noncanonical)

        with self.assertRaises(
            independent.PersonaV2EvaluationTargetResolutionClosureSliceValidationError
        ):
            independent.strict_load_canonical_json_bytes(
                b"{" + (b" " * independent.MAX_MANIFEST_BYTES) + b"}"
            )

    def test_preflight_rejects_shallow_expanded_and_unicode_bombs_before_provider(self):
        oversized_top_level = {
            f"unexpected_{ordinal}": False for ordinal in range(100_001)
        }
        oversized_nested = copy.deepcopy(self.value)
        oversized_nested["authority"] = {
            f"unexpected_{ordinal}": False for ordinal in range(100_001)
        }
        with mock.patch.object(
            independent,
            "set",
            create=True,
            side_effect=AssertionError("preflight must not copy keys into a set"),
        ), mock.patch.object(
            independent,
            "_live_dependency_snapshot",
            side_effect=AssertionError("dependency provider must not run"),
        ):
            for oversized_object in (oversized_top_level, oversized_nested):
                with self.assertRaises(
                    independent.PersonaV2EvaluationTargetResolutionClosureSliceValidationError
                ):
                    independent.validate_evaluation_target_resolution_closure_slice(
                        oversized_object
                    )
            with self.assertRaises(
                independent.PersonaV2EvaluationTargetResolutionClosureSliceValidationError
            ):
                independent._snapshot_dependencies(lambda: oversized_top_level)

        shallow = copy.deepcopy(self.value)
        shallow["artifact_kind"] = [["shared"] * 100] * 100
        with mock.patch.object(
            independent,
            "_live_dependency_snapshot",
            side_effect=AssertionError("dependency provider must not run"),
        ):
            with self.assertRaises(
                independent.PersonaV2EvaluationTargetResolutionClosureSliceValidationError
            ):
                independent.validate_evaluation_target_resolution_closure_slice(
                    shallow
                )

        expanded = copy.deepcopy(self.value)
        shared_long_string = "x" * 4_096

        def replace_strings(node):
            if type(node) is list:
                for index, item in enumerate(node):
                    if type(item) is str:
                        node[index] = shared_long_string
                    else:
                        replace_strings(item)
            elif type(node) is dict:
                for key, item in node.items():
                    if type(item) is str:
                        node[key] = shared_long_string
                    else:
                        replace_strings(item)

        replace_strings(expanded)
        with mock.patch.object(
            independent,
            "_live_dependency_snapshot",
            side_effect=AssertionError("dependency provider must not run"),
        ):
            with self.assertRaises(
                independent.PersonaV2EvaluationTargetResolutionClosureSliceValidationError
            ):
                independent.validate_evaluation_target_resolution_closure_slice(
                    expanded
                )

        huge_integer = copy.deepcopy(self.value)
        huge_integer["summary"]["persona_count"] = 10**5_000
        with mock.patch.object(
            independent,
            "_live_dependency_snapshot",
            side_effect=AssertionError("dependency provider must not run"),
        ):
            with self.assertRaises(
                independent.PersonaV2EvaluationTargetResolutionClosureSliceValidationError
            ):
                independent.validate_evaluation_target_resolution_closure_slice(
                    huge_integer
                )

        invalid_unicode = copy.deepcopy(self.value)
        invalid_unicode["hypothesis_status"] = "\ud800"
        with mock.patch.object(
            independent,
            "_live_dependency_snapshot",
            side_effect=AssertionError("dependency provider must not run"),
        ):
            with self.assertRaises(
                independent.PersonaV2EvaluationTargetResolutionClosureSliceValidationError
            ):
                independent.validate_evaluation_target_resolution_closure_slice(
                    invalid_unicode
                )

    def test_candidate_and_dependency_toctou_fail_closed(self):
        candidate = copy.deepcopy(self.value)

        def mutate_candidate(_snapshot):
            candidate["summary"]["persona_count"] = 0

        with self.assertRaises(
            independent.PersonaV2EvaluationTargetResolutionClosureSliceValidationError
        ):
            independent._validate(
                candidate,
                dependency_snapshot_provider=_independent_snapshot,
                dependency_observer=mutate_candidate,
            )

        opening = independent._frozen_dependency_snapshot()
        closing = independent._frozen_dependency_snapshot()
        closing["persona_coverage"][0]["positive_query_count"] = 89
        provider = mock.Mock(side_effect=[opening, closing])
        with self.assertRaises(
            independent.PersonaV2EvaluationTargetResolutionClosureSliceValidationError
        ):
            independent._validate(
                self.value,
                dependency_snapshot_provider=provider,
            )

        observed = independent._frozen_dependency_snapshot()

        def mutate_dependency(snapshot):
            snapshot["dependency_pins"][0]["sha256"] = "0" * 64

        with self.assertRaises(
            independent.PersonaV2EvaluationTargetResolutionClosureSliceValidationError
        ):
            independent._validate(
                self.value,
                dependency_snapshot_provider=lambda: copy.deepcopy(observed),
                dependency_observer=mutate_dependency,
            )

    def test_opening_copy_races_fail_closed_before_acceptance(self):
        candidate = copy.deepcopy(self.value)
        original_canonical = independent._canonical
        call_count = 0

        def canonical_then_mutate(value, *, label, maximum=independent.MAX_MANIFEST_BYTES):
            nonlocal call_count
            raw = original_canonical(value, label=label, maximum=maximum)
            call_count += 1
            if call_count == 1:
                candidate["authority"]["authorizes_g0_freeze"] = True
            return raw

        with mock.patch.object(
            independent,
            "_canonical",
            side_effect=canonical_then_mutate,
        ):
            with self.assertRaises(
                package.PersonaV2EvaluationTargetResolutionClosureSliceError
            ):
                package.canonical_json_bytes(candidate)

        opening = independent._frozen_dependency_snapshot()
        original_deepcopy = copy.deepcopy

        def copy_then_mutate(value, memo=None):
            detached = original_deepcopy(value, memo)
            if value is opening:
                opening["persona_coverage"][0]["positive_query_count"] = 89
            return detached

        with mock.patch.object(
            independent.copy,
            "deepcopy",
            side_effect=copy_then_mutate,
        ):
            with self.assertRaises(
                independent.PersonaV2EvaluationTargetResolutionClosureSliceValidationError
            ):
                independent._snapshot_dependencies(lambda: opening)

    def test_hash_target_mutation_and_snapshot_aliasing_fail_closed(self):
        target = copy.deepcopy(self.value)

        def mutate_during_validation(_value):
            target["summary"]["persona_count"] = 0
            return True

        with _focused_trust_boundaries(), mock.patch.object(
            package,
            "validate_evaluation_target_resolution_closure_slice",
            side_effect=mutate_during_validation,
        ):
            with self.assertRaises(
                package.PersonaV2EvaluationTargetResolutionClosureSliceError
            ):
                package.evaluation_target_resolution_closure_slice_sha256(target)

        first = package._frozen_dependency_snapshot()
        first["persona_coverage"][0]["positive_query_count"] = 0
        second = package._frozen_dependency_snapshot()
        self.assertEqual(second["persona_coverage"][0]["positive_query_count"], 90)

        with _focused_trust_boundaries():
            built = package.build_evaluation_target_resolution_closure_slice()
            built["summary"]["persona_count"] = 0
            rebuilt = package.build_evaluation_target_resolution_closure_slice()
        self.assertEqual(rebuilt["summary"]["persona_count"], 20)


@unittest.skipUnless(
    os.environ.get("KCS_RUN_EVALUATION_CLOSURE_SLICE_FULL") == "1",
    "set KCS_RUN_EVALUATION_CLOSURE_SLICE_FULL=1 for all-dependency validation",
)
class PersonaV2EvaluationTargetResolutionClosureSliceFullTest(unittest.TestCase):
    def test_full_dependency_acceptance(self):
        import resource

        self.assertEqual(
            package._expected_golden(),
            independent._expected_golden(),
        )
        started = time.monotonic()
        projection_calls = collections.Counter()
        direct_reads = collections.Counter()
        orchestration_calls = collections.Counter()
        original_provider = package.complete.projection_body_provider
        original_direct_provider = (
            package.corpus_closure._current_dependency_body
        )
        original_target_validator = (
            independent.resolution_validator.validate_query_history_target_resolution
        )
        original_feasibility_producer = package.feasibility._load_actual_snapshot
        original_feasibility_validator = (
            independent.feasibility_validator._load_actual_snapshot
        )

        def counted_provider(receipt):
            projection_calls[receipt["receipt_id"]] += 1
            return original_provider(receipt)

        def counted_direct_provider(dependency_id):
            direct_reads[dependency_id] += 1
            return original_direct_provider(dependency_id)

        def counted_target_validator(value):
            orchestration_calls["target_resolution_validation"] += 1
            return original_target_validator(value)

        def counted_feasibility_producer():
            orchestration_calls["feasibility_producer_actual"] += 1
            return original_feasibility_producer()

        def counted_feasibility_validator():
            orchestration_calls["feasibility_independent_actual"] += 1
            return original_feasibility_validator()

        package.feasibility._cached_raw.cache_clear()
        package.corpus_closure._canonical_candidate_raw.cache_clear()
        package.corpus_closure._canonical_dependency_snapshot.cache_clear()
        with mock.patch.object(
            package.complete,
            "projection_body_provider",
            side_effect=counted_provider,
        ), mock.patch.object(
            package.corpus_closure,
            "_current_dependency_body",
            side_effect=counted_direct_provider,
        ), mock.patch.object(
            independent.resolution_validator,
            "validate_query_history_target_resolution",
            side_effect=counted_target_validator,
        ), mock.patch.object(
            package.feasibility,
            "_load_actual_snapshot",
            side_effect=counted_feasibility_producer,
        ), mock.patch.object(
            independent.feasibility_validator,
            "_load_actual_snapshot",
            side_effect=counted_feasibility_validator,
        ):
            value = package.require_full_evaluation_target_resolution_closure_slice()
        raw = package.canonical_json_bytes(value)
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform != "darwin":
            rss *= 1024
        measurement = {
            "canonical_bytes": len(raw),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "maximum_rss_bytes": rss,
            "direct_dependency_read_count": sum(direct_reads.values()),
            "feasibility_independent_actual_count": orchestration_calls[
                "feasibility_independent_actual"
            ],
            "feasibility_producer_actual_count": orchestration_calls[
                "feasibility_producer_actual"
            ],
            "projection_body_call_count": sum(projection_calls.values()),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "target_resolution_validation_count": orchestration_calls[
                "target_resolution_validation"
            ],
            "unique_direct_dependency_count": len(direct_reads),
            "unique_projection_receipt_count": len(projection_calls),
        }
        print(json.dumps(measurement, sort_keys=True))
        self.assertEqual(measurement["projection_body_call_count"], 506)
        self.assertEqual(measurement["unique_projection_receipt_count"], 253)
        self.assertTrue(all(count == 2 for count in projection_calls.values()))
        self.assertEqual(measurement["direct_dependency_read_count"], 8)
        self.assertEqual(measurement["unique_direct_dependency_count"], 4)
        self.assertTrue(all(count == 2 for count in direct_reads.values()))
        self.assertEqual(measurement["target_resolution_validation_count"], 1)
        self.assertEqual(measurement["feasibility_producer_actual_count"], 1)
        self.assertEqual(
            measurement["feasibility_independent_actual_count"], 1
        )
        self.assertLessEqual(measurement["elapsed_seconds"], 7_200)
        self.assertLessEqual(measurement["maximum_rss_bytes"], 1 * 2**30)
        self.assertLessEqual(len(raw), package.TARGET_MANIFEST_BYTES)
        if package.EXPECTED_CANONICAL_BYTES is not None:
            self.assertEqual(
                measurement["canonical_bytes"], package.EXPECTED_CANONICAL_BYTES
            )
        if package.EXPECTED_SHA256 is not None:
            self.assertEqual(measurement["sha256"], package.EXPECTED_SHA256)


@unittest.skipUnless(
    os.environ.get("KCS_RUN_EVALUATION_CLOSURE_SLICE_COLD") == "1",
    "set KCS_RUN_EVALUATION_CLOSURE_SLICE_COLD=1 for two isolated full builds",
)
class PersonaV2EvaluationTargetResolutionClosureSliceColdTest(unittest.TestCase):
    def test_two_hashseed_full_builds_are_byte_identical(self):
        self.assertEqual(
            package._expected_golden(),
            independent._expected_golden(),
        )
        script = r'''
import collections
import hashlib
import json
import os
import resource
import sys
import time
from unittest import mock
from eval import persona_v2_evaluation_target_resolution_closure_slice as package
from eval import persona_v2_evaluation_target_resolution_closure_slice_validator as independent

if package._expected_golden() != independent._expected_golden():
    raise RuntimeError("producer and validator evaluation closure goldens differ")
started = time.monotonic()
projection_calls = collections.Counter()
direct_reads = collections.Counter()
orchestration_calls = collections.Counter()
original_provider = package.complete.projection_body_provider
original_direct_provider = package.corpus_closure._current_dependency_body
original_target_validator = (
    independent.resolution_validator.validate_query_history_target_resolution
)
original_feasibility_producer = package.feasibility._load_actual_snapshot
original_feasibility_validator = independent.feasibility_validator._load_actual_snapshot

def counted_provider(receipt):
    projection_calls[receipt["receipt_id"]] += 1
    return original_provider(receipt)

def counted_direct_provider(dependency_id):
    direct_reads[dependency_id] += 1
    return original_direct_provider(dependency_id)

def counted_target_validator(value):
    orchestration_calls["target_resolution_validation"] += 1
    return original_target_validator(value)

def counted_feasibility_producer():
    orchestration_calls["feasibility_producer_actual"] += 1
    return original_feasibility_producer()

def counted_feasibility_validator():
    orchestration_calls["feasibility_independent_actual"] += 1
    return original_feasibility_validator()

package.feasibility._cached_raw.cache_clear()
package.corpus_closure._canonical_candidate_raw.cache_clear()
package.corpus_closure._canonical_dependency_snapshot.cache_clear()
with mock.patch.object(
    package.complete,
    "projection_body_provider",
    side_effect=counted_provider,
), mock.patch.object(
    package.corpus_closure,
    "_current_dependency_body",
    side_effect=counted_direct_provider,
), mock.patch.object(
    independent.resolution_validator,
    "validate_query_history_target_resolution",
    side_effect=counted_target_validator,
), mock.patch.object(
    package.feasibility,
    "_load_actual_snapshot",
    side_effect=counted_feasibility_producer,
), mock.patch.object(
    independent.feasibility_validator,
    "_load_actual_snapshot",
    side_effect=counted_feasibility_validator,
):
    value = package.require_full_evaluation_target_resolution_closure_slice()
raw = package.canonical_json_bytes(value)
if len(projection_calls) != 253 or sum(projection_calls.values()) != 506:
    raise RuntimeError("all-253 two-replay call cardinality drifted")
if any(count != 2 for count in projection_calls.values()):
    raise RuntimeError("one or more projection bodies were not replayed twice")
if len(direct_reads) != 4 or sum(direct_reads.values()) != 8:
    raise RuntimeError("request-only closure direct read cardinality drifted")
if any(count != 2 for count in direct_reads.values()):
    raise RuntimeError("one or more request-only closure bodies lacked two reads")
if orchestration_calls != {
    "target_resolution_validation": 1,
    "feasibility_producer_actual": 1,
    "feasibility_independent_actual": 1,
}:
    raise RuntimeError("full evaluation dependency orchestration drifted")
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
if sys.platform != "darwin":
    rss *= 1024
print(json.dumps({
    "canonical_bytes": len(raw),
    "direct_dependency_read_count": sum(direct_reads.values()),
    "elapsed_seconds": time.monotonic() - started,
    "feasibility_independent_actual_count": orchestration_calls["feasibility_independent_actual"],
    "feasibility_producer_actual_count": orchestration_calls["feasibility_producer_actual"],
    "maximum_rss_bytes": rss,
    "projection_body_call_count": sum(projection_calls.values()),
    "python_hash_seed": os.environ.get("PYTHONHASHSEED"),
    "sha256": hashlib.sha256(raw).hexdigest(),
    "target_resolution_validation_count": orchestration_calls["target_resolution_validation"],
    "unique_direct_dependency_count": len(direct_reads),
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
            environment.pop("KCS_RUN_EVALUATION_CLOSURE_SLICE_COLD", None)
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                env=environment,
                check=True,
                capture_output=True,
                text=True,
                timeout=7_200,
            )
            measurement = json.loads(result.stdout.splitlines()[-1])
            self.assertEqual(measurement["python_hash_seed"], seed)
            self.assertEqual(measurement["projection_body_call_count"], 506)
            self.assertEqual(measurement["unique_projection_receipt_count"], 253)
            self.assertEqual(measurement["direct_dependency_read_count"], 8)
            self.assertEqual(measurement["unique_direct_dependency_count"], 4)
            self.assertEqual(
                measurement["target_resolution_validation_count"], 1
            )
            self.assertEqual(
                measurement["feasibility_producer_actual_count"], 1
            )
            self.assertEqual(
                measurement["feasibility_independent_actual_count"], 1
            )
            self.assertLessEqual(measurement["elapsed_seconds"], 7_200)
            self.assertLessEqual(measurement["maximum_rss_bytes"], 1 * 2**30)
            self.assertLessEqual(
                measurement["canonical_bytes"], package.TARGET_MANIFEST_BYTES
            )
            measurements.append(measurement)
        print(
            json.dumps(
                {"evaluation_closure_slice_cold_measurements": measurements},
                sort_keys=True,
            )
        )
        stable_fields = ("canonical_bytes", "sha256")
        self.assertEqual(
            {field: measurements[0][field] for field in stable_fields},
            {field: measurements[1][field] for field in stable_fields},
        )
        if package.EXPECTED_CANONICAL_BYTES is not None:
            self.assertEqual(
                measurements[0]["canonical_bytes"],
                package.EXPECTED_CANONICAL_BYTES,
            )
        if package.EXPECTED_SHA256 is not None:
            self.assertEqual(measurements[0]["sha256"], package.EXPECTED_SHA256)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
