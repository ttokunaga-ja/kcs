#!/usr/bin/env python3
"""Tests for the immutable 20-person suite event schedule."""

import copy
import json
import unittest

from eval import generate_persona_corpus as generator
from eval import persona_allocation as allocation
from eval import persona_event_manifest as persona_events
from eval import persona_fixture_spec as spec
from eval import persona_suite_event_manifest as suite_events


def _persona_plan(persona, profile="tiny"):
    route = allocation.build_allocation_plan(persona, profile)
    return {
        "persona_id": persona["id"],
        "planned_contract_chunks": spec.contributor_plan(
            persona, profile
        )["target_chunks"],
        "scopes": generator._source_plan_for_persona(
            persona, profile, route
        ),
    }


def _replace_manifest(manifests, persona_id, replacement):
    return [
        replacement if value["persona_id"] == persona_id else value
        for value in manifests
    ]


class TestPersonaSuiteEventManifest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # This is intentionally tiny-only.  A full all-person suite belongs to
        # the separately capacity-gated formal run, not this unit test.
        cls.persona_plans = tuple(
            _persona_plan(persona) for persona in spec.PERSONAS
        )
        cls.persona_manifests = tuple(
            persona_events.build_event_manifest(plan, "tiny")
            for plan in cls.persona_plans
        )
        cls.suite_manifest = suite_events.build_suite_event_manifest(
            cls.persona_manifests, cls.persona_plans, "tiny"
        )

    def test_all_twenty_are_deterministic_hash_bound_and_root_independent(self):
        forward = self.suite_manifest
        reversed_input = suite_events.build_suite_event_manifest(
            tuple(reversed(self.persona_manifests)),
            tuple(reversed(self.persona_plans)),
            "tiny",
        )
        self.assertEqual(forward, reversed_input)
        self.assertTrue(suite_events.validate_suite_event_manifest(
            forward, self.persona_manifests, self.persona_plans, "tiny"
        ))
        self.assertEqual(len(
            suite_events.suite_event_manifest_sha256(forward)
        ), 64)
        self.assertEqual(forward["totals"]["personas"], 20)
        self.assertEqual(
            [value["persona_id"] for value in forward[
                "persona_event_manifests"
            ]],
            [persona["id"] for persona in spec.PERSONAS],
        )
        supplied_by_persona = {
            value["persona_id"]: value for value in self.persona_manifests
        }
        plans_by_persona = {
            value["persona_id"]: value for value in self.persona_plans
        }
        for value in forward["persona_event_manifests"]:
            self.assertEqual(
                value["event_manifest_sha256"],
                persona_events.event_manifest_sha256(
                    supplied_by_persona[value["persona_id"]]
                ),
            )
            self.assertEqual(
                value["persona_plan_sha256"],
                suite_events._digest(
                    plans_by_persona[value["persona_id"]]
                ),
            )

        schedule = forward["schedule"]
        self.assertEqual(
            len(schedule),
            sum(
                len(value["schedule"])
                for value in self.persona_manifests
            ),
        )
        self.assertEqual(
            forward["totals"]["schedule_items"], len(schedule)
        )
        self.assertEqual(
            forward["schedule_sha256"], suite_events._digest(schedule)
        )
        self.assertEqual(forward["execution_lock"], {
            "kind": "exclusive_replay_root_lock",
            "required_lock_count": 1,
            "coverage": "entire_suite_schedule",
            "acquire_before_first_item": True,
            "release_after_last_item": True,
        })
        for ordinal, item in enumerate(schedule, start=1):
            self.assertEqual(set(item), {
                "suite_schedule_ordinal",
                "wave",
                "phase",
                "item_id",
                "kind",
                "persona_id",
                "planned_item_sha256",
                "prior_item_id",
            })
            self.assertEqual(item["suite_schedule_ordinal"], ordinal)
            self.assertEqual(
                item["prior_item_id"],
                schedule[ordinal - 2]["item_id"] if ordinal > 1 else None,
            )

        encoded = json.dumps(forward, ensure_ascii=True, sort_keys=True)
        self.assertNotIn("/Users/", encoded)
        self.assertNotIn("replay_root_path", encoded)
        self.assertTrue(forward["contracts"]["root_independent"])

    def test_cross_person_wave_barriers_and_w5_pair_order_are_exact(self):
        schedule = self.suite_manifest["schedule"]
        persona_ordinal = {
            persona["id"]: ordinal
            for ordinal, persona in enumerate(spec.PERSONAS)
        }

        for wave in ("W1", "W2", "W3", "W4"):
            items = [value for value in schedule if value["wave"] == wave]
            phases = [value["phase"] for value in items]
            self.assertEqual(
                phases,
                sorted(
                    phases,
                    key=(
                        "regular_events",
                        "ordinary_auto_indexes",
                    ).index,
                ),
            )
            regular = [
                value for value in items
                if value["phase"] == "regular_events"
            ]
            indexes = [
                value for value in items
                if value["phase"] == "ordinary_auto_indexes"
            ]
            self.assertTrue(regular)
            self.assertTrue(indexes)
            self.assertTrue(all(value["kind"] == "event" for value in regular))
            self.assertTrue(all(
                value["kind"] == "boundary" for value in indexes
            ))
            for block in (regular, indexes):
                ordinals = [
                    persona_ordinal[value["persona_id"]] for value in block
                ]
                self.assertEqual(ordinals, sorted(ordinals))

        w5 = [value for value in schedule if value["wave"] == "W5"]
        expected_phase_order = (
            "regular_events",
            "ordinary_auto_indexes",
            "serialized_path_purges",
            "post_purge_noop_indexes",
        )
        self.assertEqual(
            [value["phase"] for value in w5],
            sorted(
                (value["phase"] for value in w5),
                key=expected_phase_order.index,
            ),
        )

        event_by_id = {
            event["event_id"]: event
            for manifest in self.persona_manifests
            for event in manifest["events"]
        }
        boundary_by_id = {
            boundary["boundary_id"]: boundary
            for manifest in self.persona_manifests
            for boundary in manifest["boundaries"]
        }
        serial = [
            value for value in w5
            if value["phase"] == "serialized_path_purges"
        ]
        self.assertEqual(len(serial) % 2, 0)
        actual_persona_sources = []
        for index in range(0, len(serial), 2):
            event_item, boundary_item = serial[index:index + 2]
            self.assertEqual(
                (event_item["kind"], boundary_item["kind"]),
                ("event", "boundary"),
            )
            self.assertEqual(
                event_item["persona_id"], boundary_item["persona_id"]
            )
            event = event_by_id[event_item["item_id"]]
            boundary = boundary_by_id[boundary_item["item_id"]]
            self.assertEqual(event["execution_phase"], "purge_serial")
            self.assertEqual(boundary["kind"], "purged_commit")
            self.assertEqual(
                boundary["covered_event_ids"], [event_item["item_id"]]
            )
            actual_persona_sources.append((
                persona_ordinal[event_item["persona_id"]],
                event["relation"]["source_ids"][0],
            ))
        self.assertEqual(
            actual_persona_sources, sorted(actual_persona_sources)
        )
        noops = [
            value for value in w5
            if value["phase"] == "post_purge_noop_indexes"
        ]
        self.assertTrue(all(
            boundary_by_id[value["item_id"]]["kind"] == "index_noop"
            for value in noops
        ))

    def test_validation_rejects_suite_and_supplied_hash_tampering(self):
        changed_item_hash = copy.deepcopy(self.suite_manifest)
        changed_item_hash["schedule"][0]["planned_item_sha256"] = "0" * 64
        with self.assertRaisesRegex(
            suite_events.SuiteEventManifestError, "canonical expansion"
        ):
            suite_events.validate_suite_event_manifest(
                changed_item_hash,
                self.persona_manifests,
                self.persona_plans,
                "tiny",
            )

        reordered = copy.deepcopy(self.suite_manifest)
        reordered["schedule"][0], reordered["schedule"][1] = (
            reordered["schedule"][1], reordered["schedule"][0]
        )
        with self.assertRaisesRegex(
            suite_events.SuiteEventManifestError, "canonical expansion"
        ):
            suite_events.validate_suite_event_manifest(
                reordered,
                self.persona_manifests,
                self.persona_plans,
                "tiny",
            )

        changed_persona = copy.deepcopy(self.persona_manifests[0])
        # Per-person canonical validation rejects a false plan binding before
        # suite scheduling or whole-manifest digest binding.
        changed_persona["inputs"]["persona_plan_sha256"] = "b" * 64
        changed_inputs = _replace_manifest(
            self.persona_manifests, "p01", changed_persona
        )
        with self.assertRaisesRegex(
            suite_events.SuiteEventManifestError, "not canonical"
        ):
            suite_events.validate_suite_event_manifest(
                self.suite_manifest,
                changed_inputs,
                self.persona_plans,
                "tiny",
            )

        changed_binding = copy.deepcopy(self.persona_manifests[0])
        changed_binding["schedule"][0]["planned_item_sha256"] = "f" * 64
        changed_inputs = _replace_manifest(
            self.persona_manifests, "p01", changed_binding
        )
        with self.assertRaisesRegex(
            suite_events.SuiteEventManifestError, "not canonical"
        ):
            suite_events.build_suite_event_manifest(
                changed_inputs, self.persona_plans, "tiny"
            )

        changed_phase = copy.deepcopy(self.persona_manifests[0])
        changed_phase["schedule"][0]["phase"] = "bogus"
        changed_inputs = _replace_manifest(
            self.persona_manifests, "p01", changed_phase
        )
        with self.assertRaisesRegex(
            suite_events.SuiteEventManifestError, "not canonical"
        ):
            suite_events.build_suite_event_manifest(
                changed_inputs, self.persona_plans, "tiny"
            )

    def test_canonical_plan_rejects_coherently_rehashed_semantic_tampering(self):
        self.assertTrue(persona_events.validate_event_manifest(
            self.persona_manifests[0], self.persona_plans[0], "tiny"
        ))

        changed_checkpoint = copy.deepcopy(self.persona_manifests[0])
        changed_checkpoint["checkpoints"]["W1"][
            "current_contract_chunks"
        ] += 1
        changed_inputs = _replace_manifest(
            self.persona_manifests, "p01", changed_checkpoint
        )
        with self.assertRaisesRegex(
            suite_events.SuiteEventManifestError, "not canonical"
        ):
            suite_events.build_suite_event_manifest(
                changed_inputs, self.persona_plans, "tiny"
            )

        # This mutation is internally self-hash consistent and would pass the
        # former suite-only inventory check.  The matching canonical persona
        # plan nevertheless fixes the exact operation and rejects it.
        changed_item = copy.deepcopy(self.persona_manifests[0])
        event = changed_item["events"][0]
        event["operation"] = "tampered-operation"
        event["event_sha256"] = suite_events._digest({
            key: value for key, value in event.items()
            if key != "event_sha256"
        })
        schedule_item = next(
            value for value in changed_item["schedule"]
            if value["item_id"] == event["event_id"]
        )
        schedule_item["planned_item_sha256"] = event["event_sha256"]
        changed_inputs = _replace_manifest(
            self.persona_manifests, "p01", changed_item
        )
        with self.assertRaisesRegex(
            suite_events.SuiteEventManifestError, "not canonical"
        ):
            suite_events.build_suite_event_manifest(
                changed_inputs, self.persona_plans, "tiny"
            )

        changed_logical_order = copy.deepcopy(self.persona_manifests[0])
        first_item = changed_logical_order["schedule"][0]
        first_event = next(
            value for value in changed_logical_order["events"]
            if value["event_id"] == first_item["item_id"]
        )
        first_event["logical_tick"] = 2
        unhashed = {
            key: value for key, value in first_event.items()
            if key != "event_sha256"
        }
        first_event["event_sha256"] = suite_events._digest(unhashed)
        first_item["planned_item_sha256"] = first_event["event_sha256"]
        changed_inputs = _replace_manifest(
            self.persona_manifests, "p01", changed_logical_order
        )
        with self.assertRaisesRegex(
            suite_events.SuiteEventManifestError, "not canonical"
        ):
            suite_events.build_suite_event_manifest(
                changed_inputs, self.persona_plans, "tiny"
            )

    def test_rejects_wrong_persona_fixture_profile_and_root_bindings(self):
        with self.assertRaisesRegex(
            suite_events.SuiteEventManifestError, "exactly 20"
        ):
            suite_events.build_suite_event_manifest(
                self.persona_manifests[:-1], self.persona_plans, "tiny"
            )

        duplicate = list(self.persona_manifests)
        duplicate[-1] = duplicate[0]
        with self.assertRaisesRegex(
            suite_events.SuiteEventManifestError, "duplicate persona"
        ):
            suite_events.build_suite_event_manifest(
                duplicate, self.persona_plans, "tiny"
            )

        with self.assertRaisesRegex(
            suite_events.SuiteEventManifestError, "exactly 20 persona plans"
        ):
            suite_events.build_suite_event_manifest(
                self.persona_manifests, self.persona_plans[:-1], "tiny"
            )

        duplicate_plans = list(self.persona_plans)
        duplicate_plans[-1] = duplicate_plans[0]
        with self.assertRaisesRegex(
            suite_events.SuiteEventManifestError, "duplicate persona plan"
        ):
            suite_events.build_suite_event_manifest(
                self.persona_manifests, duplicate_plans, "tiny"
            )

        wrong_profile = copy.deepcopy(self.persona_manifests[0])
        wrong_profile["profile"] = "pilot"
        with self.assertRaisesRegex(
            suite_events.SuiteEventManifestError, "profile differs"
        ):
            suite_events.build_suite_event_manifest(
                _replace_manifest(
                    self.persona_manifests, "p01", wrong_profile
                ),
                self.persona_plans,
                "tiny",
            )

        wrong_fixture = copy.deepcopy(self.persona_manifests[0])
        wrong_fixture["fixture_id"] = "not-the-frozen-fixture"
        with self.assertRaisesRegex(
            suite_events.SuiteEventManifestError, "fixture differs"
        ):
            suite_events.build_suite_event_manifest(
                _replace_manifest(
                    self.persona_manifests, "p01", wrong_fixture
                ),
                self.persona_plans,
                "tiny",
            )

        absolute = copy.deepcopy(self.persona_manifests[0])
        absolute["executor_hint"] = "/tmp/persona-replay"
        with self.assertRaisesRegex(
            suite_events.SuiteEventManifestError, "absolute path"
        ):
            suite_events.build_suite_event_manifest(
                _replace_manifest(self.persona_manifests, "p01", absolute),
                self.persona_plans,
                "tiny",
            )

        windows_rooted = copy.deepcopy(self.persona_manifests[0])
        windows_rooted["executor_hint"] = "\\rooted-on-current-drive"
        with self.assertRaisesRegex(
            suite_events.SuiteEventManifestError, "absolute path"
        ):
            suite_events.build_suite_event_manifest(
                _replace_manifest(
                    self.persona_manifests, "p01", windows_rooted
                ),
                self.persona_plans,
                "tiny",
            )

        root_specific = copy.deepcopy(self.persona_manifests[0])
        root_specific["replay_root"] = "relative-but-execution-specific"
        with self.assertRaisesRegex(
            suite_events.SuiteEventManifestError, "root-specific field"
        ):
            suite_events.build_suite_event_manifest(
                _replace_manifest(
                    self.persona_manifests, "p01", root_specific
                ),
                self.persona_plans,
                "tiny",
            )

        unknown_host_binding = copy.deepcopy(self.persona_manifests[0])
        unknown_host_binding["cwd"] = "private-host/worktree"
        with self.assertRaisesRegex(
            suite_events.SuiteEventManifestError, "root-specific field"
        ):
            suite_events.build_suite_event_manifest(
                _replace_manifest(
                    self.persona_manifests, "p01", unknown_host_binding
                ),
                self.persona_plans,
                "tiny",
            )

        rooted_plan = copy.deepcopy(self.persona_plans[0])
        rooted_plan["replay_root"] = "relative-but-execution-specific"
        rooted_plans = _replace_manifest(
            self.persona_plans, "p01", rooted_plan
        )
        with self.assertRaisesRegex(
            suite_events.SuiteEventManifestError, "root-specific field"
        ):
            suite_events.build_suite_event_manifest(
                self.persona_manifests, rooted_plans, "tiny"
            )


if __name__ == "__main__":
    unittest.main()
