"""Focused tests for abstract query/history target resolution."""

from __future__ import annotations

import copy
import hashlib
import inspect
import unittest
from unittest import mock

try:  # Support package and direct discovery modes.
    from . import persona_v2_query_history_target_resolution as resolution
    from . import persona_v2_query_history_target_resolution_validator as independent
except ImportError:  # pragma: no cover - direct discovery compatibility
    import persona_v2_query_history_target_resolution as resolution
    import persona_v2_query_history_target_resolution_validator as independent


class PersonaV2QueryHistoryTargetResolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = resolution.build_query_history_target_resolution()
        cls.raw = resolution.canonical_json_bytes(cls.value)

    def test_exact_all_persona_bijection_and_counts(self):
        value = self.value
        self.assertEqual(
            value["artifact_schema"],
            "kcs.persona.pc-query-history-target-resolution/v1",
        )
        self.assertEqual(value["summary"]["persona_count"], 20)
        self.assertEqual(value["summary"]["query_capability_bijection_count"], 2_100)
        self.assertEqual(value["summary"]["positive_query_count"], 1_800)
        self.assertEqual(value["summary"]["negative_query_count"], 300)
        self.assertEqual(value["summary"]["abstract_companion_binding_count"], 200)
        self.assertEqual(
            value["summary"]["abstract_distractor_reference_count"], 5_400
        )
        self.assertEqual(value["summary"]["distinct_distractor_source_count"], 0)
        self.assertFalse(
            value["completion_claims"]["distractor_source_mapping_resolved"]
        )
        self.assertFalse(
            value["completion_claims"][
                "target_primary_companion_and_distractor_source_intents_disjoint"
            ]
        )
        self.assertEqual(len(value["input_bindings"]), 60)
        self.assertEqual(len(value["resolution_rows"]), 2_100)
        self.assertEqual(len(self.raw), 4_478_576)
        self.assertEqual(
            hashlib.sha256(self.raw).hexdigest(),
            "4ddf5c98f489586f4cff976de4bea651e07a594f8dd9ac7b96e5ec617a5a88bc",
        )
        self.assertEqual(resolution.EXPECTED_CANONICAL_BYTES, 4_478_576)
        self.assertEqual(independent.EXPECTED_CANONICAL_BYTES, 4_478_576)
        self.assertEqual(
            resolution.EXPECTED_SHA256,
            "4ddf5c98f489586f4cff976de4bea651e07a594f8dd9ac7b96e5ec617a5a88bc",
        )
        self.assertEqual(
            independent.EXPECTED_SHA256,
            "4ddf5c98f489586f4cff976de4bea651e07a594f8dd9ac7b96e5ec617a5a88bc",
        )
        self.assertEqual(
            len({row["query_key"] for row in value["resolution_rows"]}),
            2_100,
        )
        self.assertEqual(
            len(
                {
                    (row["persona_id"], row["lifecycle_binding"]["capability_key"])
                    for row in value["resolution_rows"]
                }
            ),
            2_100,
        )
        self.assertTrue(all(flag is False for flag in value["authority"].values()))

    def test_semantic_rules_not_ordinal_zip_and_pending_gap_are_explicit(self):
        value = self.value
        self.assertFalse(value["resolution_contract"]["ordinal_zip_allowed"])
        self.assertEqual(
            value["resolution_contract"]["matching_algorithm"],
            resolution.MATCHING_ALGORITHM,
        )
        rows = value["resolution_rows"]
        replacements = [
            row
            for row in rows
            if row["lifecycle_binding"]["capability_class_key"].startswith(
                "replacement-current-"
            )
        ]
        self.assertEqual(len(replacements), 60)
        self.assertTrue(
            all(
                row["abstract_answer_contract"]["expected_revision_chain_ids"]
                for row in replacements
            )
        )
        edited_moves = [
            row
            for row in rows
            if row["lifecycle_binding"]["capability_class_key"]
            == "w1-edited-cross-scope-move"
        ]
        self.assertEqual(len(edited_moves), 20)
        self.assertTrue(
            all(
                row["oracle_evidence"]["operation_kind"]
                == "searchable-cross-scope-move"
                and row["abstract_answer_contract"]["expected_revision_chain_ids"]
                for row in edited_moves
            )
        )
        self.assertFalse(
            value["completion_claims"]["effective_source_fact_membership_resolved"]
        )
        self.assertFalse(
            value["completion_claims"]["source_topic_language_fact_equality_proved"]
        )
        self.assertTrue(
            all(
                not row["resolution_status"]["effective_fact_membership_present"]
                and not row["resolution_status"][
                    "source_topic_language_fact_equality_proved"
                ]
                for row in rows
            )
        )

    def test_target_companion_and_distractor_disjointness(self):
        rows = self.value["resolution_rows"]
        target_intents = {
            row["abstract_target"]["intent_key"] for row in rows
        }
        target_documents = {
            row["abstract_target"]["logical_document_key"] for row in rows
        }
        distractor_intents = {
            key
            for row in rows
            for key in row["distractor_contract"]["distractor_intent_keys"]
        }
        distractor_documents = {
            key
            for row in rows
            for key in row["distractor_contract"][
                "distractor_logical_document_keys"
            ]
        }
        self.assertTrue(target_intents.isdisjoint(distractor_intents))
        self.assertTrue(target_documents.isdisjoint(distractor_documents))
        companion_rows = [
            row
            for row in rows
            if row["lifecycle_binding"]["companion"]["status"]
            == "source-matched-abstract-companion"
        ]
        self.assertEqual(len(companion_rows), 200)
        self.assertTrue(
            all(
                row["lifecycle_binding"]["primary_source_intent_key"]
                != row["lifecycle_binding"]["companion"]["source_intent_key"]
                for row in companion_rows
            )
        )
        lifecycle_source_intents = {
            row["lifecycle_binding"]["primary_source_intent_key"] for row in rows
        } | {
            row["lifecycle_binding"]["companion"]["source_intent_key"]
            for row in companion_rows
        }
        self.assertTrue(target_intents.isdisjoint(lifecycle_source_intents))
        for row in rows:
            self.assertTrue(
                set(row["abstract_answer_contract"]["expected_fact_ids"]).isdisjoint(
                    row["distractor_contract"]["distractor_fact_ids"]
                )
            )
            self.assertFalse(
                row["distractor_contract"]["source_mapping_resolved"]
            )
            self.assertEqual(
                row["distractor_contract"]["mapped_source_intent_keys"], []
            )

    def test_independent_validator_accepts_object_and_canonical_bytes(self):
        self.assertNotIn(
            "import persona_v2_query_history_target_resolution as",
            inspect.getsource(independent),
        )
        self.assertTrue(
            independent.validate_query_history_target_resolution(self.value)
        )
        self.assertTrue(
            independent.validate_query_history_target_resolution_bytes(self.raw)
        )
        self.assertEqual(
            resolution.query_history_target_resolution_sha256(self.value),
            resolution.query_history_target_resolution_sha256(),
        )

    def test_mutations_fail_closed_without_echoing_query_canary(self):
        mutated = copy.deepcopy(self.value)
        mutated["resolution_rows"][0]["query_key"] = "QUERY-CANARY-DO-NOT-ECHO"
        with self.assertRaises(
            independent.PersonaV2QueryHistoryTargetResolutionValidationError
        ) as caught:
            independent.validate_query_history_target_resolution(mutated)
        self.assertNotIn("QUERY-CANARY", str(caught.exception))

        authority = copy.deepcopy(self.value)
        authority["authority"]["authorizes_g0_freeze"] = True
        with self.assertRaises(
            independent.PersonaV2QueryHistoryTargetResolutionValidationError
        ):
            independent.validate_query_history_target_resolution(authority)
        with self.assertRaises(
            resolution.PersonaV2QueryHistoryTargetResolutionError
        ):
            resolution.canonical_json_bytes(authority)
        with self.assertRaises(
            resolution.PersonaV2QueryHistoryTargetResolutionError
        ):
            resolution.validate_query_history_target_resolution(authority)

        concrete = copy.deepcopy(self.value)
        concrete["resolution_rows"][0]["final_source_id"] = "forbidden"
        with self.assertRaises(
            independent.PersonaV2QueryHistoryTargetResolutionValidationError
        ):
            independent.validate_query_history_target_resolution(concrete)

    def test_strict_parser_rejects_duplicate_and_noncanonical_json(self):
        with self.assertRaises(
            independent.PersonaV2QueryHistoryTargetResolutionValidationError
        ):
            independent.strict_load_canonical_json_bytes(
                b'{"artifact_kind":"a","artifact_kind":"b"}'
            )
        with self.assertRaises(
            independent.PersonaV2QueryHistoryTargetResolutionValidationError
        ):
            independent.strict_load_canonical_json_bytes(b'{"x": 1}')
        with self.assertRaises(
            independent.PersonaV2QueryHistoryTargetResolutionValidationError
        ):
            independent.strict_load_canonical_json_bytes(
                (b"[" * 2_000) + (b"]" * 2_000)
            )

    def test_preflight_rejects_shallow_and_expanded_bombs_before_dependencies(self):
        shallow = copy.deepcopy(self.value)
        shared = ["shared"] * 100
        shallow["artifact_kind"] = [shared] * 100
        with mock.patch.object(
            independent.query_intent,
            "build_query_intent_suite",
            side_effect=AssertionError("dependency provider must not run"),
        ):
            with self.assertRaises(
                independent.PersonaV2QueryHistoryTargetResolutionValidationError
            ):
                independent.validate_query_history_target_resolution(shallow)

        expanded = copy.deepcopy(self.value)
        shared_long_string = "x" * 4_096
        for row in expanded["resolution_rows"]:
            if row["distractor_contract"]["distractor_fact_ids"]:
                row["distractor_contract"]["distractor_fact_ids"] = [
                    shared_long_string
                ] * 3
                row["distractor_contract"]["distractor_intent_keys"] = [
                    shared_long_string
                ] * 3
                row["distractor_contract"]["distractor_logical_document_keys"] = [
                    shared_long_string
                ] * 3
        with mock.patch.object(
            independent.query_intent,
            "build_query_intent_suite",
            side_effect=AssertionError("dependency provider must not run"),
        ):
            with self.assertRaises(
                independent.PersonaV2QueryHistoryTargetResolutionValidationError
            ):
                independent.validate_query_history_target_resolution(expanded)

        invalid_utf8 = copy.deepcopy(self.value)
        invalid_utf8["resolution_rows"][0]["query_key"] = "\ud800"
        with mock.patch.object(
            independent.query_intent,
            "build_query_intent_suite",
            side_effect=AssertionError("dependency provider must not run"),
        ):
            with self.assertRaises(
                independent.PersonaV2QueryHistoryTargetResolutionValidationError
            ):
                independent.validate_query_history_target_resolution(invalid_utf8)

    def test_preflight_normalizes_runtime_mutation_errors(self):
        with mock.patch.object(
            independent,
            "_preflight_shallow_schema",
            side_effect=RuntimeError("UNTRUSTED-RUNTIME-CANARY"),
        ):
            with self.assertRaises(
                independent.PersonaV2QueryHistoryTargetResolutionValidationError
            ) as caught:
                independent.preflight_query_history_target_resolution(self.value)
        self.assertNotIn("UNTRUSTED-RUNTIME-CANARY", str(caught.exception))

    def test_value_and_hash_target_mutation_toctou_fail_closed(self):
        value = copy.deepcopy(self.value)

        def mutate_value(_queries, _oracles, _lifecycles):
            value["resolution_rows"][0]["abstract_target"]["intent_key"] = (
                "mutated-target-during-validation"
            )

        with self.assertRaises(
            independent.PersonaV2QueryHistoryTargetResolutionValidationError
        ):
            independent._validate(value, dependency_observer=mutate_value)

        hash_value = copy.deepcopy(self.value)

        def mutate_during_hash(_detached):
            hash_value["resolution_rows"][0]["abstract_target"]["intent_key"] = (
                "mutated-target-during-hash"
            )
            return True

        with mock.patch.object(
            resolution,
            "validate_query_history_target_resolution",
            side_effect=mutate_during_hash,
        ):
            with self.assertRaises(
                resolution.PersonaV2QueryHistoryTargetResolutionError
            ):
                resolution.query_history_target_resolution_sha256(hash_value)

    def test_only_immutable_bytes_are_cached_and_builds_are_detached(self):
        cached = resolution._cached_canonical_raw()
        self.assertIs(type(cached), bytes)
        trusted = independent._trusted_dependency_raws()
        self.assertIs(type(trusted), tuple)
        self.assertTrue(
            all(
                type(group) is tuple and all(type(raw) is bytes for raw in group)
                for group in trusted
            )
        )
        first = resolution.build_query_history_target_resolution()
        first["summary"]["persona_count"] = 0
        second = resolution.build_query_history_target_resolution()
        self.assertEqual(second["summary"]["persona_count"], 20)

    def test_dependency_observer_mutation_is_detected(self):
        def mutate(queries, _oracles, _lifecycles):
            queries[0]["positive_query_intents"][0]["language"] = "zz"

        with self.assertRaises(resolution.PersonaV2QueryHistoryTargetResolutionError):
            resolution._build_query_history_target_resolution(
                dependency_observer=mutate
            )
        with self.assertRaises(
            independent.PersonaV2QueryHistoryTargetResolutionValidationError
        ):
            independent._validate(self.value, dependency_observer=mutate)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
