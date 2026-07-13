#!/usr/bin/env python3
"""Focused tests for deterministic persona format-by-scope allocation."""

import copy
import json
import json
import unittest

from eval import persona_allocation as allocation
from eval import persona_fixture_spec as spec


class TestPersonaAllocation(unittest.TestCase):
    def test_plan_is_stable_across_canonical_json_round_trip(self):
        for profile in ("tiny", "pilot", "full"):
            for persona in spec.PERSONAS:
                with self.subTest(profile=profile, persona=persona["id"]):
                    plan = allocation.build_allocation_plan(persona, profile)
                    loaded = json.loads(
                        json.dumps(plan, ensure_ascii=False, sort_keys=True)
                    )
                    self.assertEqual(loaded, plan)
                    self.assertTrue(
                        allocation.validate_allocation_plan(loaded, persona)
                    )

    def test_validator_rejects_a_noncanonical_equal_marginal_route(self):
        plan = allocation.build_allocation_plan("p01", "full")
        # Find a 2x2 contributor cycle with positive diagonal cells.  Moving
        # one unit around the cycle preserves every row and column marginal,
        # but it is not the frozen min-cost route.
        assignments = plan["assignments"]
        by_cell = {
            (row["family"], row["variant"], row["scope_key"]): row
            for row in assignments
        }
        changed = False
        contributor_rows = [
            row for row in assignments
            if row["gate_role"] == "contract_contributor" and row["count"] > 1
        ]
        for left in contributor_rows:
            if changed:
                break
            for right in contributor_rows:
                if (
                    left["scope_key"] == right["scope_key"]
                    or (left["family"], left["variant"])
                    == (right["family"], right["variant"])
                ):
                    continue
                def cross(source, destination):
                    key = (
                        source["family"], source["variant"],
                        destination["scope_key"],
                    )
                    row = by_cell.get(key)
                    if row is None:
                        family = source["family"]
                        relative_path = destination["relative_path"]
                        row = {
                            "scope_key": destination["scope_key"],
                            "relative_path": relative_path,
                            "family": family,
                            "variant": source["variant"],
                            "gate_role": source["gate_role"],
                            "expected_disposition": source[
                                "expected_disposition"
                            ],
                            "count": 0,
                            "route_affinity": allocation.route_affinity(
                                family, relative_path
                            ),
                            "matched_route_hints": list(
                                allocation.matched_route_hints(
                                    family, relative_path
                                )
                            ),
                        }
                        assignments.append(row)
                        by_cell[key] = row
                    return row

                cross_left = cross(left, right)
                cross_right = cross(right, left)
                left["count"] -= 1
                right["count"] -= 1
                cross_left["count"] += 1
                cross_right["count"] += 1
                changed = True
                break
        self.assertTrue(changed, "fixture must expose an equal-marginal cycle")
        plan["routing_affinity_total"] = sum(
            row["count"] * row["route_affinity"] for row in assignments
        )
        with self.assertRaisesRegex(
            allocation.AllocationError, "canonical min-cost route"
        ):
            allocation.validate_allocation_plan(plan, "p01")

    def test_all_profiles_preserve_every_row_column_and_contributor_floor(self):
        for profile in ("tiny", "pilot", "full"):
            for persona in spec.PERSONAS:
                with self.subTest(profile=profile, persona=persona["id"]):
                    plan = allocation.build_allocation_plan(persona, profile)
                    self.assertTrue(allocation.validate_allocation_plan(plan, persona))
                    self.assertEqual(plan["format_totals"], spec.format_file_counts(persona, profile))
                    self.assertEqual(plan["scope_totals"], spec.scope_file_counts(persona, profile))
                    self.assertEqual(sum(plan["scope_totals"].values()), plan["total_files"])
                    for row in plan["scope_allocations"]:
                        self.assertGreaterEqual(
                            row["contributor_files"], row["contributor_file_minimum"]
                        )
                        self.assertGreaterEqual(
                            row["contributor_chunk_capacity"],
                            row["contributor_chunk_target"],
                        )
                        self.assertLessEqual(
                            row["contributor_files"], row["contributor_chunk_target"]
                        )
                        self.assertEqual(
                            row["contributor_files"],
                            plan["scope_contributor_file_targets"][row["scope_key"]],
                        )
                        self.assertLess(row["file_count"], spec.MAX_DIRECT_FILES_PER_SCOPE)

    def test_variant_marginals_are_exact_and_plan_is_json_compatible(self):
        persona = spec.get_persona("p04")
        plan = allocation.build_allocation_plan(persona, "full")
        actual = {
            (family, entry["variant"]): 0
            for family, entries in spec.format_variant_counts(persona, "full").items()
            for entry in entries
        }
        for assignment in plan["assignments"]:
            key = (assignment["family"], assignment["variant"])
            actual[key] = actual.get(key, 0) + assignment["count"]
        expected = {
            (family, entry["variant"]): entry["count"]
            for family, entries in spec.format_variant_counts(persona, "full").items()
            for entry in entries
        }
        self.assertEqual(actual, expected)
        json.dumps(plan, ensure_ascii=True, sort_keys=True)

    def test_identical_input_is_byte_stably_deterministic(self):
        first = allocation.build_allocation_plan("p12", "pilot")
        second = allocation.build_allocation_plan("p12", "pilot")
        first_bytes = json.dumps(first, sort_keys=True, separators=(",", ":")).encode()
        second_bytes = json.dumps(second, sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(first_bytes, second_bytes)

    def test_route_hints_match_compounds_and_attract_files(self):
        self.assertEqual(
            allocation.matched_route_hints("pdf_scan", "research/archive-scans"),
            ("scans", "archive"),
        )
        self.assertGreater(
            allocation.route_affinity("code", "repos/product-alpha/docs"),
            allocation.route_affinity("code", "documents/work/product-alpha"),
        )
        plan = allocation.build_allocation_plan("p01", "full")
        code_in_repo_scopes = sum(
            assignment["count"]
            for assignment in plan["assignments"]
            if assignment["family"] == "code"
            and "repos" in assignment["relative_path"].split("/")
        )
        repo_contributor_quota = sum(
            count
            for scope_key, count in plan["scope_contributor_file_targets"].items()
            if next(
                row["relative_path"] for row in plan["scope_allocations"]
                if row["scope_key"] == scope_key
            ).startswith("repos/")
        )
        self.assertEqual(code_in_repo_scopes, repo_contributor_quota)
        self.assertGreater(plan["routing_affinity_total"], 0)

    def test_tiny_profile_never_silently_weakens_an_infeasible_floor(self):
        persona = spec.get_persona("p14")
        contributor_files = spec.contributor_plan(persona, "tiny")["contributor_files"]
        required = sum(spec.scope_contributor_file_minima(persona, "tiny").values())
        if contributor_files < required:
            with self.assertRaisesRegex(
                allocation.AllocationError,
                rf"p14 tiny has {contributor_files} contributor files .* {required}",
            ):
                allocation.build_allocation_plan(persona, "tiny")
        else:
            # This branch keeps the test valid when the tiny profile is raised
            # to a feasible file count in the canonical specification.
            plan = allocation.build_allocation_plan(persona, "tiny")
            self.assertTrue(allocation.validate_allocation_plan(plan, persona))

    def test_bounded_contributor_quota_fails_when_no_solution_exists(self):
        with self.assertRaises(allocation.AllocationError):
            allocation._bounded_proportional_counts(1, (1, 1), (1, 1), (1, 1))

    def test_attestor_rejects_changed_cell(self):
        plan = allocation.build_allocation_plan("p03", "pilot")
        changed = copy.deepcopy(plan)
        changed["assignments"][0]["count"] += 1
        with self.assertRaisesRegex(allocation.AllocationError, "marginals"):
            allocation.validate_allocation_plan(changed)


if __name__ == "__main__":
    unittest.main()
