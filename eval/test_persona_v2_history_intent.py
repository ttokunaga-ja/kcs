import copy
import hashlib
import unittest

from eval import persona_v2_contract as envelope
from eval import persona_v2_fact_membership as fact_membership
from eval import persona_v2_history_intent as history


EXPECTED_CHECKPOINTS = {
    "pilot": [
        ("W0", 12_000, 0),
        ("W1", 12_000, 2_400),
        ("W2", 12_000, 2_400),
        ("W3", 12_000, 4_800),
        ("W4", 12_000, 6_000),
        ("W5-pre-purge", 12_480, 6_480),
        ("W5-final", 12_000, 6_000),
    ],
    "full": [
        ("W0", 120_000, 0),
        ("W1", 120_000, 24_000),
        ("W2", 120_000, 24_000),
        ("W3", 120_000, 48_000),
        ("W4", 120_000, 60_000),
        ("W5-pre-purge", 124_800, 64_800),
        ("W5-final", 120_000, 60_000),
    ],
}

EXPECTED_FULL_PER_REPLAY = [
    ("W0", 2_400_000, 0),
    ("W1", 2_400_000, 480_000),
    ("W2", 2_400_000, 480_000),
    ("W3", 2_400_000, 960_000),
    ("W4", 2_400_000, 1_200_000),
    ("W5-pre-purge", 2_496_000, 1_296_000),
    ("W5-final", 2_400_000, 1_200_000),
]

EXPECTED_FULL_THREE_REPLAYS = [
    ("W0", 7_200_000, 0),
    ("W1", 7_200_000, 1_440_000),
    ("W2", 7_200_000, 1_440_000),
    ("W3", 7_200_000, 2_880_000),
    ("W4", 7_200_000, 3_600_000),
    ("W5-pre-purge", 7_488_000, 3_888_000),
    ("W5-final", 7_200_000, 3_600_000),
]


class PersonaV2HistoryIntentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.values = history.build_history_intent_suite()
        cls.memberships = fact_membership.build_fact_membership_suite()

    def test_twenty_persona_candidates_are_bounded_and_noncompiled(self):
        self.assertEqual(
            [value["persona_id"] for value in self.values],
            list(envelope.PERSONA_IDS),
        )
        digests = []
        for persona_id, value in zip(envelope.PERSONA_IDS, self.values):
            self.assertEqual(value["artifact_schema"], history.ARTIFACT_SCHEMA)
            self.assertEqual(value["artifact_kind"], history.ARTIFACT_KIND)
            self.assertEqual(value["artifact_schema_version"], 2)
            self.assertIs(value["representative_vertical_slice_complete"], True)
            self.assertIs(value["conditional_template_catalog_complete"], False)
            self.assertIs(
                value[
                    "representative_transition_and_lifecycle_template_slice_complete"
                ],
                True,
            )
            self.assertIs(value["compiled_history_plan"], False)
            self.assertIs(value["compiled_event_inventory_complete"], False)
            self.assertIs(value["history_intent_inventory_complete"], False)
            self.assertIs(
                value["pilot_event_template_and_compiled_plan_byte_subset_proved"],
                False,
            )
            self.assertIs(value["g0_contract_frozen"], False)
            raw = history.canonical_json_bytes(value)
            self.assertLessEqual(len(raw), history.MAX_HISTORY_INTENT_BYTES)
            digest = history.history_intent_sha256(persona_id, value)
            self.assertEqual(digest, hashlib.sha256(raw).hexdigest())
            self.assertTrue(history.validate_history_intent(persona_id, value))
            digests.append(digest)
        self.assertEqual(len(digests), len(set(digests)))

    def test_w0_to_w1_is_the_only_bound_typed_revision(self):
        for value, membership in zip(self.values, self.memberships):
            constraint = value["representative_transition_constraint"]
            member = membership["memberships"][0]
            expected = history.apply_typed_revision(
                member["present_fact_ids"], member["revision_memberships"][0]
            )
            self.assertEqual(constraint["semantic_revision_boundary"], "W0-to-W1-only")
            self.assertEqual(constraint["allowed_history_cohort_ids"], ["P", "X", "Y"])
            self.assertIs(
                constraint["solver_assigned_history_cohort_id_present"], False
            )
            self.assertEqual(
                constraint["changed_fact_ids_at_w1"], expected["changed_fact_ids"]
            )
            self.assertEqual(
                constraint["present_fact_ids_at_w1"], expected["present_fact_ids"]
            )
            self.assertEqual(len(constraint["changed_fact_ids_at_w1"]), 2)
            self.assertTrue(
                set(member["present_fact_ids"])
                ^ set(constraint["present_fact_ids_at_w1"])
                == set(constraint["changed_fact_ids_at_w1"])
            )

    def test_w3_and_w5_surface_templates_carry_full_membership(self):
        for value in self.values:
            templates = {
                row["event_template_key"]: row for row in value["event_templates"]
            }
            for key in (
                "history-template-w1-typed-small-edit-v1",
                "history-template-w3-surface-major-edit-v1",
                "history-template-w5-surface-correction-v1",
            ):
                self.assertIs(templates[key]["creates_source"], False)
                self.assertIs(templates[key]["creates_source_version"], True)
                self.assertIs(templates[key]["creates_materialization"], False)
            for key, wave in (
                ("history-template-w3-surface-major-edit-v1", "W3"),
                ("history-template-w5-surface-correction-v1", "W5-pre-purge"),
            ):
                row = templates[key]
                self.assertEqual(row["wave"], wave)
                self.assertEqual(row["semantic_change_mode"], "surface-only")
                self.assertEqual(row["changed_fact_ids_rule"], "exact-empty")
                self.assertEqual(row["present_fact_ids_rule"], "exact-carry-forward")
            exact_duplicate = templates[
                "history-template-w3-exact-duplicate-v1"
            ]
            self.assertEqual(exact_duplicate["wave"], "W3")
            self.assertEqual(exact_duplicate["operation_kind"], "exact-duplicate")
            self.assertIs(exact_duplicate["creates_source"], False)
            self.assertIs(exact_duplicate["creates_source_version"], False)
            self.assertIs(exact_duplicate["creates_materialization"], True)
            for key in (
                "history-template-w5-replacement-create-index-v1",
                "history-template-w4-replacement-create-index-v1",
            ):
                self.assertIs(templates[key]["creates_source"], True)
                self.assertIs(templates[key]["creates_source_version"], True)
                self.assertIs(templates[key]["creates_materialization"], True)
            constraint = value["representative_transition_constraint"]
            self.assertEqual(constraint["w3_changed_fact_ids"], [])
            self.assertEqual(constraint["w5_changed_fact_ids"], [])
            self.assertTrue(
                history.require_surface_carry_forward(
                    constraint["present_fact_ids_at_w1"],
                    list(constraint["present_fact_ids_at_w1"]),
                    [],
                )
            )

    def test_surface_carry_forward_rejects_emptying_or_semantic_change(self):
        before = ["fact-syn-001", "fact-syn-002"]
        bad_cases = [
            ([], []),
            (["fact-syn-001"], []),
            (before, ["fact-syn-002"]),
            (["fact-syn-001", "fact-syn-003"], []),
        ]
        for after, changed in bad_cases:
            with self.subTest(after=after, changed=changed):
                with self.assertRaises(history.PersonaV2HistoryIntentError):
                    history.require_surface_carry_forward(before, after, changed)

    def test_conditional_cohort_profiles_do_not_assign_a_cohort(self):
        expected = {
            "P": [
                "history-template-w1-typed-small-edit-v1",
                "history-template-w5-replacement-create-index-v1",
                "history-template-w5-replacement-current-confirmation-v1",
                "history-template-w5-old-path-purge-v1",
                "history-template-w5-forced-purged-commit-v1",
                "history-template-w5-post-purge-noop-index-v1",
            ],
            "X": [
                "history-template-w1-typed-small-edit-v1",
                "history-template-w3-surface-major-edit-v1",
                "history-template-w4-delete-v1",
                "history-template-w4-replacement-create-index-v1",
            ],
            "Y": [
                "history-template-w1-typed-small-edit-v1",
                "history-template-w3-surface-major-edit-v1",
            ],
            "N": [
                "history-template-w3-surface-major-edit-v1",
                "history-template-w5-surface-correction-v1",
            ],
            "U": [],
        }
        for value in self.values:
            rows = value["history_cohort_templates"]
            self.assertEqual(
                [row["history_cohort_id"] for row in rows],
                list(history.HISTORY_COHORT_ORDER),
            )
            self.assertEqual(
                {
                    row["history_cohort_id"]: row["required_event_template_keys"]
                    for row in rows
                },
                expected,
            )
            self.assertNotIn("assigned_history_cohort_id", value)
            by_cohort = {row["history_cohort_id"]: row for row in rows}
            self.assertEqual(
                [
                    (edge["from_event_template_key"], edge["to_event_template_key"])
                    for edge in by_cohort["P"]["dependency_edges"]
                ],
                [
                    (
                        "history-template-w5-replacement-create-index-v1",
                        "history-template-w5-replacement-current-confirmation-v1",
                    ),
                    (
                        "history-template-w5-replacement-current-confirmation-v1",
                        "history-template-w5-old-path-purge-v1",
                    ),
                    (
                        "history-template-w5-old-path-purge-v1",
                        "history-template-w5-forced-purged-commit-v1",
                    ),
                    (
                        "history-template-w5-forced-purged-commit-v1",
                        "history-template-w5-post-purge-noop-index-v1",
                    ),
                ],
            )
            self.assertIn(
                "solver-history-cohort-assignment-not-available",
                value["remaining_blockers"],
            )

    def test_restore_and_final_deleted_dependencies_and_states_are_separate(self):
        for value in self.values:
            lifecycles = {
                row["required_evidence_state"]: row
                for row in value["lifecycle_templates"]
            }
            self.assertEqual(set(lifecycles), {"current-restored", "final-deleted"})
            restored = lifecycles["current-restored"]
            deleted = lifecycles["final-deleted"]
            event_templates = {
                row["event_template_key"]: row for row in value["event_templates"]
            }
            self.assertEqual(
                restored["event_template_keys"],
                [
                    "history-template-w4-delete-v1",
                    "history-template-w5-restore-v1",
                    "history-template-w5-destination-index-v1",
                ],
            )
            self.assertEqual(
                [
                    (edge["from_event_template_key"], edge["to_event_template_key"])
                    for edge in restored["dependency_edges"]
                ],
                [
                    (
                        "history-template-w4-delete-v1",
                        "history-template-w5-restore-v1",
                    ),
                    (
                        "history-template-w5-restore-v1",
                        "history-template-w5-destination-index-v1",
                    ),
                ],
            )
            self.assertEqual(
                [row["state"] for row in restored["checkpoint_states"]],
                [
                    "current",
                    "current",
                    "current",
                    "current",
                    "deleted",
                    "current-restored",
                    "current-restored",
                ],
            )
            self.assertEqual(
                [row["state"] for row in deleted["checkpoint_states"]],
                [
                    "current",
                    "current",
                    "current",
                    "current",
                    "deleted",
                    "deleted",
                    "final-deleted",
                ],
            )
            self.assertIs(restored["new_materialization_required"], True)
            self.assertIs(restored["destination_index_receipt_required"], True)
            restore_event = event_templates["history-template-w5-restore-v1"]
            self.assertIs(restore_event["creates_source"], False)
            self.assertIs(restore_event["creates_source_version"], False)
            self.assertIs(restore_event["creates_materialization"], True)
            self.assertEqual(
                restore_event["present_fact_ids_rule"], "exact-carry-forward"
            )
            self.assertIs(restored["restored_but_unindexed_satisfies"], False)
            self.assertIs(restored["same_content_other_current_copy_satisfies"], False)
            self.assertIs(deleted["include_deleted_required"], True)
            self.assertIs(deleted["destination_index_receipt_required"], False)
            for row in lifecycles.values():
                self.assertEqual(row["prototype_instance_count"], 0)
                self.assertIs(
                    row["counts_toward_required_anchor_inventory"], False
                )
                self.assertEqual(
                    row["distinct_logical_documents_required_per_persona"], 10
                )
                self.assertEqual(row["suite_distinct_logical_document_minimum"], 200)
            self.assertIs(value["lifecycle_anchor_inventory_complete"], False)

    def test_full_and_pilot_checkpoint_literals_and_replay_totals(self):
        value = self.values[0]
        for profile, expected in EXPECTED_CHECKPOINTS.items():
            actual = [
                (
                    row["checkpoint"],
                    row["current_contract_chunks"],
                    row["history_only_contract_chunks"],
                )
                for row in value["checkpoint_chunk_contract"][profile]
            ]
            self.assertEqual(actual, expected)
        full = EXPECTED_CHECKPOINTS["full"]
        per_replay = [
            (checkpoint, current * 20, historical * 20)
            for checkpoint, current, historical in full
        ]
        three_replays = [
            (checkpoint, current * 3, historical * 3)
            for checkpoint, current, historical in per_replay
        ]
        self.assertEqual(per_replay, EXPECTED_FULL_PER_REPLAY)
        self.assertEqual(three_replays, EXPECTED_FULL_THREE_REPLAYS)

    def test_dependency_hashes_and_all_authority_are_negative(self):
        for value, member in zip(self.values, self.memberships):
            bindings = value["input_bindings"]
            self.assertEqual(
                [row["name"] for row in bindings], ["envelope", "fact-membership"]
            )
            raw = fact_membership.canonical_json_bytes(member)
            self.assertEqual(bindings[1]["canonical_bytes"], len(raw))
            self.assertEqual(bindings[1]["sha256"], hashlib.sha256(raw).hexdigest())
            for key, flag in value["authority"].items():
                self.assertIs(type(flag), bool, key)
                self.assertIs(flag, False, key)
            for key, flag in value["isolation_policy"].items():
                self.assertIs(type(flag), bool, key)
                self.assertIs(flag, False, key)
            self.assertIn(
                "event-flow-chunk-delta-checkpoint-reconciliation-not-implemented",
                value["remaining_blockers"],
            )

    def test_mutations_and_execution_escalation_are_rejected(self):
        value = self.values[0]
        mutations = []
        changed = copy.deepcopy(value)
        changed["compiled_history_plan"] = True
        mutations.append(changed)
        changed = copy.deepcopy(value)
        changed["authority"]["authorizes_history_mutation"] = True
        mutations.append(changed)
        changed = copy.deepcopy(value)
        changed["representative_transition_constraint"]["w3_changed_fact_ids"] = [
            "fact-syn-001"
        ]
        mutations.append(changed)
        changed = copy.deepcopy(value)
        changed["lifecycle_templates"][0]["dependency_edges"].pop()
        mutations.append(changed)
        changed = copy.deepcopy(value)
        changed["assigned_history_cohort_id"] = "P"
        mutations.append(changed)
        for changed in mutations:
            with self.assertRaises(history.PersonaV2HistoryIntentError):
                history.validate_history_intent("p01", changed)
        with self.assertRaises(history.PersonaV2HistoryIntentError):
            history.require_compiled_history_plan()

    def test_typed_revision_helper_rejects_partial_or_double_application(self):
        revision = {
            "current_fact_id": "fact-syn-002",
            "prior_fact_ids": ["fact-syn-001"],
            "revision_chain_id": "revision-syn-001",
        }
        self.assertEqual(
            history.apply_typed_revision(["fact-syn-001", "fact-syn-003"], revision),
            {
                "changed_fact_ids": ["fact-syn-001", "fact-syn-002"],
                "present_fact_ids": ["fact-syn-002", "fact-syn-003"],
            },
        )
        for before in (
            ["fact-syn-003"],
            ["fact-syn-001", "fact-syn-002", "fact-syn-003"],
        ):
            with self.assertRaises(history.PersonaV2HistoryIntentError):
                history.apply_typed_revision(before, revision)
        malformed = copy.deepcopy(revision)
        malformed["revision_chain_id"] = ""
        with self.assertRaises(history.PersonaV2HistoryIntentError):
            history.apply_typed_revision(
                ["fact-syn-001", "fact-syn-003"], malformed
            )


if __name__ == "__main__":
    unittest.main()
