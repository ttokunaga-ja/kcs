"""Focused tests for the non-authorizing chunk-accounting sidecar."""

from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import unittest
from unittest import mock

from eval import persona_v2_chunk_accounting as accounting
from eval import persona_v2_chunk_accounting_validator as validator
from eval import persona_v2_contract as envelope
from eval import persona_v2_overlay_contract as overlay


class PersonaV2ChunkAccountingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = accounting.build_chunk_accounting_contract()
        cls.envelope = envelope.build_envelope_contract()
        cls.overlay = overlay.build_overlay_contract()

    def _independent_validate(self, body=None, envelope_value=None, overlay_value=None):
        return validator.validate_chunk_accounting_contract(
            copy.deepcopy(self.body if body is None else body),
            envelope_value=copy.deepcopy(
                self.envelope if envelope_value is None else envelope_value
            ),
            overlay_contract_value=copy.deepcopy(
                self.overlay if overlay_value is None else overlay_value
            ),
        )

    def _assert_rehashed_semantic_rejection(self, mutate):
        tampered = copy.deepcopy(self.body)
        mutate(tampered)
        raw = accounting.canonical_json_bytes(tampered)
        with (
            mock.patch.object(
                validator,
                "EXPECTED_ACCOUNTING_CANONICAL_BYTES",
                len(raw),
            ),
            mock.patch.object(
                validator,
                "EXPECTED_ACCOUNTING_SHA256",
                hashlib.sha256(raw).hexdigest(),
            ),
            mock.patch.object(
                validator,
                "_validate_dependency_snapshots",
                return_value=None,
            ),
        ):
            with self.assertRaises(
                validator.PersonaV2ChunkAccountingValidationError
            ):
                self._independent_validate(tampered)

    def test_canonical_pin_and_both_validation_entry_points(self):
        raw = accounting.canonical_json_bytes(self.body)
        self.assertEqual(len(raw), validator.EXPECTED_ACCOUNTING_CANONICAL_BYTES)
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(),
            validator.EXPECTED_ACCOUNTING_SHA256,
        )
        self.assertNotIn(validator.EXPECTED_ACCOUNTING_SHA256.encode(), raw)
        self.assertTrue(accounting.validate_chunk_accounting_contract(self.body))
        self.assertTrue(self._independent_validate())

    def test_minimal_frozen_input_bindings_are_exact(self):
        self.assertEqual(
            self.body["input_binding_order"],
            ["persona-v2-envelope", "persona-v2-overlay-contract"],
        )
        self.assertEqual(len(self.body["input_bindings"]), 2)
        actual = {
            row["name"]: (row["canonical_bytes"], row["sha256"])
            for row in self.body["input_bindings"]
        }
        self.assertEqual(actual, validator.EXPECTED_DEPENDENCY_PINS)
        self.assertEqual(
            [row["dependency_role"] for row in self.body["input_bindings"]],
            [
                "numeric-checkpoint-cap-and-persona-owner",
                "scope-qualified-accounting-duplicate-and-recall-owner",
            ],
        )

    def test_four_metric_domains_and_state_partition_are_separate(self):
        self.assertEqual(self.body["metric_order"], list(validator.METRIC_ORDER))
        metrics = {
            row["metric_id"]: row for row in self.body["metric_contracts"]
        }
        self.assertEqual(len(metrics), 4)
        self.assertEqual(
            metrics["search-semantic-endpoint-v1"]["identity_fields_observed"],
            ["scope_id", "chunk_id"],
        )
        self.assertTrue(
            metrics["search-semantic-endpoint-v1"]["chunk_id_is_chunk_hash"]
        )
        self.assertEqual(
            metrics["persona-global-chunk-hash-v1"]["identity_fields"],
            ["chunk_id"],
        )
        self.assertEqual(
            metrics["history-path-binding-v1"]["identity_fields_observed"],
            ["scope_id", "chunk_id", "path"],
        )
        self.assertEqual(
            set(
                metrics["physical-storage-v1"]["identities_by_projection"]
            ),
            {
                "chunk-cas-object",
                "managed-source-materialization",
                "raw-cas-object",
            },
        )
        state = self.body["state_partition_contract"]
        self.assertTrue(
            state[
                "current_and_history_only_are_disjoint_within_each_participation_class"
            ]
        )
        self.assertTrue(
            state["contract_and_incidental_endpoint_sets_must_be_disjoint"]
        )
        self.assertTrue(state["history_liveness_is_scope_local_not_persona_global"])

    def test_checkpoint_literals_move_projection_and_cap_inequality(self):
        full_expected = [
            ("W0", 120_000, 0, 0),
            ("W1", 120_000, 24_000, 0),
            ("W2", 120_000, 24_000, 1),
            ("W3", 120_000, 48_000, 1),
            ("W4", 120_000, 60_000, 1),
            ("W5-pre-purge", 124_800, 64_800, 1),
            ("W5-final", 120_000, 60_000, 1),
        ]
        for profile, divisor in (("pilot", 10), ("full", 1)):
            rows = self.body["checkpoint_contract"]["profiles"][profile]
            self.assertEqual(
                [
                    (
                        row["checkpoint"],
                        row["current_contract_semantic_endpoints"],
                        row["history_only_contract_semantic_endpoints"],
                        row["incidental_move_history_multiplier"],
                    )
                    for row in rows
                ],
                [
                    (checkpoint, current // divisor, history // divisor, multiplier)
                    for checkpoint, current, history, multiplier in full_expected
                ],
            )
        self.assertEqual(
            self.body["incidental_move_cap_proof"],
            [
                {
                    "incidental_current_upper_bound": 1020,
                    "incidental_total_upper_bound": 2040,
                    "move_history_upper_bound": 350,
                    "profile": "pilot",
                    "proof_checkpoint": "W5-pre-purge",
                    "required_headroom_after_worst_case_move": 670,
                    "worst_case_current_plus_move_history": 1370,
                    "worst_case_satisfies_total_cap": True,
                },
                {
                    "incidental_current_upper_bound": 10200,
                    "incidental_total_upper_bound": 20400,
                    "move_history_upper_bound": 350,
                    "profile": "full",
                    "proof_checkpoint": "W5-pre-purge",
                    "required_headroom_after_worst_case_move": 9850,
                    "worst_case_current_plus_move_history": 10550,
                    "worst_case_satisfies_total_cap": True,
                },
            ],
        )

    def test_move_qim_and_cross_metric_delta_table(self):
        move = self.body["move_anchor_contract"]
        self.assertEqual(move["incidental_move_anchor_count"], 5)
        self.assertEqual(
            (
                move["per_source_actual_chunk_inclusive_minimum"],
                move["per_source_actual_chunk_inclusive_maximum"],
                move["qIM_inclusive_minimum"],
                move["qIM_inclusive_maximum"],
            ),
            (1, 70, 5, 350),
        )
        self.assertEqual(
            sum(move["anonymous_capability_reclassification"].values()), 105
        )
        operation = next(
            row
            for row in self.body["operation_delta_contracts"]
            if row["operation_id"] == "cross-scope-move-incidental"
        )
        terms = {
            (row["metric_id"], row["projection"]): (
                row["direction"],
                row["coefficient"],
                row["symbol"],
            )
            for row in operation["delta_terms"]
        }
        self.assertEqual(
            terms[
                ("search-semantic-endpoint-v1", "incidental-history-only")
            ],
            ("increase", 1, "qIM"),
        )
        self.assertEqual(
            terms[("persona-global-chunk-hash-v1", "distinct-chunk-hashes")],
            ("preserve", 0, "zero"),
        )
        self.assertEqual(
            terms[("history-path-binding-v1", "reachable-path-bindings")],
            ("increase", 1, "qIM"),
        )
        self.assertEqual(
            terms[("physical-storage-v1", "raw-cas-regular-objects")],
            ("increase", 1, "nIM"),
        )
        self.assertEqual(
            terms[("physical-storage-v1", "chunk-cas-regular-objects")],
            ("increase", 1, "qIM"),
        )
        self.assertIn(
            "all-planned-destination-scope-chunk-endpoints-are-pairwise-distinct",
            operation["preconditions"],
        )
        self.assertIn(
            "all-planned-destination-scope-path-materializations-are-pairwise-distinct",
            operation["preconditions"],
        )
        self.assertIn(
            "each-destination-scope-path-has-no-live-materialization-before-its-move",
            operation["preconditions"],
        )

    def test_duplicate_and_rename_deltas_do_not_cross_metric_collapse(self):
        operations = {
            row["operation_id"]: row
            for row in self.body["operation_delta_contracts"]
        }

        def term_map(operation):
            return {
                (row["metric_id"], row["projection"]): (
                    row["direction"],
                    row["coefficient"],
                    row["symbol"],
                )
                for row in operation["delta_terms"]
            }

        rename = term_map(operations["same-scope-rename-contributor"])
        same = term_map(operations["same-scope-exact-duplicate-diagnostic"])
        cross = term_map(operations["cross-scope-exact-duplicate-contributor"])
        self.assertTrue(
            {
                "source-path-is-a-live-contract-contributor-materialization",
                "destination-scope-path-has-no-live-materialization-before-rename",
                "destination-scope-chunk-path-bindings-are-not-reachable-before-rename",
            }.issubset(
                operations["same-scope-rename-contributor"]["preconditions"]
            )
        )
        duplicate_live_path_preconditions = {
            "source-contract-endpoints-are-current-with-a-live-source-path-binding",
            "destination-scope-chunk-path-bindings-are-not-reachable-before-duplicate",
        }
        self.assertTrue(
            duplicate_live_path_preconditions.issubset(
                operations["same-scope-exact-duplicate-diagnostic"]["preconditions"]
            )
        )
        self.assertTrue(
            duplicate_live_path_preconditions.issubset(
                operations["cross-scope-exact-duplicate-contributor"]["preconditions"]
            )
        )
        expected_physical = {
            "managed-source-regular-files",
            "raw-cas-regular-objects",
            "chunk-cas-regular-objects",
            "managed-source-inodes",
            "raw-cas-inodes",
            "chunk-cas-inodes",
        }
        for operation in operations.values():
            self.assertEqual(
                {
                    row["projection"]
                    for row in operation["delta_terms"]
                    if row["metric_id"] == "physical-storage-v1"
                },
                expected_physical,
            )
        self.assertEqual(
            rename[("search-semantic-endpoint-v1", "contract-current")],
            ("preserve", 0, "zero"),
        )
        self.assertEqual(
            rename[("history-path-binding-v1", "reachable-path-bindings")],
            ("increase", 1, "qR"),
        )
        self.assertEqual(
            same[("search-semantic-endpoint-v1", "contract-current")],
            ("preserve", 0, "zero"),
        )
        self.assertEqual(
            cross[("search-semantic-endpoint-v1", "contract-current")],
            ("increase", 1, "qD"),
        )
        self.assertEqual(
            cross[("persona-global-chunk-hash-v1", "distinct-chunk-hashes")],
            ("preserve", 0, "zero"),
        )

    def test_performance_and_recall_denominators_are_intentionally_different(self):
        evaluation = self.body["evaluation_denominator_contract"]
        self.assertEqual(
            evaluation["mvp_performance_denominator"],
            ["scope_id", "chunk_hash"],
        )
        self.assertEqual(
            evaluation["formal_recall_denominator"],
            ["raw_hash", "section"],
        )
        self.assertEqual(
            evaluation["mvp_performance_minimum_current_endpoints"], 100_000
        )
        self.assertEqual(
            evaluation["persona_contract_current_endpoint_target"], 120_000
        )

    def test_all_authority_is_false_and_no_concrete_instance_fields_exist(self):
        self.assertFalse(self.body["g0_contract_frozen"])
        self.assertEqual(set(self.body["authority"]), validator.AUTHORITY_FIELDS)
        self.assertTrue(all(flag is False for flag in self.body["authority"].values()))
        self.assertFalse(self.body["completion_claims"]["actual_accounting_attested"])
        self.assertFalse(
            self.body["completion_claims"]["source_instance_assignment_present"]
        )
        self.assertTrue(
            validator.PROHIBITED_INSTANCE_KEYS.isdisjoint(
                set(validator._walk_keys(self.body))
            )
        )

    def test_builds_are_deeply_detached_and_validator_import_is_independent(self):
        first = accounting.build_chunk_accounting_contract()
        second = accounting.build_chunk_accounting_contract()
        self.assertIsNot(first, second)
        self.assertIsNot(first["metric_contracts"], second["metric_contracts"])
        self.assertIsNot(first["input_bindings"], second["input_bindings"])
        first["metric_contracts"][0]["identity_fields_observed"][0] = "collapsed"
        first["checkpoint_contract"]["profiles"]["full"][0][
            "current_contract_semantic_endpoints"
        ] = 1
        first["input_bindings"][0]["sha256"] = "0" * 64
        self.assertEqual(second, accounting.build_chunk_accounting_contract())

        tree = ast.parse(inspect.getsource(validator))
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertNotIn("persona_v2_chunk_accounting", imported)

    def test_rehashed_bool_float_extra_key_and_authority_tampering_is_rejected(self):
        self._assert_rehashed_semantic_rejection(
            lambda value: value["move_anchor_contract"].__setitem__(
                "qIM_inclusive_maximum", True
            )
        )
        floated = copy.deepcopy(self.body)
        floated["move_anchor_contract"]["qIM_inclusive_maximum"] = 350.0
        with self.assertRaises(validator.PersonaV2ChunkAccountingValidationError):
            self._independent_validate(floated)
        self._assert_rehashed_semantic_rejection(
            lambda value: value["move_anchor_contract"].__setitem__(
                "later_layer_source_ids", []
            )
        )
        self._assert_rehashed_semantic_rejection(
            lambda value: value["authority"].__setitem__(
                "authorizes_kio_execution", True
            )
        )

    def test_rehashed_cross_metric_and_move_delta_tampering_is_rejected(self):
        self._assert_rehashed_semantic_rejection(
            lambda value: value["metric_contracts"][0].__setitem__(
                "chunk_id_is_chunk_hash", False
            )
        )
        self._assert_rehashed_semantic_rejection(
            lambda value: value["metric_contracts"][1].__setitem__(
                "identity_fields", ["scope_id", "chunk_id"]
            )
        )
        self._assert_rehashed_semantic_rejection(
            lambda value: value["operation_delta_contracts"][0][
                "preconditions"
            ].remove(
                "destination-scope-chunk-path-bindings-are-not-reachable-before-rename"
            )
        )

        def collapse_move_history(value):
            operation = value["operation_delta_contracts"][1]
            term = next(
                row
                for row in operation["delta_terms"]
                if row["metric_id"] == "search-semantic-endpoint-v1"
                and row["projection"] == "incidental-history-only"
            )
            term.update({"direction": "preserve", "coefficient": 0, "symbol": "zero"})

        self._assert_rehashed_semantic_rejection(collapse_move_history)
        self._assert_rehashed_semantic_rejection(
            lambda value: value["evaluation_denominator_contract"].__setitem__(
                "formal_recall_denominator", ["scope_id", "chunk_hash"]
            )
        )

    def test_dependency_tamper_and_split_brain_are_rejected(self):
        bad_envelope = copy.deepcopy(self.envelope)
        bad_envelope["history_checkpoints"]["full"]["W0"][
            "current_contract_chunks"
        ] = 120_001
        with self.assertRaises(validator.PersonaV2ChunkAccountingValidationError):
            self._independent_validate(envelope_value=bad_envelope)

        bad_overlay = copy.deepcopy(self.overlay)
        envelope_binding = next(
            row
            for row in bad_overlay["input_bindings"]
            if row["name"] == "envelope"
        )
        envelope_binding["sha256"] = "0" * 64
        with self.assertRaises(validator.PersonaV2ChunkAccountingValidationError):
            self._independent_validate(overlay_value=bad_overlay)

    def test_caller_owned_objects_are_reauthenticated_on_all_exits(self):
        body = copy.deepcopy(self.body)
        envelope_value = copy.deepcopy(self.envelope)
        overlay_value = copy.deepcopy(self.overlay)

        def mutate_caller_and_return(*_args):
            body["metric_order"][0] = "changed-during-validation"
            return True

        with mock.patch.object(
            validator,
            "_validate_snapshot",
            side_effect=mutate_caller_and_return,
        ):
            with self.assertRaisesRegex(
                validator.PersonaV2ChunkAccountingValidationError,
                "caller-owned chunk accounting changed",
            ):
                validator.validate_chunk_accounting_contract(
                    body,
                    envelope_value=envelope_value,
                    overlay_contract_value=overlay_value,
                )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
