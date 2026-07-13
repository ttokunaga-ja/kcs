#!/usr/bin/env python3
"""Contract tests for the twenty-person synthetic PC specification."""

import copy
import unittest
from unittest import mock

from eval import persona_fixture_spec as spec


class TestPersonaFixtureSpec(unittest.TestCase):
    def test_twenty_independent_people_and_twenty_scopes_each(self):
        self.assertEqual(len(spec.PERSONAS), 20)
        self.assertEqual(len({p["id"] for p in spec.PERSONAS}), 20)
        self.assertEqual(len({p["role"] for p in spec.PERSONAS}), 20)
        for persona in spec.PERSONAS:
            scopes = spec.scope_specs(persona)
            self.assertEqual(len(scopes), 20)
            self.assertEqual(sum(s["kind"] == "primary" for s in scopes), 12)
            self.assertEqual(sum(s["kind"] == "secondary" for s in scopes), 8)
            self.assertEqual(len({s["scope_key"] for s in scopes}), 20)

    def test_persona_format_mixes_are_exact_and_heterogeneous(self):
        matrices = []
        for persona in spec.PERSONAS:
            matrix = tuple(persona["format_percentages"][key] for key in spec.FORMAT_KEYS)
            self.assertEqual(sum(matrix), 100)
            matrices.append(matrix)
            self.assertEqual(
                sum(spec.format_file_counts(persona, "tiny").values()),
                spec.TINY_RAW_FILES_PER_PERSON,
            )
            self.assertEqual(sum(spec.format_file_counts(persona, "pilot").values()), 1_000)
            self.assertEqual(
                sum(spec.format_file_counts(persona, "full").values()),
                persona["full_raw_files"],
            )
            variants = spec.format_variant_counts(persona, "full")
            for family in spec.FORMAT_KEYS:
                self.assertEqual(
                    sum(entry["count"] for entry in variants[family]),
                    spec.format_file_counts(persona, "full")[family],
                )
        self.assertEqual(len(set(matrices)), 20)
        self.assertEqual(min(p["full_raw_files"] for p in spec.PERSONAS), 7_000)
        self.assertEqual(max(p["full_raw_files"] for p in spec.PERSONAS), 16_000)
        txt_roles = {entry[2] for entry in spec.FORMAT_VARIANTS["txt_log"]}
        self.assertEqual(txt_roles, {"contract_contributor", "incidental_searchable"})

    def test_persona_fidelity_rows_are_unique_ordered_and_non_live(self):
        self.assertEqual(spec.FIDELITY_SCHEMA_VERSION, 1)
        self.assertEqual(
            spec.FIDELITY_HYPOTHESIS_STATUS,
            "initial-hypothesis-not-observed-user-statistics",
        )
        self.assertIsNone(spec.validate_persona_fidelity())
        profiles = [persona["fidelity"] for persona in spec.PERSONAS]
        self.assertEqual(len({profile["profile_id"] for profile in profiles}), 20)
        self.assertEqual(len({profile["device_class"] for profile in profiles}), 20)
        self.assertEqual(
            len({profile["size_profile"]["profile_id"] for profile in profiles}),
            20,
        )
        self.assertEqual(
            len({
                profile["domain_binary_raw_only_profile"]["profile_id"]
                for profile in profiles
            }),
            20,
        )
        for persona, profile in zip(spec.PERSONAS, profiles):
            self.assertEqual(set(profile), set(spec.FIDELITY_PROFILE_KEYS))
            self.assertEqual(profile["persona_id"], persona["id"])
            self.assertIn(profile["os_semantics"], spec.OS_SEMANTICS)
            self.assertEqual(profile["os_execution_mode"], spec.OS_EXECUTION_MODE)
            self.assertIsInstance(profile["languages"], tuple)
            self.assertGreater(len(profile["languages"]), 0)
            self.assertEqual(len(profile["languages"]), len(set(profile["languages"])))
            self.assertTrue(all(
                source.endswith(("-snapshot", "-export"))
                for source in profile["synthetic_snapshot_or_export_sources"]
            ))
            self.assertEqual(profile["source_mode"], spec.SYNTHETIC_SOURCE_MODE)
            self.assertIs(profile["live_sync"], False)
            self.assertIs(profile["hypothesis_only"], True)
            self.assertIs(profile["synthetic_only"], True)
            self.assertEqual(profile["searchability_claim"], "none")
            self.assertIs(profile["contains_real_pii"], False)
            self.assertIs(profile["contains_real_phi"], False)
            self.assertIs(profile["contains_real_credentials"], False)
            binary = profile["domain_binary_raw_only_profile"]
            self.assertEqual(binary["status"], "planned-metadata-only")
            self.assertEqual(binary["gate_role"], "raw_only")
            self.assertEqual(binary["expected_contributor_chunks"], 0)
            self.assertIs(binary["implemented_by_renderer"], False)
            self.assertEqual(binary["searchability_claim"], "none")
        self.assertEqual(
            spec.get_persona("p17")["fidelity"]["nesting_model"]["planned_max_depth"],
            6,
        )
        self.assertIn(
            "dicom-like-synthetic-container",
            spec.get_persona("p16")["fidelity"]
            ["domain_binary_raw_only_profile"]["planned_variants"],
        )

    def test_common_size_complexity_bucket_contract_is_exact_and_hypothetical(self):
        self.assertIsNone(spec.validate_size_complexity_buckets())
        expected = {
            "text_code_chunks": (((1, 4), (5, 20), (21, 50), (51, 72)), (55, 30, 12, 3)),
            "pdf_text_pages": (((1, 5), (6, 30), (31, 200), (201, None)), (40, 35, 20, 5)),
            "eml_attachments": (((0, 0), (1, 1), (2, 5), (6, None)), (65, 25, 9, 1)),
            "xlsx_sheets": (((1, 1), (2, 5), (6, 20), (21, None)), (45, 40, 13, 2)),
            "pptx_slides": (((1, 10), (11, 40), (41, 100), (101, None)), (45, 40, 13, 2)),
            "image_media_domain_bytes": (
                (
                    (0, 256 * 1024 - 1),
                    (256 * 1024, 4 * 1024 * 1024 - 1),
                    (4 * 1024 * 1024, 64 * 1024 * 1024 - 1),
                    (64 * 1024 * 1024, 100 * 1024 * 1024),
                ),
                (35, 40, 20, 5),
            ),
        }
        self.assertEqual(tuple(spec.COMMON_SIZE_COMPLEXITY_BUCKETS), tuple(expected))
        for profile_id, (ranges, percentages) in expected.items():
            row = spec.COMMON_SIZE_COMPLEXITY_BUCKETS[profile_id]
            self.assertEqual(
                tuple(
                    (bucket["minimum_inclusive"], bucket["maximum_inclusive"])
                    for bucket in row["buckets"]
                ),
                ranges,
            )
            self.assertEqual(
                tuple(bucket["percentage"] for bucket in row["buckets"]),
                percentages,
            )
            self.assertIs(row["hypothesis_only"], True)
            self.assertIs(row["implemented_by_renderer"], False)
            self.assertEqual(row["searchability_claim"], "none")

    def test_fidelity_validation_rejects_missing_unknown_and_cloned_rows(self):
        missing_row = copy.deepcopy(list(spec.PERSONAS[:-1]))
        with self.assertRaisesRegex(ValueError, "exactly 20"):
            spec.validate_persona_fidelity(missing_row)

        missing_attribute = copy.deepcopy(list(spec.PERSONAS))
        del missing_attribute[0]["fidelity"]["locale"]
        with self.assertRaisesRegex(ValueError, "missing or unknown"):
            spec.validate_persona_fidelity(missing_attribute)

        unknown_attribute = copy.deepcopy(list(spec.PERSONAS))
        unknown_attribute[0]["fidelity"]["observed_population"] = True
        with self.assertRaisesRegex(ValueError, "missing or unknown"):
            spec.validate_persona_fidelity(unknown_attribute)

        cloned = copy.deepcopy(list(spec.PERSONAS))
        cloned[1]["fidelity"] = copy.deepcopy(cloned[0]["fidelity"])
        cloned[1]["fidelity"]["persona_id"] = "p02"
        cloned[1]["fidelity"]["profile_id"] = "p02-fidelity-v1"
        with self.assertRaisesRegex(ValueError, "cloned"):
            spec.validate_persona_fidelity(cloned)

    def test_fidelity_validation_rejects_live_unknown_tier_and_overclaims(self):
        mutations = (
            (lambda profile: profile.__setitem__("live_sync", True), "live sync"),
            (
                lambda profile: profile.__setitem__(
                    "synthetic_snapshot_or_export_sources", ("github-live",)
                ),
                "synthetic snapshots/exports",
            ),
            (
                lambda profile: profile.__setitem__("sensitivity_tiers", ("S4",)),
                "sensitivity tiers",
            ),
            (
                lambda profile: profile.__setitem__("sensitivity_tiers", ("S3", "S2")),
                "sensitivity tiers",
            ),
            (
                lambda profile: profile.__setitem__("contains_real_pii", True),
                "free of real sensitive data",
            ),
            (
                lambda profile: profile.__setitem__(
                    "searchability_claim", "raw-binary-searchable"
                ),
                "non-searchable",
            ),
            (
                lambda profile: profile.__setitem__("os_semantics", "unknown-os"),
                "unknown simulated OS semantics",
            ),
            (
                lambda profile: profile.__setitem__("languages", ("en", "ja")),
                "fidelity hypothesis drifted",
            ),
        )
        for mutate, message in mutations:
            with self.subTest(message=message):
                personas = copy.deepcopy(list(spec.PERSONAS))
                mutate(personas[0]["fidelity"])
                with self.assertRaisesRegex(ValueError, message):
                    spec.validate_persona_fidelity(personas)

    def test_numeric_contracts_reject_bool_and_ratio_drift(self):
        personas = copy.deepcopy(list(spec.PERSONAS))
        personas[0]["fidelity"]["nesting_model"]["planned_max_depth"] = True
        with self.assertRaisesRegex(ValueError, "planned nesting depth"):
            spec.validate_persona_fidelity(personas)

        personas = copy.deepcopy(list(spec.PERSONAS))
        personas[0]["fidelity"]["domain_binary_raw_only_profile"][
            "expected_contributor_chunks"
        ] = False
        with self.assertRaisesRegex(ValueError, "planned raw-only"):
            spec.validate_persona_fidelity(personas)

        buckets = copy.deepcopy(spec.COMMON_SIZE_COMPLEXITY_BUCKETS)
        buckets["text_code_chunks"]["buckets"][0]["percentage"] = True
        with self.assertRaisesRegex(ValueError, "percentage"):
            spec.validate_size_complexity_buckets(buckets)

        buckets = copy.deepcopy(spec.COMMON_SIZE_COMPLEXITY_BUCKETS)
        buckets["pdf_text_pages"]["buckets"][0]["percentage"] = 39
        buckets["pdf_text_pages"]["buckets"][1]["percentage"] = 36
        with self.assertRaisesRegex(ValueError, "percentages drifted"):
            spec.validate_size_complexity_buckets(buckets)

        personas = copy.deepcopy(list(spec.PERSONAS))
        personas[0]["format_percentages"]["ipynb"] = True
        with mock.patch.object(spec, "PERSONAS", tuple(personas)):
            with self.assertRaisesRegex(ValueError, "invalid format percentage"):
                spec.validate_spec()

        with self.assertRaises(ValueError):
            spec.largest_remainder(True, (1, 1))
        with self.assertRaises(ValueError):
            spec.largest_remainder(1, (True, 1))

    def test_nesting_and_portability_cover_complex_pc_shapes(self):
        depths = []
        personas_with_depth_five = set()
        all_primary_matrices = set()
        for persona in spec.PERSONAS:
            primary = tuple(persona["primary_paths"])
            all_primary_matrices.add(primary)
            for relative in spec.all_scope_paths(persona):
                components = spec.validate_relative_scope(relative)
                depths.append(len(components))
                if len(components) >= 5:
                    personas_with_depth_five.add(persona["id"])
        self.assertEqual(len(all_primary_matrices), 20)
        self.assertIn(2, depths)
        self.assertGreaterEqual(
            sum(depth >= 4 for depth in depths), spec.MIN_SCOPES_AT_DEPTH_FOUR
        )
        self.assertGreaterEqual(
            len(personas_with_depth_five), spec.MIN_PERSONAS_WITH_DEPTH_FIVE
        )
        self.assertGreaterEqual(max(depths), spec.MIN_MAXIMUM_SCOPE_DEPTH)

    def test_full_profile_has_120k_plan_and_scope_headroom(self):
        for persona in spec.PERSONAS:
            plan = spec.contributor_plan(persona, "full")
            self.assertEqual(plan["target_chunks"], 120_000)
            self.assertGreater(plan["contributor_files"], 0)
            self.assertLessEqual(
                plan["persona_average_chunks_per_file_ceiling"],
                spec.MAX_CONTRIBUTOR_CHUNKS_PER_FILE,
            )
            scope_counts = spec.scope_file_counts(persona, "full")
            self.assertEqual(sum(scope_counts.values()), persona["full_raw_files"])
            self.assertLess(max(scope_counts.values()), spec.MAX_DIRECT_FILES_PER_SCOPE)
            self.assertEqual(
                spec.contributor_plan(persona, "pilot")["target_chunks"],
                12_000,
            )
            chunk_targets = spec.scope_contributor_chunk_targets(persona, "full")
            scopes = spec.scope_specs(persona)
            primary_keys = {s["scope_key"] for s in scopes if s["kind"] == "primary"}
            self.assertEqual(sum(chunk_targets.values()), 120_000)
            self.assertEqual(sum(chunk_targets[key] for key in primary_keys), 90_000)
            self.assertEqual(
                sum(value for key, value in chunk_targets.items() if key not in primary_keys),
                30_000,
            )
            minima = spec.scope_contributor_file_minima(persona, "full")
            self.assertLessEqual(sum(minima.values()), plan["contributor_files"])
            self.assertTrue(all(minima[key] <= scope_counts[key] for key in scope_counts))
        self.assertEqual(spec.FORMAL_HISTORY_CHUNKS_PER_PERSON, 180_000)
        self.assertEqual(
            spec.FORMAL_CURRENT_CHUNKS_PER_PERSON * len(spec.PERSONAS),
            2_400_000,
        )
        self.assertEqual(
            spec.FORMAL_CURRENT_CHUNKS_PER_PERSON * len(spec.PERSONAS) * spec.REPLAY_COUNT,
            7_200_000,
        )

    def test_tiny_profile_can_place_a_contributor_in_every_scope(self):
        for persona in spec.PERSONAS:
            contributor_files = spec.contributor_plan(persona, "tiny")[
                "contributor_files"
            ]
            required = sum(
                spec.scope_contributor_file_minima(persona, "tiny").values()
            )
            self.assertGreaterEqual(
                contributor_files,
                required,
                msg=persona["id"],
            )

    def test_scope_weights_and_history_contract(self):
        self.assertEqual(sum(spec.PRIMARY_SCOPE_WEIGHTS_PCT), 75)
        self.assertEqual(sum(spec.SECONDARY_SCOPE_WEIGHTS_PCT), 25)
        self.assertEqual(tuple(spec.HISTORY_COHORT_FULL_PCT), spec.HISTORY_COHORT_KEYS)
        self.assertEqual(sum(spec.HISTORY_COHORT_FULL_PCT.values()), 100)
        self.assertTrue(spec.HISTORY_COHORT_ASSIGNMENT_EXECUTABLE)
        self.assertIsNone(spec.require_executable_history_cohort_assignment())
        self.assertTrue(spec.HISTORY_STRUCTURAL_ASSIGNMENT_EXECUTABLE)
        self.assertIsNone(
            spec.require_executable_history_structural_assignment()
        )
        self.assertTrue(spec.HISTORY_EVENT_MANIFEST_EXECUTABLE)
        self.assertIsNone(spec.require_executable_history_event_manifest())
        self.assertFalse(spec.HISTORY_ASSIGNMENT_EXECUTABLE)
        with self.assertRaisesRegex(ValueError, "W0 history preparation"):
            spec.require_executable_history_assignment()
        self.assertEqual(tuple(wave["id"] for wave in spec.WAVES), tuple(f"W{i}" for i in range(6)))
        operations = {operation for wave in spec.WAVES for operation in wave["operations"]}
        for expected in ("create", "edit", "rename", "move", "duplicate", "archive", "delete", "restore", "purge"):
            self.assertIn(expected, operations)
        self.assertEqual(
            spec.EVENT_BOUNDARIES,
            ("index_auto", "purged_commit", "index_noop", "none"),
        )
        for persona in spec.PERSONAS:
            cohorts = spec.history_cohort_chunk_targets(persona, "full")
            self.assertEqual(cohorts, {
                "P": 4_800,
                "X": 12_000,
                "Y": 7_200,
                "N": 4_800,
                "U": 91_200,
            })
            targets = spec.history_wave_chunk_targets(persona, "full")
            self.assertEqual(targets["W0"]["current_contract_contributor_chunks"], 120_000)
            self.assertEqual(targets["W0"]["history_only_contract_contributor_chunks"], 0)
            self.assertEqual(targets["W5"]["current_contract_contributor_chunks"], 120_000)
            self.assertEqual(targets["W5"]["history_only_contract_contributor_chunks"], 60_000)
            self.assertEqual(
                targets["W5"]["current_plus_history_contract_contributor_chunks"],
                180_000,
            )
            events = spec.history_event_plan(persona, "full")
            self.assertEqual(events["W4"]["replacement_current_contract_chunks"], 12_000)
            self.assertEqual(events["W5"]["correction_history_contract_chunks"], 4_800)
            self.assertEqual(events["W5"]["purged_current_contract_chunks"], 4_800)
            self.assertEqual(events["W5"]["purged_history_contract_chunks"], 4_800)
            self.assertEqual(events["W5"]["purged_total_contract_version_chunks"], 9_600)
            self.assertEqual(events["W5"]["replacement_current_contract_chunks"], 4_800)
            self.assertEqual(events["W5"]["pre_purge_current_contract_chunks"], 124_800)
            self.assertEqual(events["W5"]["pre_purge_history_contract_chunks"], 64_800)
            self.assertEqual(events["W5"]["index_auto_boundaries"], 20)
            self.assertEqual(events["W5"]["index_noop_boundaries"], 20)
            self.assertTrue(events["W5"]["purged_commit_boundaries_from_source_allocator"])

    def test_tiny_history_rounding_uses_joint_residual(self):
        for persona in spec.PERSONAS:
            current = spec.contributor_plan(persona, "tiny")["target_chunks"]
            cohorts = spec.history_cohort_chunk_targets(persona, "tiny")
            self.assertEqual(cohorts["P"], current * 4 // 100)
            self.assertEqual(cohorts["X"], current * 10 // 100)
            self.assertEqual(cohorts["N"], cohorts["P"])
            self.assertEqual(
                cohorts["P"] + cohorts["X"] + cohorts["Y"],
                current * 20 // 100,
            )
            self.assertEqual(sum(cohorts.values()), current)
            events = spec.history_event_plan(persona, "tiny")
            self.assertIsNone(events["W1"]["index_auto_boundaries"])
            self.assertIsNone(events["W5"]["index_noop_boundaries"])

    def test_full_mixed_format_offline_index_oracle_is_explicit(self):
        totals = spec.suite_expected_offline_index_counts("full")
        self.assertEqual(totals["physical_files"], 195_000)
        self.assertEqual(totals["normalized_files"], 124_030)
        self.assertEqual(totals["pending_online_tasks"], 89_360)
        self.assertEqual(totals["skipped_unrecognized_binary_files"], 8_950)
        self.assertEqual(totals["failed_files"], 0)
        self.assertEqual(totals["completed_online_tasks"], 0)
        self.assertEqual(totals["external_cost_microusd"], 0)
        # Text-layer PDFs are deliberately present in both local-normalized and
        # optional enhancement-pending counters; these are not a partition.
        pdf_text = sum(
            spec.format_file_counts(persona, "full")["pdf_text"]
            for persona in spec.PERSONAS
        )
        self.assertEqual(
            totals["normalized_files"]
            + totals["pending_online_tasks"]
            + totals["skipped_unrecognized_binary_files"]
            - pdf_text,
            totals["physical_files"],
        )

    def test_largest_remainder_is_stable(self):
        self.assertEqual(spec.largest_remainder(7, (1, 1, 1)), (3, 2, 2))
        self.assertEqual(spec.largest_remainder(100, (10, 9, 8)), (37, 33, 30))

    def test_nonportable_paths_fail_closed(self):
        for value in ("con/docs", "safe/../escape", "/absolute/path", "one", "bad?/leaf", "Upper/leaf"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    spec.validate_relative_scope(value)

    def test_managed_source_basenames_are_portable_and_not_sensitive(self):
        self.assertEqual(
            spec.validate_source_basename("p01-pdf-text-00001.pdf"),
            "p01-pdf-text-00001.pdf",
        )
        for value in (
            "../escape.md",
            "UPPER.md",
            "con.txt",
            "account-token.txt",
            "private.pem",
            "bad:name.txt",
            "source.",
            "source..",
            "x" * 121,
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                spec.validate_source_basename(value)


if __name__ == "__main__":
    unittest.main()
