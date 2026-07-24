#!/usr/bin/env python3
"""Tests for immutable root-independent persona event manifests."""

import copy
import json
import unittest

from eval import generate_persona_corpus as generator
from eval import persona_allocation as allocation
from eval import persona_event_manifest as event_manifest
from eval import persona_fixture_spec as spec


def _persona_plan(persona, profile="tiny"):
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


class TestPersonaEventManifest(unittest.TestCase):
    def test_p01_tiny_has_exact_chunk_and_physical_checkpoints(self):
        plan = _persona_plan(spec.get_persona("p01"))
        manifest = event_manifest.build_event_manifest(plan, "tiny")
        self.assertEqual(manifest["status"], "planned_not_observed")
        self.assertEqual(
            len(event_manifest.event_manifest_sha256(manifest)), 64
        )
        self.assertEqual(manifest["checkpoints"], {
            "W0": {
                "current_contract_chunks": 375,
                "history_only_contract_chunks": 0,
                "live_physical_files": 200,
            },
            "W1": {
                "current_contract_chunks": 375,
                "history_only_contract_chunks": 75,
                "live_physical_files": 201,
            },
            "W2": {
                "current_contract_chunks": 375,
                "history_only_contract_chunks": 75,
                "live_physical_files": 201,
            },
            "W3": {
                "current_contract_chunks": 375,
                "history_only_contract_chunks": 150,
                "live_physical_files": 204,
            },
            "W4": {
                "current_contract_chunks": 375,
                "history_only_contract_chunks": 187,
                "live_physical_files": 203,
            },
            "W5_pre_purge_auto": {
                "current_contract_chunks": 390,
                "history_only_contract_chunks": 202,
                "live_physical_files": 209,
            },
            "W5": {
                "current_contract_chunks": 375,
                "history_only_contract_chunks": 187,
                "live_physical_files": 204,
            },
        })
        self.assertEqual(
            manifest["totals"]["purged_commit_boundaries"], 5
        )
        self.assertEqual(manifest["totals"]["structural_events"], 11)
        self.assertEqual(manifest["totals"]["lifecycle_source_ids"], 220)
        self.assertEqual(manifest["totals"]["source_version_rows"], 275)
        self.assertEqual(
            manifest["totals"]["distinct_materialization_ids"], 222
        )
        self.assertEqual(manifest["event_arithmetic"], {
            "W1": {
                "current_contract_chunks": 0,
                "history_only_contract_chunks": 75,
                "live_physical_files": 1,
            },
            "W2": {
                "current_contract_chunks": 0,
                "history_only_contract_chunks": 0,
                "live_physical_files": 0,
            },
            "W3": {
                "current_contract_chunks": 0,
                "history_only_contract_chunks": 75,
                "live_physical_files": 3,
            },
            "W4": {
                "current_contract_chunks": 0,
                "history_only_contract_chunks": 37,
                "live_physical_files": -1,
            },
            "W5_pre_purge_auto": {
                "current_contract_chunks": 15,
                "history_only_contract_chunks": 15,
                "live_physical_files": 6,
            },
            "W5_purge": {
                "current_contract_chunks": -15,
                "history_only_contract_chunks": -15,
                "live_physical_files": -5,
            },
        })
        self.assertEqual(
            {
                wave: sum(
                    boundary["wave"] == wave
                    and boundary["kind"] == "index_auto"
                    for boundary in manifest["boundaries"]
                )
                for wave in ("W1", "W2", "W3", "W4", "W5")
            },
            {"W1": 13, "W2": 3, "W3": 14, "W4": 11, "W5": 10},
        )

        event_ids = [event["event_id"] for event in manifest["events"]]
        boundary_ids = [
            boundary["boundary_id"] for boundary in manifest["boundaries"]
        ]
        scheduled_ids = [item["item_id"] for item in manifest["schedule"]]
        self.assertEqual(len(event_ids), len(set(event_ids)))
        self.assertEqual(len(boundary_ids), len(set(boundary_ids)))
        self.assertFalse(set(event_ids) & set(boundary_ids))
        self.assertCountEqual(scheduled_ids, event_ids + boundary_ids)
        self.assertEqual(len(scheduled_ids), len(set(scheduled_ids)))

    def test_p01_full_manifest_reaches_formal_scale_and_all_w2_scopes(self):
        persona_plan = _persona_plan(spec.get_persona("p01"), "full")
        manifest = event_manifest.build_event_manifest(persona_plan, "full")

        self.assertEqual(manifest["checkpoints"]["W0"], {
            "current_contract_chunks": 120_000,
            "history_only_contract_chunks": 0,
            "live_physical_files": 12_000,
        })
        self.assertEqual(manifest["checkpoints"]["W5_pre_purge_auto"], {
            "current_contract_chunks": 124_800,
            "history_only_contract_chunks": 64_800,
            "live_physical_files": 12_305,
        })
        self.assertEqual(manifest["checkpoints"]["W5"], {
            "current_contract_chunks": 120_000,
            "history_only_contract_chunks": 60_000,
            "live_physical_files": 12_004,
        })
        self.assertEqual(
            {
                key: manifest["totals"][key]
                for key in (
                    "events",
                    "structural_events",
                    "boundaries",
                    "schedule_items",
                    "lifecycle_source_ids",
                    "source_version_rows",
                    "distinct_materialization_ids",
                )
            },
            {
                "events": 4_693,
                "structural_events": 30,
                "boundaries": 421,
                "schedule_items": 5_114,
                "lifecycle_source_ids": 13_056,
                "source_version_rows": 16_365,
                "distinct_materialization_ids": 13_058,
            },
        )

        active_scope_keys = {
            scope["scope_key"] for scope in persona_plan["scopes"]
        }
        w2_scope_keys = {
            boundary["scope_key"]
            for boundary in manifest["boundaries"]
            if boundary["wave"] == "W2"
            and boundary["kind"] == "index_auto"
        }
        self.assertEqual(len(active_scope_keys), 20)
        self.assertEqual(w2_scope_keys, active_scope_keys)

    def test_all_twenty_tiny_personas_are_deterministic_and_root_independent(self):
        for persona in spec.PERSONAS:
            with self.subTest(persona=persona["id"]):
                plan = _persona_plan(persona)
                first = event_manifest.build_event_manifest(plan, "tiny")
                second = event_manifest.build_event_manifest(plan, "tiny")
                self.assertEqual(first, second)
                self.assertEqual(
                    event_manifest._digest(first),
                    event_manifest._digest(second),
                )
                encoded = json.dumps(first, sort_keys=True, ensure_ascii=True)
                self.assertNotIn("/Users/", encoded)
                self.assertNotIn("commit_sha", encoded)
                self.assertEqual(first["persona_id"], persona["id"])
                self.assertEqual(first["profile"], "tiny")
                self.assertTrue(first["contracts"]["root_independent"])

    def test_index_boundaries_are_unique_and_cross_scope_refs_are_complete(self):
        manifest = event_manifest.build_event_manifest(
            _persona_plan(spec.get_persona("p02")), "tiny"
        )
        auto = [
            value for value in manifest["boundaries"]
            if value["kind"] == "index_auto"
        ]
        pairs = [(value["wave"], value["scope_key"]) for value in auto]
        self.assertEqual(len(pairs), len(set(pairs)))
        expected_pairs = {
            (event["wave"], scope_key)
            for event in manifest["events"]
            if event["execution_phase"] == "regular"
            for scope_key in event["index_scope_keys"]
        }
        self.assertEqual(set(pairs), expected_pairs)
        events_by_id = {
            event["event_id"]: event for event in manifest["events"]
        }
        self.assertTrue(any(
            {
                events_by_id[event_id]["lane"]
                for event_id in boundary["covered_event_ids"]
            }
            == {"history", "structural"}
            for boundary in auto
        ))

        moves = [
            event for event in manifest["events"]
            if event["operation"] == "cross_scope_move"
        ]
        self.assertEqual(len(moves), 2)
        for event in moves:
            refs = event["boundary_refs"]
            self.assertEqual(
                {value["role"] for value in refs},
                {"source_index", "destination_index"},
            )
            self.assertEqual({value["kind"] for value in refs}, {"index_auto"})
            self.assertTrue(all(value["boundary_id"] for value in refs))

        restore = next(
            event for event in manifest["events"]
            if event["operation"] == "restore_to_active_scope"
        )
        self.assertEqual(
            restore["source_command"]["kind"], "kio_restore_path"
        )
        self.assertEqual(
            restore["source_command"]["commit_boundary_kind"], "none"
        )
        self.assertIs(restore["source_command"]["force"], False)
        self.assertEqual(
            [value["kind"] for value in restore["boundary_refs"]],
            ["none", "index_auto"],
        )
        self.assertIsNone(restore["boundary_refs"][0]["boundary_id"])
        self.assertEqual(
            restore["boundary_refs"][1]["role"], "destination_index"
        )
        self.assertEqual(
            set(restore["affected_scope_keys"]),
            {
                restore["source_command"]["scope_key"],
                restore["boundary_refs"][1]["scope_key"],
            },
        )
        self.assertEqual(
            restore["restore_locator"]["expected_raw_sha256"],
            restore["state_transition"]["after"][0]["materialization"][
                "raw_sha256"
            ],
        )

    def test_w5_regular_auto_purge_commit_and_noop_order_is_frozen(self):
        manifest = event_manifest.build_event_manifest(
            _persona_plan(spec.get_persona("p01")), "tiny"
        )
        w5 = [item for item in manifest["schedule"] if item["wave"] == "W5"]
        phases = [item["phase"] for item in w5]
        self.assertEqual(
            phases,
            sorted(
                phases,
                key=(
                    "regular_events",
                    "ordinary_auto_indexes",
                    "serialized_path_purges",
                    "post_purge_noop_indexes",
                ).index,
            ),
        )
        serial = [
            item for item in w5 if item["phase"] == "serialized_path_purges"
        ]
        self.assertEqual(len(serial), 10)
        for index in range(0, len(serial), 2):
            event_item, boundary_item = serial[index:index + 2]
            self.assertEqual(event_item["item_kind"], "event")
            self.assertEqual(boundary_item["item_kind"], "boundary")
            self.assertIn("path-purge", event_item["item_id"])
            self.assertIn("purged-commit", boundary_item["item_id"])
            self.assertEqual(
                event_item["item_id"].rsplit("-", 1)[-1],
                boundary_item["item_id"].rsplit("-", 1)[-1],
            )

        for index, item in enumerate(manifest["schedule"]):
            self.assertEqual(
                item["prior_item_id"],
                manifest["schedule"][index - 1]["item_id"]
                if index else None,
            )

        purge_events = [
            event for event in manifest["events"]
            if event["operation"] == "unlink_then_path_purge"
        ]
        self.assertEqual(
            [event["relation"]["source_ids"][0] for event in purge_events],
            sorted(
                event["relation"]["source_ids"][0]
                for event in purge_events
            ),
        )
        for event in purge_events:
            self.assertEqual(
                event["source_command"]["kind"],
                "filesystem_unlink_exact_path",
            )
            self.assertEqual(
                [value["kind"] for value in event["boundary_refs"]],
                ["purged_commit", "index_noop"],
            )
            purge_boundary = next(
                boundary
                for boundary in manifest["boundaries"]
                if boundary["boundary_id"]
                == event["boundary_refs"][0]["boundary_id"]
            )
            self.assertEqual(
                purge_boundary["command"],
                {
                    "kind": "kio_purge_path",
                    "reason": "legal",
                    "confirmation": "yes",
                },
            )
            self.assertEqual(
                [value["source_version"] for value in event[
                    "history_purge_versions"
                ]],
                [0, 1],
            )
            self.assertTrue(all(
                len(value["raw_sha256"]) == 64
                and value["raw_bytes"] > 0
                and len(value["render_request_sha256"]) == 64
                for value in event["history_purge_versions"]
            ))

    def test_complete_state_raw_witness_and_event_hash_chains(self):
        manifest = event_manifest.build_event_manifest(
            _persona_plan(spec.get_persona("p03")), "tiny"
        )
        prior = None
        prior_root = manifest["managed_event_state"]["initial_root_sha256"]
        for event in manifest["events"]:
            before = event["state_transition"]["before"]
            after = event["state_transition"]["after"]
            before_paths = [
                (
                    value["materialization"]["current_scope_key"],
                    value["materialization"]["file_name"].casefold(),
                )
                for value in before
            ]
            after_paths = [
                (
                    value["materialization"]["current_scope_key"],
                    value["materialization"]["file_name"].casefold(),
                )
                for value in after
            ]
            self.assertEqual(before_paths, after_paths)
            self.assertEqual(
                event["managed_state_root_before_sha256"], prior_root
            )
            self.assertEqual(event["prior_event_sha256"], prior)
            unhashed = copy.deepcopy(event)
            digest = unhashed.pop("event_sha256")
            self.assertEqual(digest, event_manifest._digest(unhashed))
            prior = digest
            prior_root = event["managed_state_root_after_sha256"]
            for state in before + after:
                self.assertIn(state["presence"], ("present", "absent"))
                value = state["materialization"]
                self.assertEqual(len(value["raw_sha256"]), 64)
                self.assertEqual(len(value["render_request_sha256"]), 64)
                self.assertIs(type(value["raw_bytes"]), int)
                self.assertGreater(value["raw_bytes"], 0)
                self.assertNotIn("data", value)
        self.assertEqual(
            prior_root,
            manifest["managed_event_state"]["final_root_sha256"],
        )
        self.assertEqual(
            prior,
            manifest["managed_event_state"]["final_event_sha256"],
        )

        transform_kinds = {
            state["materialization"]["transform_witness"]["kind"]
            for event in manifest["events"]
            for state in event["state_transition"]["after"]
            if state["presence"] == "present"
            and state["materialization"]["transform_witness"] is not None
        }
        self.assertEqual(
            transform_kinds,
            {"near-png-one-channel/v1", "png-to-scan-pdf/v1"},
        )

    def test_validator_rejects_content_schedule_and_equal_scalar_tampering(self):
        persona_plan = _persona_plan(spec.get_persona("p01"))
        manifest = event_manifest.build_event_manifest(persona_plan, "tiny")
        self.assertTrue(event_manifest.validate_event_manifest(
            manifest, persona_plan, "tiny"
        ))
        mutations = []

        changed_raw = copy.deepcopy(manifest)
        changed_raw["events"][0]["state_transition"]["before"][0][
            "materialization"
        ]["raw_sha256"] = "0" * 64
        mutations.append(changed_raw)

        changed_schedule = copy.deepcopy(manifest)
        changed_schedule["schedule"][-2:] = reversed(
            changed_schedule["schedule"][-2:]
        )
        mutations.append(changed_schedule)

        bool_schema = copy.deepcopy(manifest)
        bool_schema["schema_version"] = True
        mutations.append(bool_schema)

        float_tick = copy.deepcopy(manifest)
        float_tick["schedule"][0]["logical_tick"] = 1.0
        mutations.append(float_tick)

        changed_witness = copy.deepcopy(manifest)
        transformed = next(
            state["materialization"]
            for event in changed_witness["events"]
            for state in event["state_transition"]["after"]
            if state["presence"] == "present"
            and state["materialization"]["transform_witness"] is not None
        )
        transformed["transform_witness"]["child_raw_sha256"] = "f" * 64
        mutations.append(changed_witness)

        for index, mutation in enumerate(mutations):
            with self.subTest(mutation=index):
                with self.assertRaisesRegex(
                    event_manifest.EventManifestError,
                    "canonical expansion",
                ):
                    event_manifest.validate_event_manifest(
                        mutation, persona_plan, "tiny"
                    )

    def test_internal_leaf_semantics_reject_false_arithmetic_parent_and_lineage(self):
        manifest = event_manifest.build_event_manifest(
            _persona_plan(spec.get_persona("p01")), "tiny"
        )

        false_chunks = copy.deepcopy(manifest["events"])
        history_edit = next(
            event for event in false_chunks
            if event["operation"] == "edit_v0_to_v1"
        )
        for side in ("before", "after"):
            value = history_edit["state_transition"][side][0][
                "materialization"
            ]
            value["requested_contributor_chunks"] = 17
            value["planned_contract_chunks"] = 17
        with self.assertRaisesRegex(
            event_manifest.EventManifestError, "declared event delta"
        ):
            event_manifest._event_delta([history_edit])

        wrong_parent = copy.deepcopy(manifest["events"])
        derived = next(
            event for event in wrong_parent
            if event["operation"] == "near_duplicate"
        )
        derived["relation"]["derived_from_source_ids"] = [
            "p01-src-999999"
        ]
        with self.assertRaisesRegex(
            event_manifest.EventManifestError, "render contract parents"
        ):
            event_manifest._validate_event_semantics(wrong_parent)

        crossed_lineage = copy.deepcopy(manifest["events"])
        states = [
            state["materialization"]
            for event in crossed_lineage
            for side in ("before", "after")
            for state in event["state_transition"][side]
            if state["presence"] == "present"
        ]
        first = states[0]
        second = next(
            value for value in states if value["source_id"] != first["source_id"]
        )
        second["materialization_id"] = first["materialization_id"]
        with self.assertRaisesRegex(
            event_manifest.EventManifestError, "crosses source lineage"
        ):
            event_manifest._validate_event_semantics(crossed_lineage)

    def test_structural_topology_raw_only_and_live_ids_are_leaf_bound(self):
        persona_plan = _persona_plan(spec.get_persona("p01"))
        manifest = event_manifest.build_event_manifest(
            persona_plan, "tiny"
        )

        contributor_rename = next(
            event for event in manifest["events"]
            if event["operation"] == "same_scope_rename"
        )
        self.assertGreater(
            event_manifest._present_materializations(
                contributor_rename, "before"
            )[0]["planned_contract_chunks"],
            0,
        )
        self.assertEqual(
            event_manifest._leaf_event_delta(contributor_rename),
            {"current": 0, "history_only": 0},
        )

        non_raw_move = copy.deepcopy(next(
            event for event in manifest["events"]
            if event["operation"] == "cross_scope_move"
        ))
        for side in ("before", "after"):
            for state in non_raw_move["state_transition"][side]:
                value = state["materialization"]
                value["gate_role"] = "contract_contributor"
                value["requested_contributor_chunks"] = 1
                value["planned_contract_chunks"] = 1
        with self.assertRaisesRegex(
            event_manifest.EventManifestError,
            "requires_raw_only structural leaves",
        ):
            event_manifest._leaf_event_delta(non_raw_move)

        reused_alias_id = copy.deepcopy(manifest["events"])
        exact = next(
            event for event in reused_alias_id
            if event["operation"] == "exact_duplicate"
        )
        parent_id = event_manifest._present_materializations(
            exact, "before"
        )[0]["materialization_id"]
        for side in ("before", "after"):
            for state in exact["state_transition"][side]:
                value = state["materialization"]
                if value["materialization_id"] != parent_id:
                    value["materialization_id"] = parent_id
        with self.assertRaisesRegex(
            event_manifest.EventManifestError,
            "alias topology|multiple paths",
        ):
            event_manifest._validate_event_semantics(
                reused_alias_id,
                event_manifest._w0_materialization_owners(persona_plan),
            )

        w0_collision = copy.deepcopy(manifest["events"])
        exact = next(
            event for event in w0_collision
            if event["operation"] == "exact_duplicate"
        )
        event_source_ids = {
            state["materialization"]["source_id"]
            for event in w0_collision
            for side in ("before", "after")
            for state in event["state_transition"][side]
        }
        untouched_owner = next(
            owner
            for owner in event_manifest._w0_materialization_owners(
                persona_plan
            )
            if owner["source_id"] not in event_source_ids
        )
        alias_id = exact["relation"]["materialization_ids"][1]
        for side in ("before", "after"):
            for state in exact["state_transition"][side]:
                if state["materialization"]["materialization_id"] == alias_id:
                    state["materialization"]["materialization_id"] = (
                        untouched_owner["materialization_id"]
                    )
        exact["relation"]["materialization_ids"][1] = untouched_owner[
            "materialization_id"
        ]
        with self.assertRaisesRegex(
            event_manifest.EventManifestError,
            "crosses source lineage|multiple paths",
        ):
            event_manifest._validate_event_semantics(
                w0_collision,
                event_manifest._w0_materialization_owners(persona_plan),
            )

    def test_history_raw_purge_relation_restore_and_boundary_bindings(self):
        persona_plan = _persona_plan(spec.get_persona("p01"))
        manifest = event_manifest.build_event_manifest(
            persona_plan, "tiny"
        )
        owners = event_manifest._w0_materialization_owners(persona_plan)

        same_raw_edit = copy.deepcopy(next(
            event for event in manifest["events"]
            if event["operation"] == "edit_v0_to_v1"
        ))
        old = event_manifest._present_materializations(
            same_raw_edit, "before"
        )[0]
        new = event_manifest._present_materializations(
            same_raw_edit, "after"
        )[0]
        new["raw_sha256"] = old["raw_sha256"]
        with self.assertRaisesRegex(
            event_manifest.EventManifestError,
            "history edit source/version contract",
        ):
            event_manifest._leaf_event_delta(same_raw_edit)

        same_raw_x = copy.deepcopy(next(
            event for event in manifest["events"]
            if event["operation"] == "replace_x_one_for_one"
        ))
        old = event_manifest._present_materializations(same_raw_x, "before")[0]
        new = event_manifest._present_materializations(same_raw_x, "after")[0]
        new["raw_sha256"] = old["raw_sha256"]
        with self.assertRaisesRegex(
            event_manifest.EventManifestError,
            "X replacement",
        ):
            event_manifest._leaf_event_delta(same_raw_x)

        bad_purge_content = copy.deepcopy(manifest["events"])
        purge = next(
            event for event in bad_purge_content
            if event["operation"] == "unlink_then_path_purge"
        )
        purge["history_purge_versions"][0]["raw_sha256"] = "a" * 64
        with self.assertRaisesRegex(
            event_manifest.EventManifestError,
            "purge content differs",
        ):
            event_manifest._validate_event_semantics(
                bad_purge_content, owners
            )

        bad_alias_relation = copy.deepcopy(manifest["events"])
        exact = next(
            event for event in bad_alias_relation
            if event["operation"] == "exact_duplicate"
        )
        exact["relation"]["alias_of_materialization_ids"] = []
        with self.assertRaisesRegex(
            event_manifest.EventManifestError,
            "typed relation differs",
        ):
            event_manifest._validate_event_semantics(
                bad_alias_relation, owners
            )

        bad_restore_locator = copy.deepcopy(manifest["events"])
        restore = next(
            event for event in bad_restore_locator
            if event["operation"] == "restore_to_active_scope"
        )
        restore["restore_locator"]["source_file_name"] = "wrong.txt"
        with self.assertRaisesRegex(
            event_manifest.EventManifestError,
            "restore relation/locator",
        ):
            event_manifest._validate_event_semantics(
                bad_restore_locator, owners
            )

        same_raw_p = copy.deepcopy(manifest["events"])
        create = next(
            event for event in same_raw_p
            if event["operation"] == "create_p_replacement"
        )
        replaced_source_id = create["relation"]["replaces_source_ids"][0]
        purge = next(
            event for event in same_raw_p
            if event["operation"] == "unlink_then_path_purge"
            and event["relation"]["source_ids"] == [replaced_source_id]
        )
        old_raw = purge["history_purge_versions"][0]["raw_sha256"]
        new_source_id = create["relation"]["source_ids"][0]
        for side in ("before", "after"):
            for state in create["state_transition"][side]:
                value = state["materialization"]
                if value["source_id"] == new_source_id:
                    value["raw_sha256"] = old_raw
        with self.assertRaisesRegex(
            event_manifest.EventManifestError,
            "P replacement is not raw-distinct",
        ):
            event_manifest._validate_event_semantics(same_raw_p, owners)

        bad_boundary = copy.deepcopy(manifest)
        purge_boundary = next(
            boundary for boundary in bad_boundary["boundaries"]
            if boundary["kind"] == "purged_commit"
        )
        purge_boundary["source_id"] = "p01-src-999999"
        with self.assertRaisesRegex(
            event_manifest.EventManifestError,
            "purged boundary source differs",
        ):
            event_manifest._validate_event_graph(
                bad_boundary["events"],
                bad_boundary["boundaries"],
                bad_boundary["schedule"],
            )

    def test_structural_operations_are_bound_to_typed_transform_formats(self):
        manifest = event_manifest.build_event_manifest(
            _persona_plan(spec.get_persona("p01")), "tiny"
        )

        wrong_near_contract = copy.deepcopy(next(
            event for event in manifest["events"]
            if event["operation"] == "near_duplicate"
        ))
        parent = event_manifest._present_materializations(
            wrong_near_contract, "before"
        )[0]
        child = next(
            value
            for value in event_manifest._present_materializations(
                wrong_near_contract, "after"
            )
            if value["source_id"] != parent["source_id"]
        )
        child["render_contract"]["kind"] = "png-to-scan-pdf/v1"
        child["transform_witness"]["kind"] = "png-to-scan-pdf/v1"
        wrong_near_contract["relation"]["kind"] = "png-to-scan-pdf"
        with self.assertRaisesRegex(
            event_manifest.EventManifestError,
            "typed transform contract",
        ):
            event_manifest._leaf_event_delta(wrong_near_contract)

        wrong_derived_format = copy.deepcopy(next(
            event for event in manifest["events"]
            if event["operation"] == "derived_format"
        ))
        parent = event_manifest._present_materializations(
            wrong_derived_format, "before"
        )[0]
        child = next(
            value
            for value in event_manifest._present_materializations(
                wrong_derived_format, "after"
            )
            if value["source_id"] != parent["source_id"]
        )
        child.update({
            "family": "image",
            "variant": "png",
            "extension": "png",
            "media_type": "image/png",
        })
        child["render_request"]["family"] = "image"
        child["render_request"]["variant"] = "png"
        with self.assertRaisesRegex(
            event_manifest.EventManifestError,
            "child format contract differs",
        ):
            event_manifest._leaf_event_delta(wrong_derived_format)

        wrong_renderer = copy.deepcopy(next(
            event for event in manifest["events"]
            if event["operation"] == "near_duplicate"
        ))
        parent = event_manifest._present_materializations(
            wrong_renderer, "before"
        )[0]
        child = next(
            value
            for value in event_manifest._present_materializations(
                wrong_renderer, "after"
            )
            if value["source_id"] != parent["source_id"]
        )
        child["renderer_id"] = "wrong-renderer"
        with self.assertRaisesRegex(
            event_manifest.EventManifestError,
            "child format contract differs",
        ):
            event_manifest._leaf_event_delta(wrong_renderer)


if __name__ == "__main__":
    unittest.main()
