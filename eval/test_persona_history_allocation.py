#!/usr/bin/env python3
"""Tests for deterministic source-level persona history allocation."""

import copy
import json
import unittest

from eval import generate_persona_corpus as generator
from eval import persona_allocation as allocation
from eval import persona_fixture_spec as spec
from eval import persona_history_allocation as history


def _persona_plan(persona, profile):
    route = allocation.build_allocation_plan(persona, profile)
    return {
        "persona_id": persona["id"],
        "planned_contract_chunks": spec.contributor_plan(persona, profile)[
            "target_chunks"
        ],
        "scopes": generator._source_plan_for_persona(
            persona, profile, route
        ),
    }


def _sum_replacements(rows):
    return sum(row["requested_contributor_chunks"] for row in rows)


class TestPersonaHistoryAllocation(unittest.TestCase):
    def test_every_persona_and_profile_has_exact_disjoint_whole_source_strata(self):
        for profile in ("tiny", "pilot", "full"):
            for persona in spec.PERSONAS:
                with self.subTest(profile=profile, persona=persona["id"]):
                    source_plan = _persona_plan(persona, profile)
                    plan = history.build_history_allocation(source_plan, profile)
                    self.assertTrue(
                        history.validate_history_allocation(
                            plan, source_plan, profile
                        )
                    )
                    round_tripped = json.loads(
                        json.dumps(plan, sort_keys=True, ensure_ascii=True)
                    )
                    self.assertEqual(round_tripped, plan)

                    strata = plan["strata"]
                    all_ids = [
                        source_id
                        for stratum in history.STRATUM_SELECTION_ORDER
                        for source_id in strata[stratum]["source_ids"]
                    ]
                    self.assertEqual(len(all_ids), len(set(all_ids)))
                    current = plan["current_contract_chunks"]
                    self.assertEqual(
                        strata[history.PURGE_AFTER_W1]["target_chunks"],
                        current * 4 // 100,
                    )
                    self.assertEqual(
                        strata[history.REPEAT_THEN_DELETE]["target_chunks"],
                        current * 10 // 100,
                    )
                    self.assertEqual(
                        strata[history.LATE_THEN_CORRECT]["target_chunks"],
                        current * 4 // 100,
                    )
                    self.assertEqual(
                        strata[history.REPEAT_LIVE]["target_chunks"],
                        current * 20 // 100
                        - current * 10 // 100
                        - current * 4 // 100,
                    )
                    self.assertEqual(
                        plan["waves"]["W1"]["history_only_delta_chunks"],
                        current * 20 // 100,
                    )
                    self.assertEqual(
                        plan["waves"]["W3"]["history_only_delta_chunks"],
                        current * 20 // 100,
                    )
                    self.assertEqual(
                        plan["waves"]["W4"]["history_only_delta_chunks"],
                        current * 10 // 100,
                    )
                    self.assertEqual(
                        plan["waves"]["W5"]["history_only_delta_chunks_net"],
                        0,
                    )

    def test_full_has_twenty_scope_coverage_and_formal_checkpoint_math(self):
        for persona in spec.PERSONAS:
            with self.subTest(persona=persona["id"]):
                plan = history.build_history_allocation(
                    _persona_plan(persona, "full"), "full"
                )
                for stratum in history.STRATUM_SELECTION_ORDER:
                    self.assertEqual(plan["strata"][stratum]["scope_count"], 20)
                    cap = (
                        plan["strata"][stratum]["target_chunks"] * 20 // 100
                        + spec.MAX_CONTRIBUTOR_CHUNKS_PER_FILE
                    )
                    for chunks in plan["strata"][stratum]["scope_chunks"].values():
                        self.assertGreater(chunks, 0)
                        self.assertLessEqual(chunks, cap)
                self.assertEqual(plan["waves"]["W1"]["affected_scope_keys"], plan["scope_keys"])
                self.assertEqual(plan["waves"]["W3"]["affected_scope_keys"], plan["scope_keys"])
                self.assertEqual(plan["waves"]["W4"]["affected_scope_keys"], plan["scope_keys"])
                self.assertEqual(plan["waves"]["W5"]["affected_scope_keys"], plan["scope_keys"])
                self.assertEqual(plan["checkpoints"]["W0"], {"current": 120_000, "history_only": 0})
                self.assertEqual(plan["checkpoints"]["W1"], {"current": 120_000, "history_only": 24_000})
                self.assertEqual(plan["checkpoints"]["W3"], {"current": 120_000, "history_only": 48_000})
                self.assertEqual(plan["checkpoints"]["W4"], {"current": 120_000, "history_only": 60_000})
                self.assertEqual(
                    plan["checkpoints"]["W5_pre_purge_auto"],
                    {"current": 124_800, "history_only": 64_800},
                )
                self.assertEqual(plan["checkpoints"]["W5"], {"current": 120_000, "history_only": 60_000})

    def test_replacements_preserve_scope_variant_and_quota_one_for_one(self):
        source_plan = _persona_plan(spec.get_persona("p14"), "full")
        sources = {
            row["source_id"]: dict(row, scope_key=scope["scope_key"])
            for scope in source_plan["scopes"]
            for row in scope["sources"]
        }
        plan = history.build_history_allocation(source_plan, "full")
        seen_new_ids = set(sources)
        for wave in ("W4", "W5"):
            replacements = plan["waves"][wave]["replacement_sources"]
            for replacement in replacements:
                old = sources[replacement["replaces_source_id"]]
                self.assertNotIn(replacement["source_id"], seen_new_ids)
                seen_new_ids.add(replacement["source_id"])
                for key in (
                    "schema_version", "scope_key", "family", "variant", "gate_role",
                    "expected_disposition", "extension", "media_type",
                    "requested_contributor_chunks",
                ):
                    self.assertEqual(replacement[key], old[key])
                self.assertNotEqual(replacement["file_name"], old["file_name"])
            self.assertEqual(
                _sum_replacements(replacements),
                plan["waves"][wave]["replacement_current_chunks"],
            )

    def test_w5_separates_current_history_and_total_purge_accounting(self):
        plan = history.build_history_allocation(
            _persona_plan(spec.get_persona("p01"), "full"), "full"
        )
        w5 = plan["waves"]["W5"]
        self.assertEqual(w5["correction_history_chunks"], 4_800)
        self.assertEqual(w5["pre_purge_current_contract_chunks"], 124_800)
        self.assertEqual(w5["pre_purge_history_only_contract_chunks"], 64_800)
        self.assertEqual(w5["purged_current_chunks"], 4_800)
        self.assertEqual(w5["purged_history_only_chunks"], 4_800)
        self.assertEqual(w5["purged_total_contract_chunk_rows"], 9_600)
        self.assertEqual(w5["purge_raw_versions_per_source"], 2)
        self.assertEqual(w5["replacement_current_chunks"], 4_800)
        self.assertEqual(w5["history_only_delta_chunks_net"], 0)
        self.assertEqual(w5["current_delta_chunks_net"], 0)
        self.assertEqual(w5["index_auto_scope_keys"], plan["scope_keys"])
        self.assertEqual(w5["index_noop_scope_keys"], plan["scope_keys"])
        self.assertEqual(
            w5["execution_order"],
            [
                "correct-n-create-p-replacements-and-zero-quota-restore",
                "index-auto-while-old-p-and-new-p-replacements-coexist",
                "remove-one-old-p-and-immediately-path-purge-in-source-order",
                "index-noop-per-purge-affected-scope",
            ],
        )

    def test_validator_rejects_changed_membership_or_quota(self):
        source_plan = _persona_plan(spec.get_persona("p03"), "pilot")
        plan = history.build_history_allocation(source_plan, "pilot")
        changed = copy.deepcopy(plan)
        changed["strata"][history.PURGE_AFTER_W1]["source_ids"].reverse()
        with self.assertRaisesRegex(
            history.HistoryAllocationError, "canonical allocation"
        ):
            history.validate_history_allocation(changed, source_plan, "pilot")

        bad_source = copy.deepcopy(source_plan)
        bad_source["scopes"][0]["sources"][0][
            "requested_contributor_chunks"
        ] = -1
        with self.assertRaisesRegex(
            history.HistoryAllocationError, "canonical W0 source expansion"
        ):
            history.build_history_allocation(bad_source, "pilot")

        wrong_profile_total = copy.deepcopy(source_plan)
        wrong_profile_total["planned_contract_chunks"] += 1
        contributor = next(
            source
            for scope in wrong_profile_total["scopes"]
            for source in scope["sources"]
            if source["gate_role"] == "contract_contributor"
        )
        contributor["requested_contributor_chunks"] += 1
        with self.assertRaisesRegex(
            history.HistoryAllocationError, "canonical W0 source expansion"
        ):
            history.build_history_allocation(wrong_profile_total, "pilot")

    def test_rejects_noncanonical_scope_variant_version_and_quota_cap(self):
        source_plan = _persona_plan(spec.get_persona("p01"), "full")
        mutations = []

        bad_scope = copy.deepcopy(source_plan)
        bad_scope["scopes"][0]["scope_key"] = "../../escape"
        mutations.append(bad_scope)

        bad_variant = copy.deepcopy(source_plan)
        bad_variant["scopes"][0]["sources"][0]["family"] = "bogus-family"
        bad_variant["scopes"][0]["sources"][0]["variant"] = "bogus-variant"
        bad_variant["scopes"][0]["sources"][0]["media_type"] = "text/evil"
        mutations.append(bad_variant)

        bad_version = copy.deepcopy(source_plan)
        bad_version["scopes"][0]["sources"][0]["version"] = 7
        mutations.append(bad_version)

        bad_quota = copy.deepcopy(source_plan)
        contributor = next(
            source
            for scope in bad_quota["scopes"]
            for source in scope["sources"]
            if source["gate_role"] == "contract_contributor"
        )
        bad_quota["planned_contract_chunks"] += (
            spec.MAX_CONTRIBUTOR_CHUNKS_PER_FILE + 1
            - contributor["requested_contributor_chunks"]
        )
        contributor["requested_contributor_chunks"] = (
            spec.MAX_CONTRIBUTOR_CHUNKS_PER_FILE + 1
        )
        mutations.append(bad_quota)

        for index, mutation in enumerate(mutations):
            with self.subTest(mutation=index):
                with self.assertRaisesRegex(
                    history.HistoryAllocationError,
                    "canonical W0 source expansion",
                ):
                    history.build_history_allocation(mutation, "full")

    def test_rejects_python_equal_noncanonical_scalar_types(self):
        source_plan = _persona_plan(spec.get_persona("p01"), "tiny")

        source_mutations = []
        bool_schema = copy.deepcopy(source_plan)
        bool_schema["scopes"][0]["sources"][0]["schema_version"] = True
        source_mutations.append(bool_schema)

        bool_version = copy.deepcopy(source_plan)
        bool_version["scopes"][0]["sources"][0]["version"] = False
        source_mutations.append(bool_version)

        float_total = copy.deepcopy(source_plan)
        float_total["planned_contract_chunks"] = float(
            float_total["planned_contract_chunks"]
        )
        source_mutations.append(float_total)

        for index, mutation in enumerate(source_mutations):
            with self.subTest(kind="source", mutation=index):
                with self.assertRaisesRegex(
                    history.HistoryAllocationError,
                    "canonical W0 source expansion",
                ):
                    history.build_history_allocation(mutation, "tiny")

        plan = history.build_history_allocation(source_plan, "tiny")
        history_mutations = []
        bool_schema = copy.deepcopy(plan)
        bool_schema["schema_version"] = True
        history_mutations.append(bool_schema)

        replacement = next(
            replacement
            for wave in ("W4", "W5")
            for replacement in plan["waves"][wave]["replacement_sources"]
        )
        bool_version = copy.deepcopy(plan)
        replacement_index = next(
            index
            for index, candidate in enumerate(
                bool_version["waves"]["W4"]["replacement_sources"]
                + bool_version["waves"]["W5"]["replacement_sources"]
            )
            if candidate["source_id"] == replacement["source_id"]
        )
        if replacement_index < len(
            bool_version["waves"]["W4"]["replacement_sources"]
        ):
            bool_version["waves"]["W4"]["replacement_sources"][
                replacement_index
            ]["version"] = False
        else:
            bool_version["waves"]["W5"]["replacement_sources"][
                replacement_index
                - len(bool_version["waves"]["W4"]["replacement_sources"])
            ]["version"] = False
        history_mutations.append(bool_version)

        float_current = copy.deepcopy(plan)
        float_current["current_contract_chunks"] = float(
            float_current["current_contract_chunks"]
        )
        history_mutations.append(float_current)

        for index, mutation in enumerate(history_mutations):
            with self.subTest(kind="history", mutation=index):
                with self.assertRaisesRegex(
                    history.HistoryAllocationError,
                    "canonical allocation",
                ):
                    history.validate_history_allocation(
                        mutation, source_plan, "tiny"
                    )


if __name__ == "__main__":
    unittest.main()
