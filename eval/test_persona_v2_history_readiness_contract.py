"""Focused and opt-in tests for the static history-readiness contract."""

from __future__ import annotations

import ast
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
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_history_readiness_contract as package
    from . import persona_v2_history_readiness_contract_validator as independent
except ImportError:  # pragma: no cover - direct discovery compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_history_readiness_contract as package
    import persona_v2_history_readiness_contract_validator as independent


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


class PersonaV2HistoryReadinessContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = package.build_history_readiness_contract()
        cls.raw = package.canonical_json_bytes(cls.value)
        cls.digest = hashlib.sha256(cls.raw).hexdigest()

    def _validate(self, value):
        return independent.validate_history_readiness_contract(value)

    def test_candidate_identity_pin_and_optional_golden_parity(self):
        self.assertEqual(
            self.value["artifact_schema"],
            "kio.persona.pc-history-readiness-contract/v1",
        )
        self.assertEqual(self.value["artifact_schema_version"], 1)
        self.assertEqual(
            self.value["candidate_status"],
            "proposal-local-golden-frozen-not-issued",
        )
        self.assertTrue(self.value["proposal_only"])
        self.assertLess(len(self.raw), package.TARGET_CONTRACT_BYTES)
        self.assertLessEqual(len(self.raw), package.MAX_CONTRACT_BYTES)
        self.assertEqual(package._expected_golden(), independent._expected_golden())
        self.assertIsNone(package._expected_golden())
        pin = self.value["dependency_pin"]
        self.assertEqual(pin["canonical_bytes"], 8_455)
        self.assertEqual(
            pin["sha256"],
            "64131249be0313bfbccdbc673fa56bd2f54e1a534ac5c52323d6e64741c55f2d",
        )
        self.assertEqual(
            pin["pin_status"], "accepted-frozen-history-slice-body-pin-not-issued"
        )
        self.assertEqual(
            pin["dependency_role"],
            "query-independent-structural-history-demand-accepted-frozen-pin",
        )
        self.assertTrue(pin["dependency_accepted"])
        self.assertTrue(pin["dependency_frozen"])
        self.assertFalse(pin["dependency_issued"])
        self.assertFalse(pin["body_opened_in_fast_candidate_build"])
        self.assertTrue(pin["body_required_for_full_acceptance"])
        replay_pin = self.value["replay_id_dependency_pin"]
        self.assertEqual(
            package.REPLAY_IDS,
            (
                "formal-replay-01",
                "formal-replay-02",
                "formal-replay-03",
            ),
        )
        self.assertEqual(replay_pin["expected_replay_ids"], list(package.REPLAY_IDS))
        self.assertEqual(replay_pin["canonical_bytes"], 41_099)
        self.assertEqual(
            replay_pin["sha256"],
            "8c9071d0549c7d876068aa145de369f21f787ca2f23dfeb61254efa4e83b808f",
        )
        self.assertFalse(replay_pin["body_opened_in_fast_candidate_build"])
        self.assertFalse(replay_pin["body_required_for_full_acceptance"])
        self.assertEqual(
            replay_pin["binding_scope"],
            "replay-id-order-only-no-runtime-or-path-authority",
        )
        self.assertEqual(
            replay_pin["dependency_role"],
            "exact-formal-replay-id-order-and-namespace-binding",
        )
        self.assertEqual(
            replay_pin["pin_status"],
            "accepted-frozen-compositor-replay-id-binding-not-issued",
        )
        self.assertTrue(replay_pin["dependency_accepted"])
        self.assertTrue(replay_pin["dependency_frozen"])
        self.assertFalse(replay_pin["dependency_issued"])

    def test_exact_checkpoint_literals_and_totals(self):
        expected = [
            ("W0", 120_000, 0),
            ("W1", 120_000, 24_000),
            ("W2", 120_000, 24_000),
            ("W3", 120_000, 48_000),
            ("W4", 120_000, 60_000),
            ("W5-pre-purge", 124_800, 64_800),
            ("W5-final", 120_000, 60_000),
        ]
        rows = self.value["checkpoint_contract"]
        self.assertEqual(len(rows), 7)
        self.assertEqual(
            [
                (
                    row["checkpoint"],
                    row["current_contract_semantic_endpoints_per_persona"],
                    row["history_only_contract_semantic_endpoints_per_persona"],
                )
                for row in rows
            ],
            expected,
        )
        for ordinal, row in enumerate(rows):
            self.assertEqual(row["checkpoint_ordinal"], ordinal)
            self.assertEqual(row["persona_count"], 20)
            self.assertEqual(row["receipt_count_per_replay"], 20)
            self.assertEqual(
                row["total_current_contract_semantic_endpoints_per_replay"],
                expected[ordinal][1] * 20,
            )
            self.assertEqual(
                row["total_history_only_contract_semantic_endpoints_per_replay"],
                expected[ordinal][2] * 20,
            )
        semantics = self.value["endpoint_counting_contract"]
        self.assertEqual(
            semantics["metric_id"],
            "search-semantic-endpoint-v1/contract-contributor",
        )
        self.assertEqual(semantics["identity_fields"], ["scope_key", "chunk_id"])
        self.assertTrue(semantics["chunk_id_is_chunk_hash"])
        self.assertTrue(semantics["current_and_history_only_sets_are_disjoint"])
        self.assertFalse(semantics["persona_replay_or_checkpoint_pooling_allowed"])

    def test_exact_3_container_60_root_420_checkpoint_21_seal_and_3_terminal_receipts(self):
        summary = self.value["summary"]
        self.assertEqual(summary["persona_count"], 20)
        self.assertEqual(summary["replay_count"], 3)
        self.assertEqual(summary["checkpoint_count_per_replay"], 7)
        self.assertEqual(summary["persona_checkpoint_receipt_count"], 420)
        self.assertEqual(summary["checkpoint_seal_count"], 21)
        self.assertEqual(summary["persona_device_root_count"], 60)
        self.assertEqual(summary["persona_registry_root_count"], 60)
        self.assertEqual(summary["persona_root_receipt_count"], 60)
        self.assertEqual(summary["replay_container_count"], 3)
        self.assertEqual(summary["replay_container_receipt_count"], 3)
        self.assertEqual(summary["replay_terminal_count"], 3)
        self.assertEqual(summary["runtime_external_artifact_count"], 507)

        container_receipts = self.value["replay_container_receipt_coordinates"]
        receipts = self.value["persona_checkpoint_receipt_coordinates"]
        seals = self.value["checkpoint_seal_coordinates"]
        roots = self.value["persona_root_receipt_coordinates"]
        terminals = self.value["replay_terminal_coordinates"]
        self.assertEqual(len(container_receipts), 3)
        self.assertEqual(len(receipts), 20 * 3 * 7)
        self.assertEqual(len(seals), 3 * 7)
        self.assertEqual(len(roots), 20 * 3)
        self.assertEqual(len(terminals), 3)
        self.assertEqual(
            len({row["receipt_id"] for row in container_receipts}), 3
        )
        self.assertEqual(len({row["receipt_id"] for row in receipts}), 420)
        self.assertEqual(len({row["seal_id"] for row in seals}), 21)
        self.assertEqual(len({row["receipt_id"] for row in roots}), 60)
        self.assertEqual(len({row["terminal_id"] for row in terminals}), 3)

        expected_coordinates = {
            (replay_id, checkpoint, persona_id)
            for replay_id in package.REPLAY_IDS
            for checkpoint, _current, _history in package.CHECKPOINT_ROWS
            for persona_id in package.PERSONA_IDS
        }
        actual_coordinates = {
            (row["replay_id"], row["checkpoint"], row["persona_id"])
            for row in receipts
        }
        self.assertEqual(actual_coordinates, expected_coordinates)
        for terminal in terminals:
            self.assertEqual(terminal["expected_checkpoint_seal_count"], 7)
            self.assertEqual(
                terminal["expected_persona_checkpoint_receipt_count"], 140
            )

    def test_receipt_coordinates_repeat_exact_checkpoint_counts(self):
        expected = {
            checkpoint: (current_count, history_count)
            for checkpoint, current_count, history_count in package.CHECKPOINT_ROWS
        }
        per_coordinate = {}
        for row in self.value["persona_checkpoint_receipt_coordinates"]:
            self.assertEqual(
                (
                    row["expected_contract_current_endpoint_count"],
                    row["expected_contract_history_only_endpoint_count"],
                ),
                expected[row["checkpoint"]],
            )
            key = (row["replay_id"], row["checkpoint"])
            per_coordinate[key] = per_coordinate.get(key, 0) + 1
        self.assertEqual(set(per_coordinate.values()), {20})

    def test_60_device_and_registry_roots_are_separate_from_3_containers(self):
        containers = self.value["replay_container_coordinates"]
        container_receipts = self.value["replay_container_receipt_coordinates"]
        devices = self.value["persona_device_root_coordinates"]
        registries = self.value["persona_registry_root_coordinates"]
        root_receipts = self.value["persona_root_receipt_coordinates"]
        self.assertEqual(len(containers), 3)
        self.assertEqual(len(container_receipts), 3)
        self.assertEqual(len(devices), 60)
        self.assertEqual(len(registries), 60)
        self.assertEqual(len(root_receipts), 60)

        container_ids = {row["replay_container_id"] for row in containers}
        device_ids = {row["persona_device_root_id"] for row in devices}
        registry_ids = {row["persona_registry_root_id"] for row in registries}
        self.assertEqual(len(container_ids), 3)
        self.assertEqual(len(device_ids), 60)
        self.assertEqual(len(registry_ids), 60)
        self.assertTrue(container_ids.isdisjoint(device_ids))
        self.assertTrue(container_ids.isdisjoint(registry_ids))
        self.assertTrue(device_ids.isdisjoint(registry_ids))
        container_receipt_by_replay = {
            row["replay_id"]: row for row in container_receipts
        }
        self.assertEqual(set(container_receipt_by_replay), set(package.REPLAY_IDS))
        for container in containers:
            receipt = container_receipt_by_replay[container["replay_id"]]
            self.assertEqual(container["required_receipt_id"], receipt["receipt_id"])
            self.assertEqual(
                container["replay_container_id"], receipt["replay_container_id"]
            )

        expected_persona_coordinates = {
            (replay_id, persona_id)
            for replay_id in package.REPLAY_IDS
            for persona_id in package.PERSONA_IDS
        }
        for rows, identity_field in (
            (devices, "persona_device_root_id"),
            (registries, "persona_registry_root_id"),
            (root_receipts, "receipt_id"),
        ):
            self.assertEqual(
                {(row["replay_id"], row["persona_id"]) for row in rows},
                expected_persona_coordinates,
            )
            self.assertEqual(len({row[identity_field] for row in rows}), 60)
            self.assertEqual(
                {
                    row["persona_id"]: row["persona_ordinal"]
                    for row in rows
                    if row["replay_id"] == package.REPLAY_IDS[0]
                },
                {
                    persona_id: ordinal
                    for ordinal, persona_id in enumerate(package.PERSONA_IDS, start=1)
                },
            )

        device_by_coordinate = {
            (row["replay_id"], row["persona_id"]): row for row in devices
        }
        registry_by_coordinate = {
            (row["replay_id"], row["persona_id"]): row for row in registries
        }
        for row in root_receipts:
            coordinate = (row["replay_id"], row["persona_id"])
            self.assertEqual(
                row["persona_device_root_id"],
                device_by_coordinate[coordinate]["persona_device_root_id"],
            )
            self.assertEqual(
                row["persona_registry_root_id"],
                registry_by_coordinate[coordinate]["persona_registry_root_id"],
            )
            self.assertEqual(
                row["replay_container_id"],
                f"formal-replay-container/{row['replay_id']}",
            )
            self.assertEqual(
                row["replay_container_receipt_id"],
                container_receipt_by_replay[row["replay_id"]]["receipt_id"],
            )

        for row in self.value["persona_checkpoint_receipt_coordinates"]:
            self.assertEqual(
                row["persona_ordinal"], int(row["persona_id"].removeprefix("p"))
            )

    def test_each_seal_requires_one_ordered_20_persona_digest_bundle(self):
        seal_contract = self.value["field_contracts"]["checkpoint_seal"]
        required = set(seal_contract["required_fields"])
        digest_fields = set(seal_contract["digest_fields"])
        expected_bundle_fields = {
            "ordered_persona_checkpoint_receipt_bodies_sha256",
            "ordered_persona_checkpoint_receipt_ids_sha256",
            "ordered_persona_root_receipt_bodies_sha256",
            "ordered_persona_root_receipt_ids_sha256",
        }
        self.assertTrue(expected_bundle_fields.issubset(required))
        self.assertTrue(expected_bundle_fields.issubset(digest_fields))
        binding = seal_contract["coordinate_binding"]
        self.assertTrue(
            binding[
                "persona_checkpoint_receipt_ids_and_bodies_are_ordered_by_persona_id_ascii"
            ]
        )
        self.assertTrue(
            binding[
                "ordered_persona_root_receipt_bodies_bind_exact_replay_root_set"
            ]
        )
        seals = self.value["checkpoint_seal_coordinates"]
        self.assertEqual(len(seals), 21)
        self.assertTrue(
            all(row["expected_persona_receipt_count"] == 20 for row in seals)
        )

    def test_root_partition_and_seal_bundle_tampering_fail_before_provider(self):
        device_as_container = copy.deepcopy(self.value)
        device_as_container["persona_device_root_coordinates"][0][
            "persona_device_root_id"
        ] = device_as_container["replay_container_coordinates"][0][
            "replay_container_id"
        ]
        registry_as_device = copy.deepcopy(self.value)
        registry_as_device["persona_registry_root_coordinates"][0][
            "persona_registry_root_id"
        ] = registry_as_device["persona_device_root_coordinates"][0][
            "persona_device_root_id"
        ]
        weakened_seal = copy.deepcopy(self.value)
        weakened_seal["field_contracts"]["checkpoint_seal"][
            "coordinate_binding"
        ]["ordered_persona_root_receipt_bodies_bind_exact_replay_root_set"] = False
        pooled_seal = copy.deepcopy(self.value)
        pooled_seal["checkpoint_seal_coordinates"][0][
            "expected_persona_receipt_count"
        ] = 19
        weakened_container = copy.deepcopy(self.value)
        weakened_container["field_contracts"]["replay_container_receipt"][
            "coordinate_binding"
        ]["receipt_is_first_runtime_artifact_for_replay"] = False
        overlapping_container_path = copy.deepcopy(self.value)
        overlapping_container_path["cross_runtime_evidence_contract"][
            "replay_container_path_digest_set_is_disjoint_from_persona_device_root_path_digest_set"
        ] = False
        missing_container_receipt = copy.deepcopy(self.value)
        missing_container_receipt["replay_container_receipt_coordinates"].pop()

        for value in (
            device_as_container,
            registry_as_device,
            weakened_seal,
            pooled_seal,
            weakened_container,
            overlapping_container_path,
            missing_container_receipt,
        ):
            provider = mock.Mock(side_effect=AssertionError("provider opened"))
            with self.assertRaises(
                independent.PersonaV2HistoryReadinessContractValidationError
            ):
                independent._validate(value, dependency_snapshot_provider=provider)
            provider.assert_not_called()

    def test_field_allowlists_are_exact_and_exclude_query_or_eval_payloads(self):
        contracts = self.value["field_contracts"]
        self.assertEqual(
            set(contracts),
            {
                "checkpoint_seal",
                "persona_checkpoint_receipt",
                "persona_root_receipt",
                "replay_container_receipt",
                "replay_terminal",
            },
        )
        for name, contract in contracts.items():
            with self.subTest(name=name):
                self.assertFalse(contract["additional_fields_allowed"])
                required = contract["required_fields"]
                self.assertEqual(len(required), len(set(required)))
                self.assertEqual(required, sorted(required))
                joined = " ".join(required).lower()
                self.assertNotIn("query", joined)
                self.assertNotIn("oracle", joined)
                self.assertNotIn("evaluation", joined)
                self.assertNotIn("recall", joined)
        self.assertEqual(
            set(contracts["replay_container_receipt"]["required_fields"]),
            set(package.REPLAY_CONTAINER_RECEIPT_FIELDS),
        )
        self.assertEqual(
            set(contracts["persona_root_receipt"]["required_fields"]),
            set(package.FRESH_ROOT_FIELDS),
        )
        self.assertEqual(
            set(contracts["persona_checkpoint_receipt"]["required_fields"]),
            set(package.PERSONA_CHECKPOINT_RECEIPT_FIELDS),
        )
        self.assertEqual(
            set(contracts["checkpoint_seal"]["required_fields"]),
            set(package.CHECKPOINT_SEAL_FIELDS),
        )
        self.assertEqual(
            set(contracts["replay_terminal"]["required_fields"]),
            set(package.REPLAY_TERMINAL_FIELDS),
        )
        container = contracts["replay_container_receipt"]
        self.assertEqual(
            set(container["exact_true_fields"]),
            {
                "container_created_empty_before_any_persona_root",
                "container_created_exclusively",
                "container_created_fresh",
                "container_created_without_copy_clone_reflink_or_hardlink",
                "container_did_not_replace_existing_path",
                "container_path_did_not_exist_before_creation",
                "receipt_emitted_before_any_persona_root_or_write",
            },
        )
        root = contracts["persona_root_receipt"]
        self.assertIn(
            "device_root_is_strict_descendant_of_replay_container",
            root["exact_true_fields"],
        )
        self.assertIn("replay_container_receipt_sha256", root["digest_fields"])

    def test_dynamic_runtime_bodies_and_hashes_are_outside_global_golden(self):
        scope = self.value["global_golden_scope"]
        self.assertTrue(scope["covers_static_contract_body_only"])
        self.assertTrue(scope["runtime_receipts_seals_and_terminals_are_external"])
        self.assertTrue(
            scope["runtime_evidence_is_validated_against_coordinate_and_field_contracts"]
        )
        self.assertFalse(scope["dynamic_receipt_bytes_are_global_golden_inputs"])
        self.assertFalse(scope["dynamic_receipt_hashes_are_global_golden_inputs"])
        exclusions = self.value["dependency_exclusion_contract"]
        self.assertTrue(all(count == 0 for count in exclusions.values()))
        self.assertFalse(
            self.value["canonical_limits"]["dynamic_runtime_bodies_embedded"]
        )
        cross = self.value["cross_runtime_evidence_contract"]
        self.assertTrue(all(flag is True for flag in cross.values()))
        for field in (
            "persona_device_root_path_sha256_pairwise_distinct_across_all_60_roots",
            "persona_registry_root_path_sha256_pairwise_distinct_across_all_60_roots",
            "persona_root_receipt_body_sha256_pairwise_distinct_across_all_60_coordinates",
            "replay_container_is_strict_ancestor_of_each_persona_device_root",
            "replay_container_creation_nonce_sha256_pairwise_distinct_across_three_replays",
            "replay_container_path_digest_set_is_disjoint_from_persona_device_root_path_digest_set",
            "replay_container_path_digest_set_is_disjoint_from_persona_registry_root_path_digest_set",
            "replay_container_path_sha256_in_root_receipts_equals_bound_container_receipt_path_sha256",
            "replay_container_path_sha256_pairwise_distinct_across_three_replays",
            "replay_container_receipt_body_sha256_pairwise_distinct_across_three_coordinates",
            "root_creation_nonce_sha256_pairwise_distinct_across_all_60_coordinates",
            "no_persona_replay_or_checkpoint_receipt_pooling",
            "source_plan_sha256_identical_across_all_replays",
            "writer_plan_sha256_identical_across_all_replays",
        ):
            self.assertTrue(cross[field], field)

    def test_ordered_fail_fast_state_machine_is_total_on_success_path(self):
        machine = self.value["state_machine"]
        states = machine["state_order_per_replay"]
        transitions = machine["success_transitions"]
        self.assertEqual(states[0], "replay-container-attested")
        self.assertEqual(states[1], "twenty-persona-root-pairs-attested")
        self.assertEqual(states[-1], "replay-terminal-sealed")
        self.assertEqual(len(states), 2 + 7 * 3 + 1)
        self.assertEqual(len(transitions), len(states) - 1)
        for ordinal, transition in enumerate(transitions):
            self.assertEqual(transition["transition_ordinal"], ordinal)
            self.assertEqual(transition["from_state"], states[ordinal])
            self.assertEqual(transition["to_state"], states[ordinal + 1])
            self.assertTrue(transition["guard_must_be_exact_true"])
            self.assertEqual(
                transition["guard_failure_target"], "failed-terminal-absorbing"
            )
        self.assertEqual(machine["failure_state"], "failed-terminal-absorbing")
        self.assertTrue(machine["failure_state_is_absorbing"])
        self.assertTrue(
            machine["failure_stops_all_later_replay_and_checkpoint_emission"]
        )
        self.assertFalse(
            machine["next_checkpoint_mutation_before_current_seal_allowed"]
        )
        self.assertFalse(
            machine["next_replay_container_before_current_replay_terminal_allowed"]
        )
        self.assertFalse(
            machine["persona_root_creation_before_replay_container_receipt_allowed"]
        )
        self.assertTrue(machine["replay_container_receipt_is_first_runtime_artifact"])
        self.assertFalse(machine["w5_purge_before_w5_pre_purge_seal_allowed"])
        self.assertTrue(
            machine["all_persona_w0_index_receipts_complete_before_w1_mutation"]
        )
        self.assertTrue(machine["w0_persona_roots_written_one_at_a_time"])
        self.assertEqual(machine["persona_w0_creation_order"], list(package.PERSONA_IDS))
        self.assertFalse(
            machine["final_evaluation_before_all_three_replay_terminals_allowed"]
        )
        self.assertEqual(machine["replay_execution_order"], list(package.REPLAY_IDS))

    def test_all_authority_and_runtime_observation_remain_false(self):
        self.assertEqual(set(self.value["authority"]), package.AUTHORITY_FIELDS)
        self.assertTrue(all(flag is False for flag in self.value["authority"].values()))
        claims = self.value["completion_claims"]
        for field in (
            "all_420_runtime_receipts_observed",
            "all_21_checkpoint_seals_observed",
            "all_3_replay_container_receipts_observed",
            "all_3_replay_containers_observed",
            "all_3_replay_terminals_observed",
            "all_60_persona_device_roots_observed",
            "all_60_persona_registry_roots_observed",
            "all_60_persona_root_receipts_observed",
            "dependency_issued",
            "history_runtime_ready_for_evaluation",
            "replay_id_binding_issued",
        ):
            self.assertFalse(claims[field], field)
        for field in (
            "dependency_accepted",
            "dependency_frozen",
            "exact_runtime_coordinate_contract_defined",
            "full_dependency_body_replay_passed",
            "global_contract_golden_frozen",
            "ordered_fail_fast_state_machine_defined",
            "replay_id_binding_accepted",
            "replay_id_binding_frozen",
            "runtime_field_allowlists_defined",
            "two_hash_seed_cold_replays_passed",
        ):
            self.assertTrue(claims[field], field)

    def test_query_oracle_and_evaluation_results_cannot_authorize(self):
        boundary = self.value["query_oracle_evaluation_independence"]
        self.assertTrue(all(flag is False for flag in boundary.values()))
        self.assertEqual(self.value["dependency_exclusion_contract"]["query_body_count"], 0)
        self.assertEqual(self.value["dependency_exclusion_contract"]["oracle_body_count"], 0)
        self.assertEqual(
            self.value["dependency_exclusion_contract"]["evaluation_result_body_count"],
            0,
        )

    def test_fast_public_paths_never_open_live_history_body(self):
        with mock.patch.object(
            independent.history_slice,
            "require_full_history_presolve_input_closure_slice",
            side_effect=AssertionError("live dependency opened"),
        ) as live:
            value = package.build_history_readiness_contract()
            self.assertTrue(package.validate_history_readiness_contract(value))
            raw = package.canonical_json_bytes(value)
            self.assertTrue(independent.validate_history_readiness_contract_bytes(raw))
            self.assertEqual(package.history_readiness_contract_sha256(value), self.digest)
        live.assert_not_called()

    def test_tampering_fails_before_dependency_provider(self):
        mutations = []
        authority = copy.deepcopy(self.value)
        authority["authority"]["authorizes_kio_execution"] = True
        mutations.append(authority)
        coordinate = copy.deepcopy(self.value)
        coordinate["persona_checkpoint_receipt_coordinates"][0][
            "expected_contract_current_endpoint_count"
        ] += 1
        mutations.append(coordinate)
        fields = copy.deepcopy(self.value)
        fields["field_contracts"]["persona_root_receipt"]["additional_fields_allowed"] = True
        mutations.append(fields)
        golden_scope = copy.deepcopy(self.value)
        golden_scope["global_golden_scope"][
            "dynamic_receipt_hashes_are_global_golden_inputs"
        ] = True
        mutations.append(golden_scope)
        dependency = copy.deepcopy(self.value)
        dependency["dependency_pin"]["dependency_frozen"] = False
        mutations.append(dependency)
        replay_dependency = copy.deepcopy(self.value)
        replay_dependency["replay_id_dependency_pin"]["dependency_frozen"] = False
        mutations.append(replay_dependency)
        local_freeze = copy.deepcopy(self.value)
        local_freeze["completion_claims"]["global_contract_golden_frozen"] = False
        mutations.append(local_freeze)
        runtime_ready = copy.deepcopy(self.value)
        runtime_ready["completion_claims"][
            "history_runtime_ready_for_evaluation"
        ] = True
        mutations.append(runtime_ready)

        for value in mutations:
            provider = mock.Mock(side_effect=AssertionError("provider opened"))
            with self.subTest(value=value):
                with self.assertRaises(
                    independent.PersonaV2HistoryReadinessContractValidationError
                ):
                    independent._validate(
                        value,
                        dependency_snapshot_provider=provider,
                    )
                provider.assert_not_called()

    def test_alias_cycle_and_long_string_fail_before_normalization_or_provider(self):
        alias = copy.deepcopy(self.value)
        shared = alias["orders"]["personas"]
        alias["orders"]["replays"] = shared
        cycle = copy.deepcopy(self.value)
        cycle["state_machine"]["cycle"] = cycle["state_machine"]
        for value in (alias, cycle):
            provider = mock.Mock(side_effect=AssertionError("provider opened"))
            with self.assertRaises(
                independent.PersonaV2HistoryReadinessContractValidationError
            ):
                independent._validate(value, dependency_snapshot_provider=provider)
            provider.assert_not_called()

        long_string = copy.deepcopy(self.value)
        long_string["artifact_kind"] = "x" * (
            artifact_common.MAX_CANONICAL_STRING_BYTES + 1
        )
        provider = mock.Mock(side_effect=AssertionError("provider opened"))
        with mock.patch.object(
            artifact_common.unicodedata,
            "normalize",
            side_effect=AssertionError("normalization reached"),
        ) as normalize:
            with self.assertRaises(
                independent.PersonaV2HistoryReadinessContractValidationError
            ):
                independent._validate(
                    long_string,
                    dependency_snapshot_provider=provider,
                )
        normalize.assert_not_called()
        provider.assert_not_called()

    def test_multibyte_utf8_oversize_fails_before_canonical_encoder_or_provider(self):
        value = copy.deepcopy(self.value)
        value["artifact_kind"] = "\U0001f600" * 1_025
        self.assertLessEqual(
            len(value["artifact_kind"]),
            artifact_common.MAX_CANONICAL_STRING_BYTES,
        )
        with mock.patch.object(
            artifact_common,
            "canonical_json_bytes",
            side_effect=AssertionError("canonical encoder reached"),
        ) as encoder, mock.patch.object(
            artifact_common.unicodedata,
            "normalize",
            side_effect=AssertionError("normalization reached"),
        ) as normalize:
            with self.assertRaises(
                package.PersonaV2HistoryReadinessContractError
            ):
                package.canonical_json_bytes(value)
        encoder.assert_not_called()
        normalize.assert_not_called()

        provider = mock.Mock(side_effect=AssertionError("provider opened"))
        with mock.patch.object(
            artifact_common,
            "canonical_json_bytes",
            side_effect=AssertionError("canonical encoder reached"),
        ) as encoder, mock.patch.object(
            artifact_common.unicodedata,
            "normalize",
            side_effect=AssertionError("normalization reached"),
        ) as normalize:
            with self.assertRaises(
                independent.PersonaV2HistoryReadinessContractValidationError
            ):
                independent._validate(
                    value,
                    dependency_snapshot_provider=provider,
                )
        encoder.assert_not_called()
        normalize.assert_not_called()
        provider.assert_not_called()

    def test_noncanonical_types_and_values_fail_closed(self):
        cases = []
        null_value = copy.deepcopy(self.value)
        null_value["proposal_only"] = None
        cases.append(null_value)
        float_value = copy.deepcopy(self.value)
        float_value["artifact_schema_version"] = 1.0
        cases.append(float_value)
        negative = copy.deepcopy(self.value)
        negative["summary"]["persona_count"] = -1
        cases.append(negative)
        tuple_value = copy.deepcopy(self.value)
        tuple_value["orders"]["replays"] = tuple(package.REPLAY_IDS)
        cases.append(tuple_value)
        for value in cases:
            provider = mock.Mock(side_effect=AssertionError("provider opened"))
            with self.assertRaises(
                independent.PersonaV2HistoryReadinessContractValidationError
            ):
                independent._validate(value, dependency_snapshot_provider=provider)
            provider.assert_not_called()

    def test_nonexact_top_level_key_fails_before_key_equality_or_provider(self):
        class HostileString(str):
            __hash__ = str.__hash__

            def __eq__(self, _other):
                raise AssertionError("top-level key equality reached")

        value = dict(self.value)
        artifact_kind = value.pop("artifact_kind")
        value[HostileString("artifact_kind")] = artifact_kind
        provider = mock.Mock(side_effect=AssertionError("provider opened"))
        with self.assertRaises(
            independent.PersonaV2HistoryReadinessContractValidationError
        ):
            independent._validate(value, dependency_snapshot_provider=provider)
        provider.assert_not_called()

    def test_strict_raw_loader_rejects_noncanonical_duplicate_and_oversize(self):
        invalid = (
            b" " + self.raw,
            self.raw + b"\n",
            b'{"a":1,"a":1}',
            b'{"artifact_schema_version":01}',
            b'{"artifact_schema_version":1.0}',
            b'{"proposal_only":null}',
            b"x" * (independent.MAX_CONTRACT_BYTES + 1),
        )
        with mock.patch.object(
            independent,
            "_live_dependency_snapshot",
            side_effect=AssertionError("provider opened"),
        ) as live:
            for raw in invalid:
                with self.subTest(raw=raw[:40]):
                    with self.assertRaises(
                        independent.PersonaV2HistoryReadinessContractValidationError
                    ):
                        independent.validate_history_readiness_contract_bytes(raw)
        live.assert_not_called()

    def test_atomic_goldens_and_full_parity_fail_before_live_dependency(self):
        valid_pair = (len(self.raw), self.digest)
        invalid_pairs = (
            (valid_pair[0], None),
            (None, valid_pair[1]),
            (True, valid_pair[1]),
            (0, valid_pair[1]),
            (package.TARGET_CONTRACT_BYTES + 1, valid_pair[1]),
            (valid_pair[0], "A" * 64),
            (valid_pair[0], "0" * 63),
        )
        for module, error_type in (
            (package, package.PersonaV2HistoryReadinessContractError),
            (
                independent,
                independent.PersonaV2HistoryReadinessContractValidationError,
            ),
        ):
            for byte_count, digest in invalid_pairs:
                with self.subTest(module=module.__name__, pair=(byte_count, digest)), mock.patch.object(
                    module, "EXPECTED_CANONICAL_BYTES", byte_count
                ), mock.patch.object(module, "EXPECTED_SHA256", digest):
                    with self.assertRaises(error_type):
                        module._expected_golden()

        with mock.patch.object(
            independent,
            "_live_dependency_snapshot",
            side_effect=AssertionError("live dependency opened"),
        ) as live:
            with self.assertRaises(
                independent.PersonaV2HistoryReadinessContractValidationError
            ):
                independent.validate_history_readiness_contract_full(self.value)
        live.assert_not_called()

    def test_mismatched_goldens_fail_before_build_or_live_dependency(self):
        with mock.patch.object(
            package, "EXPECTED_CANONICAL_BYTES", len(self.raw)
        ), mock.patch.object(
            package, "EXPECTED_SHA256", self.digest
        ), mock.patch.object(
            independent, "EXPECTED_CANONICAL_BYTES", len(self.raw)
        ), mock.patch.object(
            independent, "EXPECTED_SHA256", "0" * 64
        ), mock.patch.object(
            independent.history_slice,
            "require_full_history_presolve_input_closure_slice",
            side_effect=AssertionError("live dependency opened"),
        ) as live:
            with self.assertRaises(package.PersonaV2HistoryReadinessContractError):
                package.build_history_readiness_contract()
            with self.assertRaises(
                independent.PersonaV2HistoryReadinessContractValidationError
            ):
                independent.validate_history_readiness_contract_full(
                    self.value,
                    producer_expected_golden=(len(self.raw), self.digest),
                )
        live.assert_not_called()

    def test_upstream_goldens_are_exactly_aligned_before_dependency_provider(self):
        unset_modules = (
            independent.history_slice,
            independent.history_validator,
        )
        for module in unset_modules:
            provider = mock.Mock(side_effect=AssertionError("provider opened"))
            with self.subTest(module=module.__name__, mode="unset"), mock.patch.object(
                module, "EXPECTED_CANONICAL_BYTES", None
            ), mock.patch.object(module, "EXPECTED_SHA256", None):
                with self.assertRaises(
                    independent.PersonaV2HistoryReadinessContractValidationError
                ):
                    independent._validate(
                        self.value,
                        dependency_snapshot_provider=provider,
                    )
            provider.assert_not_called()

        drift_modules = (
            independent.history_slice,
            independent.history_validator,
            independent.device_compositor,
            independent.compositor_validator,
        )
        for module in drift_modules:
            provider = mock.Mock(side_effect=AssertionError("provider opened"))
            with self.subTest(module=module.__name__, mode="drift"), mock.patch.object(
                module, "EXPECTED_SHA256", "0" * 64
            ):
                with self.assertRaises(
                    independent.PersonaV2HistoryReadinessContractValidationError
                ):
                    independent._validate(
                        self.value,
                        dependency_snapshot_provider=provider,
                    )
            provider.assert_not_called()

        with mock.patch.object(
            package.history_slice, "EXPECTED_CANONICAL_BYTES", None
        ), mock.patch.object(
            package.history_slice, "EXPECTED_SHA256", None
        ), mock.patch.object(
            independent.history_slice,
            "require_full_history_presolve_input_closure_slice",
            side_effect=AssertionError("provider opened"),
        ) as live:
            with self.assertRaises(package.PersonaV2HistoryReadinessContractError):
                package.build_history_readiness_contract()
        live.assert_not_called()

    def test_dependency_provider_is_two_read_and_detects_toctou(self):
        calls = []

        def provider():
            calls.append(1)
            return independent._candidate_dependency_snapshot()

        self.assertTrue(
            independent._validate(
                self.value,
                dependency_snapshot_provider=provider,
            )
        )
        self.assertEqual(len(calls), 2)

        snapshots = [
            independent._candidate_dependency_snapshot(),
            independent._candidate_dependency_snapshot(),
        ]
        snapshots[1]["dependency_pin"]["canonical_bytes"] += 1
        with self.assertRaises(
            independent.PersonaV2HistoryReadinessContractValidationError
        ):
            independent._validate(
                self.value,
                dependency_snapshot_provider=lambda: snapshots.pop(0),
            )

        mutable = independent._candidate_dependency_snapshot()

        def mutate_dependency(opening):
            opening["dependency_pin"]["sha256"] = "0" * 64

        with self.assertRaises(
            independent.PersonaV2HistoryReadinessContractValidationError
        ):
            independent._validate(
                self.value,
                dependency_snapshot_provider=lambda: mutable,
                dependency_observer=mutate_dependency,
            )

    def test_caller_mutation_during_dependency_validation_is_detected(self):
        value = copy.deepcopy(self.value)

        def mutate_caller(_opening_dependency):
            value["summary"]["persona_count"] = 0

        with self.assertRaises(
            independent.PersonaV2HistoryReadinessContractValidationError
        ):
            independent._validate(
                value,
                dependency_snapshot_provider=independent._candidate_dependency_snapshot,
                dependency_observer=mutate_caller,
            )

    def test_builds_and_snapshots_are_detached(self):
        first = package._candidate_dependency_snapshot()
        first["dependency_pin"]["canonical_bytes"] = 0
        second = package._candidate_dependency_snapshot()
        self.assertEqual(second["dependency_pin"]["canonical_bytes"], 8_455)
        built = package.build_history_readiness_contract()
        built["summary"]["persona_count"] = 0
        rebuilt = package.build_history_readiness_contract()
        self.assertEqual(rebuilt["summary"]["persona_count"], 20)

    def test_authoritative_require_always_fails_without_live_dependency(self):
        with mock.patch.object(
            independent.history_slice,
            "require_full_history_presolve_input_closure_slice",
            side_effect=AssertionError("live dependency opened"),
        ) as live:
            with self.assertRaises(package.PersonaV2HistoryReadinessContractError):
                package.require_authoritative_history_readiness_contract()
        live.assert_not_called()

    def test_independent_validator_does_not_import_target_producer(self):
        path = Path(independent.__file__).resolve()
        imported = _ast_imported_modules(path)
        forbidden = "persona_v2_history_readiness_contract"
        self.assertFalse(
            any(
                module == forbidden
                or module.endswith("." + forbidden)
                or module.startswith(forbidden + ".")
                for module in imported
            ),
            imported,
        )

    def test_validation_and_hash_are_exact(self):
        self.assertTrue(self._validate(self.value))
        self.assertTrue(independent.validate_history_readiness_contract_bytes(self.raw))
        self.assertEqual(package.history_readiness_contract_sha256(), self.digest)


@unittest.skipUnless(
    os.environ.get("KIO_RUN_HISTORY_READINESS_CONTRACT_FULL") == "1",
    "set KIO_RUN_HISTORY_READINESS_CONTRACT_FULL=1 for live dependency replay",
)
class PersonaV2HistoryReadinessContractFullTest(unittest.TestCase):
    def test_full_dependency_acceptance(self):
        import resource

        calls = []
        original = independent.history_slice.require_full_history_presolve_input_closure_slice

        def counted_dependency_replay():
            calls.append(1)
            return original()

        started = time.monotonic()
        with mock.patch.object(
            independent.history_slice,
            "require_full_history_presolve_input_closure_slice",
            side_effect=counted_dependency_replay,
        ):
            value = package.require_full_history_readiness_contract()
        raw = package.canonical_json_bytes(value)
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform != "darwin":
            rss *= 1024
        measurement = {
            "canonical_bytes": len(raw),
            "dependency_full_replay_count": len(calls),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "maximum_rss_bytes": rss,
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        print(json.dumps(measurement, sort_keys=True))
        self.assertEqual(measurement["dependency_full_replay_count"], 1)
        self.assertLessEqual(measurement["elapsed_seconds"], 21_600)
        self.assertLessEqual(measurement["maximum_rss_bytes"], 1 * 2**30)
        self.assertLessEqual(len(raw), package.TARGET_CONTRACT_BYTES)
        if package.EXPECTED_CANONICAL_BYTES is not None:
            self.assertEqual(len(raw), package.EXPECTED_CANONICAL_BYTES)
        if package.EXPECTED_SHA256 is not None:
            self.assertEqual(
                hashlib.sha256(raw).hexdigest(), package.EXPECTED_SHA256
            )


@unittest.skipUnless(
    os.environ.get("KIO_RUN_HISTORY_READINESS_CONTRACT_COLD") == "1",
    "set KIO_RUN_HISTORY_READINESS_CONTRACT_COLD=1 for two isolated full replays",
)
class PersonaV2HistoryReadinessContractColdTest(unittest.TestCase):
    def test_two_hashseed_full_builds_are_byte_identical(self):
        script = r'''
import hashlib
import json
import resource
import sys
import time
from eval import persona_v2_history_readiness_contract as package

started = time.monotonic()
value = package.require_full_history_readiness_contract()
raw = package.canonical_json_bytes(value)
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
if sys.platform != "darwin":
    rss *= 1024
print(json.dumps({
    "canonical_bytes": len(raw),
    "completion_claims": value["completion_claims"],
    "dependency_pin": value["dependency_pin"],
    "elapsed_seconds": round(time.monotonic() - started, 3),
    "maximum_rss_bytes": rss,
    "replay_id_dependency_pin": value["replay_id_dependency_pin"],
    "sha256": hashlib.sha256(raw).hexdigest(),
}, sort_keys=True))
'''
        results = []
        project_root = str(Path(__file__).resolve().parents[1])
        for seed in ("0", "1"):
            environment = os.environ.copy()
            environment["PYTHONHASHSEED"] = seed
            environment.pop("KIO_RUN_HISTORY_READINESS_CONTRACT_FULL", None)
            environment.pop("KIO_RUN_HISTORY_READINESS_CONTRACT_COLD", None)
            completed = subprocess.run(
                [sys.executable, "-c", script],
                cwd=project_root,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
                timeout=21_600,
            )
            result = json.loads(completed.stdout.strip().splitlines()[-1])
            print(json.dumps({"hash_seed": seed, **result}, sort_keys=True))
            self.assertLessEqual(result["elapsed_seconds"], 21_600)
            self.assertLessEqual(result["maximum_rss_bytes"], 1 * 2**30)
            results.append(result)
        self.assertEqual(results[0]["canonical_bytes"], results[1]["canonical_bytes"])
        self.assertEqual(results[0]["sha256"], results[1]["sha256"])
        self.assertEqual(results[0]["dependency_pin"], results[1]["dependency_pin"])
        self.assertEqual(
            results[0]["replay_id_dependency_pin"],
            results[1]["replay_id_dependency_pin"],
        )
        self.assertEqual(
            results[0]["completion_claims"], results[1]["completion_claims"]
        )
        self.assertEqual(results[0]["dependency_pin"], package._history_slice_binding())
        self.assertEqual(
            results[0]["replay_id_dependency_pin"],
            package._device_compositor_replay_binding(),
        )
        claims = results[0]["completion_claims"]
        for field in (
            "dependency_accepted",
            "dependency_frozen",
            "full_dependency_body_replay_passed",
            "global_contract_golden_frozen",
            "replay_id_binding_accepted",
            "replay_id_binding_frozen",
            "two_hash_seed_cold_replays_passed",
        ):
            self.assertTrue(claims[field], field)
        for field in (
            "all_420_runtime_receipts_observed",
            "all_21_checkpoint_seals_observed",
            "all_3_replay_container_receipts_observed",
            "all_3_replay_containers_observed",
            "all_3_replay_terminals_observed",
            "all_60_persona_device_roots_observed",
            "all_60_persona_registry_roots_observed",
            "all_60_persona_root_receipts_observed",
            "dependency_issued",
            "history_runtime_ready_for_evaluation",
            "replay_id_binding_issued",
        ):
            self.assertFalse(claims[field], field)
        if package.EXPECTED_CANONICAL_BYTES is not None:
            self.assertEqual(results[0]["canonical_bytes"], package.EXPECTED_CANONICAL_BYTES)
        if package.EXPECTED_SHA256 is not None:
            self.assertEqual(results[0]["sha256"], package.EXPECTED_SHA256)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
