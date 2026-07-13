#!/usr/bin/env python3
"""Tests for canonical quota-neutral persona structural allocation."""

import copy
import unittest

from eval import generate_persona_corpus as generator
from eval import persona_allocation as allocation
from eval import persona_fixture_spec as spec
from eval import persona_history_allocation as history
from eval import persona_renderers as renderers
from eval import persona_structural_allocation as structural


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


class TestPersonaStructuralAllocation(unittest.TestCase):
    def test_all_personas_and_profiles_have_exact_structural_inventory(self):
        expected_counts = {
            "tiny": structural.MINIMAL_EVENT_COUNTS,
            "pilot": structural.MINIMAL_EVENT_COUNTS,
            "full": structural.FULL_EVENT_COUNTS,
        }
        expected_totals = {"tiny": 4_080, "pilot": 20_080, "full": 195_080}
        for profile in ("tiny", "pilot", "full"):
            suite_live = 0
            for persona in spec.PERSONAS:
                with self.subTest(profile=profile, persona=persona["id"]):
                    persona_plan = _persona_plan(persona, profile)
                    plan = structural.build_structural_allocation(
                        persona_plan, profile
                    )
                    self.assertEqual(
                        plan["event_counts_by_wave"], expected_counts[profile]
                    )
                    self.assertEqual(
                        plan["totals"]["events"],
                        sum(expected_counts[profile].values()),
                    )
                    self.assertEqual(
                        plan["totals"]["final_live_physical_file_delta"], 4
                    )
                    self.assertEqual(
                        plan["physical_file_delta_by_checkpoint"],
                        {"W0": 0, "W1": 1, "W2": 1, "W3": 4, "W4": 3, "W5": 4},
                    )
                    self.assertTrue(
                        all(
                            event["expected_contract_chunk_delta"]
                            == {"current": 0, "history_only": 0}
                            for event in plan["events"]
                        )
                    )
                    self.assertEqual(
                        plan["anchors"]["raw_traveler"]["family"],
                        structural.TRAVELER_FAMILY_BY_PERSONA[persona["id"]],
                    )
                    self.assertEqual(
                        plan["anchors"]["raw_traveler"]["gate_role"],
                        "raw_only",
                    )
                    self.assertEqual(
                        plan["anchors"]["raw_traveler"][
                            "requested_contributor_chunks"
                        ],
                        0,
                    )
                    if profile == "full":
                        self.assertEqual(
                            plan["structural_index_scope_keys_by_wave"]["W2"],
                            plan["scope_keys"],
                        )
                        self.assertEqual(
                            len(plan["anchors"]["rename_u_sources"]), 20
                        )
                    else:
                        self.assertEqual(
                            len(plan["anchors"]["rename_u_sources"]), 1
                        )
                    suite_live += sum(
                        len(scope["sources"]) for scope in persona_plan["scopes"]
                    ) + 4
            self.assertEqual(suite_live, expected_totals[profile])

    def test_lineages_materializations_and_source_namespace_are_disjoint(self):
        persona = spec.get_persona("p17")
        persona_plan = _persona_plan(persona, "tiny")
        plan = structural.build_structural_allocation(persona_plan, "tiny")
        history_plan = history.build_history_allocation(persona_plan, "tiny")

        w0_ids = {
            source["source_id"]
            for scope in persona_plan["scopes"]
            for source in scope["sources"]
        }
        replacement_ids = {
            row["source_id"]
            for wave in ("W4", "W5")
            for row in history_plan["waves"][wave]["replacement_sources"]
        }
        structural_ids = set(
            plan["source_namespace"]["structural_source_ids"]
        )
        self.assertEqual(len(structural_ids), 3)
        self.assertFalse(structural_ids & w0_ids)
        self.assertFalse(structural_ids & replacement_ids)

        sources = {
            row["source_id"]: row
            for row in (
                plan["anchors"]["rename_u_sources"]
                + [
                    plan["anchors"]["raw_traveler"],
                    plan["anchors"]["near_png_parent"],
                    plan["anchors"]["derive_png_parent"],
                ]
                + plan["new_sources"]
            )
        }
        cohort_ids = {
            source_id
            for row in history_plan["strata"].values()
            for source_id in row["source_ids"]
        }
        for source in plan["anchors"]["rename_u_sources"]:
            self.assertEqual(source["gate_role"], "contract_contributor")
            self.assertNotIn(source["source_id"], cohort_ids)

        for event in plan["events"]:
            if event["requires_raw_only"]:
                for materialization in (
                    event["before_materializations"]
                    + event["after_materializations"]
                ):
                    self.assertEqual(
                        sources[materialization["source_id"]]["gate_role"],
                        "raw_only",
                    )
                    self.assertEqual(
                        sources[materialization["source_id"]][
                            "requested_contributor_chunks"
                        ],
                        0,
                    )

        exact = next(
            event for event in plan["events"]
            if event["operation"] == "exact_duplicate"
        )
        self.assertEqual(len(exact["before_materializations"]), 1)
        self.assertEqual(len(exact["after_materializations"]), 2)
        self.assertEqual(
            {row["source_id"] for row in exact["after_materializations"]},
            {exact["before_materializations"][0]["source_id"]},
        )
        self.assertEqual(
            len({row["materialization_id"] for row in exact["after_materializations"]}),
            2,
        )
        self.assertEqual(
            exact["relation"]["alias_of_materialization_ids"],
            [exact["before_materializations"][0]["materialization_id"]],
        )
        self.assertEqual(exact["relation"]["derived_from_source_ids"], [])

        restore = next(
            event for event in plan["events"]
            if event["operation"] == "restore_to_active_scope"
        )
        self.assertEqual(restore["before_materializations"], [])
        self.assertEqual(len(restore["after_materializations"]), 1)
        self.assertNotEqual(
            restore["command_scope_key"],
            restore["after_materializations"][0]["current_scope_key"],
        )
        self.assertIn(
            restore["after_materializations"][0]["current_scope_key"],
            plan["scope_keys"],
        )
        self.assertEqual(
            restore["relation"]["restored_from_materialization_ids"],
            [restore["restore_locator"]["source_materialization_id"]],
        )
        self.assertEqual(restore["restore_locator"]["kind"], "path-at-checkpoint")
        self.assertEqual(restore["restore_locator"]["checkpoint"], "W4")
        self.assertIs(restore["restore_locator"]["expected_purged"], False)
        self.assertEqual(
            restore["restore_locator"]["command_boundary_kind"], "none"
        )
        self.assertEqual(
            restore["restore_locator"]["destination_scope_key"],
            restore["after_materializations"][0]["current_scope_key"],
        )

    def test_near_and_derived_sources_have_machine_readable_transform_contracts(self):
        plan = structural.build_structural_allocation(
            _persona_plan(spec.get_persona("p02"), "tiny"), "tiny"
        )
        by_kind = {
            row["render_contract"]["kind"]: row
            for row in plan["new_sources"]
        }
        near = by_kind["near-png-one-channel/v1"]
        derived = by_kind["png-to-scan-pdf/v1"]
        self.assertEqual((near["family"], near["variant"]), ("image", "png"))
        self.assertEqual(
            (derived["family"], derived["variant"]),
            ("pdf_scan", "pdf-scan"),
        )
        self.assertEqual(near["gate_role"], "raw_only")
        self.assertEqual(derived["gate_role"], "raw_only")
        self.assertNotEqual(
            near["render_contract"]["parent_source_ids"],
            derived["render_contract"]["parent_source_ids"],
        )

    def test_validator_rejects_tamper_and_python_equal_scalar_types(self):
        persona_plan = _persona_plan(spec.get_persona("p01"), "tiny")
        plan = structural.build_structural_allocation(persona_plan, "tiny")
        self.assertTrue(
            structural.validate_structural_allocation(
                plan, persona_plan, "tiny"
            )
        )

        mutations = []
        changed_path = copy.deepcopy(plan)
        changed_path["events"][0]["after_materializations"][0][
            "file_name"
        ] = "forged.md"
        mutations.append(changed_path)

        bool_schema = copy.deepcopy(plan)
        bool_schema["schema_version"] = True
        mutations.append(bool_schema)

        float_ordinal = copy.deepcopy(plan)
        float_ordinal["events"][0]["ordinal"] = 1.0
        mutations.append(float_ordinal)

        changed_relation = copy.deepcopy(plan)
        changed_relation["events"][-1]["relation"]["prior_event_ids"] = []
        mutations.append(changed_relation)

        for index, mutation in enumerate(mutations):
            with self.subTest(mutation=index):
                with self.assertRaisesRegex(
                    structural.StructuralAllocationError,
                    "canonical allocation",
                ):
                    structural.validate_structural_allocation(
                        mutation, persona_plan, "tiny"
                    )

    def test_public_materialization_helper_matches_w0_projection(self):
        persona = spec.get_persona("p03")
        persona_plan = _persona_plan(persona, "tiny")
        scope = persona_plan["scopes"][0]
        source = scope["sources"][0]
        result = generator.materialize_source(persona["id"], scope, source)
        self.assertEqual(result["source"], source)
        self.assertEqual(result["request"].source_id, source["source_id"])
        self.assertEqual(
            result["physical"]["raw_sha256"],
            generator._sha256(result["rendered"].data),
        )
        self.assertEqual(
            result["physical"]["relative_path"],
            f"{scope['relative_path']}/{source['file_name']}",
        )

    def test_structural_materializer_dispatches_parent_bound_transforms(self):
        persona = spec.get_persona("p02")
        persona_plan = _persona_plan(persona, "tiny")
        scope_by_key = {
            scope["scope_key"]: scope for scope in persona_plan["scopes"]
        }
        plan = structural.build_structural_allocation(persona_plan, "tiny")
        new_by_kind = {
            source["render_contract"]["kind"]: source
            for source in plan["new_sources"]
        }
        cases = (
            (
                plan["anchors"]["near_png_parent"],
                new_by_kind["near-png-one-channel/v1"],
            ),
            (
                plan["anchors"]["derive_png_parent"],
                new_by_kind["png-to-scan-pdf/v1"],
            ),
        )
        for parent_source, child_source in cases:
            with self.subTest(kind=child_source["render_contract"]["kind"]):
                parent_scope = scope_by_key[
                    parent_source["render_origin_scope_key"]
                ]
                child_scope = scope_by_key[
                    child_source["render_origin_scope_key"]
                ]
                parent = generator.materialize_source(
                    persona["id"], parent_scope, parent_source
                )
                child = generator.materialize_structural_source(
                    persona["id"],
                    child_scope,
                    child_source,
                    parent_materializations=(parent,),
                )
                self.assertEqual(
                    child["transform_witness"]["parent_raw_sha256"],
                    parent["physical"]["raw_sha256"],
                )
                self.assertEqual(
                    child["transform_witness"]["child_raw_sha256"],
                    child["physical"]["raw_sha256"],
                )
                self.assertNotEqual(
                    child["physical"]["raw_sha256"],
                    parent["physical"]["raw_sha256"],
                )

        near_parent, near_source = cases[0]
        near_parent_scope = scope_by_key[near_parent["render_origin_scope_key"]]
        near_parent_rendered = generator.materialize_source(
            persona["id"], near_parent_scope, near_parent
        )
        near = generator.materialize_structural_source(
            persona["id"],
            scope_by_key[near_source["render_origin_scope_key"]],
            near_source,
            parent_materializations=(near_parent_rendered,),
        )
        parent_pixels = renderers.decode_fixture_png_rgb(
            near_parent_rendered["rendered"].data
        )
        child_pixels = renderers.decode_fixture_png_rgb(near["rendered"].data)
        self.assertEqual(
            sum(left != right for left, right in zip(parent_pixels, child_pixels)),
            1,
        )


if __name__ == "__main__":
    unittest.main()
