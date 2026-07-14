import copy
import hashlib
import unittest

from eval import persona_v2_contract as envelope
from eval import persona_v2_fact_membership as membership
from eval import persona_v2_source_intent as source_intent


class PersonaV2FactMembershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.values = membership.build_fact_membership_suite()
        cls.sources = source_intent.build_source_intent_origin_shard_suite()

    def test_twenty_persona_representatives_are_bounded_and_deterministic(self):
        self.assertEqual(
            [value["persona_id"] for value in self.values],
            list(envelope.PERSONA_IDS),
        )
        intent_keys = []
        logical_document_keys = []
        digests = []
        for persona_id, value in zip(envelope.PERSONA_IDS, self.values):
            self.assertEqual(value["artifact_schema"], membership.ARTIFACT_SCHEMA)
            self.assertEqual(value["artifact_kind"], membership.ARTIFACT_KIND)
            self.assertEqual(value["artifact_schema_version"], 2)
            self.assertEqual(value["fixture_id"], envelope.FIXTURE_ID)
            self.assertEqual(value["representative_membership_count"], 1)
            self.assertIs(value["representative_vertical_slice_complete"], True)
            self.assertIs(value["fact_membership_inventory_complete"], False)
            self.assertIs(value["fact_oracle_input_closure_complete"], False)
            self.assertIs(value["g0_contract_frozen"], False)
            raw = membership.canonical_json_bytes(value)
            self.assertLessEqual(len(raw), membership.MAX_FACT_MEMBERSHIP_BYTES)
            digest = membership.fact_membership_sha256(persona_id, value)
            self.assertEqual(digest, hashlib.sha256(raw).hexdigest())
            self.assertTrue(membership.validate_fact_membership(persona_id, value))
            digests.append(digest)
            row = value["memberships"][0]
            intent_keys.append(row["intent_key"])
            logical_document_keys.append(row["logical_document_key"])
        self.assertEqual(len(intent_keys), len(set(intent_keys)))
        self.assertEqual(len(logical_document_keys), len(set(logical_document_keys)))
        self.assertEqual(len(digests), len(set(digests)))

    def test_source_intent_is_exact_owner_and_sections_are_total(self):
        for value, source in zip(self.values, self.sources):
            row = value["memberships"][0]
            intent = source["intent_rows"][0]
            fact_set = source["catalogs"]["present_fact_sets"][0]
            quota = source["catalogs"]["quota_contexts"][0]
            self.assertIs(
                value["source_intent_is_canonical_present_fact_set_owner"], True
            )
            self.assertEqual(row["intent_key"], intent["intent_key"])
            self.assertEqual(
                row["present_fact_set_key"], intent["present_fact_set_key"]
            )
            self.assertEqual(row["present_fact_ids"], fact_set["present_fact_ids"])
            self.assertEqual(
                row["allowed_history_cohort_ids"],
                quota["allowed_history_cohort_ids"],
            )
            self.assertEqual(row["allowed_history_cohort_ids"], ["P", "X", "Y"])
            self.assertTrue(
                membership.validate_exact_present_fact_projection(
                    fact_set["present_fact_ids"],
                    row["present_fact_ids"],
                    row["section_memberships"],
                )
            )
            self.assertEqual(
                [entry["fact_id"] for entry in row["section_memberships"]],
                row["present_fact_ids"],
            )

    def test_w0_revision_membership_requires_a_w1_edit_cohort(self):
        for value in self.values:
            row = value["memberships"][0]
            self.assertEqual(len(row["revision_memberships"]), 1)
            revision = row["revision_memberships"][0]
            self.assertTrue(
                set(revision["prior_fact_ids"]) <= set(row["present_fact_ids"])
            )
            self.assertNotIn(revision["current_fact_id"], row["present_fact_ids"])
            self.assertEqual(row["allowed_history_cohort_ids"], ["P", "X", "Y"])

    def test_dependency_bindings_are_one_way_and_exact(self):
        for value, source in zip(self.values, self.sources):
            bindings = value["input_bindings"]
            self.assertEqual(
                [row["name"] for row in bindings],
                ["fact-graph", "source-intent-origin-shard"],
            )
            source_binding = bindings[1]
            source_raw = source_intent.canonical_json_bytes(source)
            self.assertEqual(source_binding["canonical_bytes"], len(source_raw))
            self.assertEqual(
                source_binding["sha256"], hashlib.sha256(source_raw).hexdigest()
            )
            self.assertNotIn("fact-membership", [
                row["name"] for row in source["input_bindings"]
            ])

    def test_conflict_fact_precondition_is_projected_without_overlay_escalation(self):
        for value in self.values:
            conflict = value["conflict_copy_feasibility"]
            self.assertIs(conflict["conflict_overlay_membership_complete"], False)
            self.assertIs(
                conflict["unordered_w0_current_fact_pair_precondition_complete"],
                True,
            )
            self.assertIs(
                conflict["distinct_conflict_branch_membership_complete"], False
            )
            self.assertEqual(
                conflict["existing_unordered_w0_current_conflict_fact_pair_count"],
                1,
            )
            self.assertIs(conflict["fact_invention_allowed"], False)
            self.assertIs(
                conflict["requires_two_distinct_unordered_w0_current_branches"],
                True,
            )
            self.assertIn(
                "distinct-conflict-branch-membership-not-bound",
                value["remaining_blockers"],
            )
            row = value["memberships"][0]
            self.assertEqual(len(row["unordered_w0_current_fact_pairs"]), 1)
            members = row["unordered_w0_current_fact_pairs"][0]["member_fact_ids"]
            self.assertEqual(members, sorted(members))
            self.assertTrue(set(members) <= set(row["present_fact_ids"]))

    def test_every_authority_and_environment_capability_remains_false(self):
        for value in self.values:
            self.assertTrue(value["authority"])
            self.assertTrue(value["isolation_policy"])
            for key, flag in value["authority"].items():
                self.assertIs(type(flag), bool, key)
                self.assertIs(flag, False, key)
            for key, flag in value["isolation_policy"].items():
                self.assertIs(type(flag), bool, key)
                self.assertIs(flag, False, key)

    def test_projection_helper_rejects_missing_extra_duplicate_and_section_drift(self):
        source_ids = ["fact-syn-001", "fact-syn-002"]
        sections = [
            {"fact_id": "fact-syn-001", "section_key": "section-syn-001"},
            {"fact_id": "fact-syn-002", "section_key": "section-syn-002"},
        ]
        self.assertTrue(
            membership.validate_exact_present_fact_projection(
                source_ids, list(source_ids), sections
            )
        )
        bad_cases = [
            (["fact-syn-001"], sections[:1]),
            (source_ids + ["fact-syn-003"], sections + [{
                "fact_id": "fact-syn-003", "section_key": "section-syn-003"
            }]),
            (["fact-syn-001", "fact-syn-001"], sections),
            (source_ids, list(reversed(sections))),
            (source_ids, [sections[0], {
                "fact_id": "fact-syn-002", "section_key": "section-syn-001"
            }]),
        ]
        for projected, section_rows in bad_cases:
            with self.subTest(projected=projected, sections=section_rows):
                with self.assertRaises(membership.PersonaV2FactMembershipError):
                    membership.validate_exact_present_fact_projection(
                        source_ids, projected, section_rows
                    )

    def test_mutation_and_completion_escalation_are_rejected(self):
        value = self.values[0]
        mutations = []
        changed = copy.deepcopy(value)
        changed["memberships"][0]["present_fact_ids"].pop()
        mutations.append(changed)
        changed = copy.deepcopy(value)
        changed["authority"]["authorizes_g0_freeze"] = True
        mutations.append(changed)
        changed = copy.deepcopy(value)
        changed["fact_membership_inventory_complete"] = True
        mutations.append(changed)
        changed = copy.deepcopy(value)
        changed["conflict_copy_feasibility"][
            "conflict_overlay_membership_complete"
        ] = True
        mutations.append(changed)
        changed = copy.deepcopy(value)
        changed["conflict_copy_feasibility"][
            "distinct_conflict_branch_membership_complete"
        ] = True
        mutations.append(changed)
        changed = copy.deepcopy(value)
        changed["memberships"][0].pop("unordered_w0_current_fact_pairs")
        mutations.append(changed)
        changed = copy.deepcopy(value)
        changed["memberships"][0]["unordered_w0_current_fact_pairs"][0][
            "member_fact_ids"
        ].pop()
        mutations.append(changed)
        for changed in mutations:
            with self.assertRaises(membership.PersonaV2FactMembershipError):
                membership.validate_fact_membership("p01", changed)
        with self.assertRaises(membership.PersonaV2FactMembershipError):
            membership.require_fact_oracle_input_closure()

    def test_builds_are_detached(self):
        first = membership.build_fact_membership("p01")
        second = membership.build_fact_membership("p01")
        first["memberships"][0]["present_fact_ids"].pop()
        self.assertEqual(len(second["memberships"][0]["present_fact_ids"]), 8)


if __name__ == "__main__":
    unittest.main()
