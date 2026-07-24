#!/usr/bin/env python3
"""Tests for the full persona streaming count/capacity oracle."""

import copy
import hashlib
import json
import unittest
from unittest import mock

from eval import persona_event_manifest
from eval import persona_full_scale_limits as limits


def _digest(label):
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _shards(persona_row):
    result = []
    rows_by_kind = {
        "events": persona_row["counts"]["events"],
        "boundaries": persona_row["counts"]["boundaries"],
        "schedule": persona_row["counts"]["schedule_items"],
    }
    for kind in ("events", "boundaries", "schedule"):
        remaining = rows_by_kind[kind]
        ordinal = 0
        while remaining:
            ordinal += 1
            rows = min(remaining, limits.MAX_JSONL_SHARD_ROWS)
            remaining -= rows
            result.append({
                "kind": kind,
                "ordinal": ordinal,
                "sha256": _digest(
                    f"{persona_row['persona_id']}:{kind}:{ordinal}"
                ),
                "bytes": rows * 97,
                "rows": rows,
                "declared_max_row_bytes": 97,
                "close_reason": "final" if remaining == 0 else "row_limit",
            })
    return result


def _worker(persona_row, oracle, *, peak_rss_bytes=16 * limits.MIB):
    return limits.build_worker_capacity_receipt(
        persona_id=persona_row["persona_id"],
        event_manifest_sha256=_digest(
            f"manifest:{persona_row['persona_id']}"
        ),
        event_projection_sha256=_digest(
            f"projection:{persona_row['persona_id']}"
        ),
        shards=_shards(persona_row),
        max_json_depth=12,
        max_initial_materialization_row_bytes=4_096,
        peak_rss_bytes=peak_rss_bytes,
        child_exit_code=0,
        child_terminating_signal=0,
        oracle=oracle,
    )


def _suite(workers, oracle):
    suite_files = {
        "suite_event_manifest_bytes": 2 * limits.MIB,
        "suite_schedule_bytes": 4 * limits.MIB,
        "schedule_locator_bytes": 4 * limits.MIB,
        "schedule_mmr_bytes": limits.MIB,
    }
    worker_bytes = sum(
        value["outputs"]["logical_event_bytes"] for value in workers
    )
    artifact_bytes = worker_bytes + sum(suite_files.values()) + limits.MIB
    return limits.build_suite_capacity_receipt(
        replay_ordinal=1,
        worker_receipts=list(reversed(workers)),
        suite_event_manifest_sha256=_digest("suite-manifest"),
        suite_schedule_sha256=_digest("suite-schedule"),
        schedule_locator_root_sha256=_digest("locator-root"),
        schedule_mmr_root_sha256=_digest("mmr-root"),
        schedule_mmr_leaf_count=48_771,
        **suite_files,
        max_suite_schedule_row_bytes=512,
        max_locator_row_bytes=512,
        artifact_bytes=artifact_bytes,
        workspace_bytes=artifact_bytes + limits.MIB,
        composer_peak_rss_bytes=32 * limits.MIB,
        oracle=oracle,
    )


class TestPersonaFullScaleLimits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # A hard tripwire: the oracle may build canonical source/history plans,
        # but must not materialize even one full event manifest.
        with mock.patch.object(
            persona_event_manifest,
            "build_event_manifest",
            side_effect=AssertionError("full event manifest was built"),
        ) as event_builder:
            cls.oracle = limits.build_full_scale_limits()
        event_builder.assert_not_called()
        cls.persona_by_id = {
            row["persona_id"]: row for row in cls.oracle["personas"]
        }

    def test_exact_frozen_counts_formulas_and_three_replays(self):
        oracle = self.oracle
        self.assertEqual(len(oracle["personas"]), 20)
        self.assertEqual(oracle["per_replay"]["cohort_sources"], {
            "P": 2_775, "X": 6_931, "Y": 4_162, "N": 2_777,
        })
        self.assertEqual(oracle["per_replay"]["events"], 43_596)
        self.assertEqual(oracle["per_replay"]["boundaries"], 5_175)
        self.assertEqual(oracle["per_replay"]["schedule_items"], 48_771)
        self.assertEqual(oracle["per_replay"]["logical_rows"], 97_542)
        self.assertEqual(oracle["all_replays"], {
            "replays": 3,
            "events": 130_788,
            "boundaries": 15_525,
            "schedule_items": 146_313,
            "logical_rows": 292_626,
        })

        for person in oracle["personas"]:
            with self.subTest(persona=person["persona_id"]):
                cohorts = person["cohort_source_counts"]
                counts = person["counts"]
                self.assertEqual(
                    counts["events"],
                    3 * cohorts["P"] + 3 * cohorts["X"]
                    + 2 * cohorts["Y"] + 2 * cohorts["N"] + 30,
                )
                self.assertEqual(counts["boundaries"], cohorts["P"] + 120)
                self.assertEqual(
                    counts["schedule_items"],
                    counts["events"] + counts["boundaries"],
                )
                self.assertEqual(len(person["phase_ranges"]), 12)
                prior_end = 0
                for phase in person["phase_ranges"]:
                    self.assertEqual(phase["start_ordinal"], prior_end + 1)
                    self.assertEqual(
                        phase["end_ordinal"] - phase["start_ordinal"] + 1,
                        phase["rows"],
                    )
                    prior_end = phase["end_ordinal"]
                self.assertEqual(prior_end, counts["schedule_items"])
                self.assertLessEqual(
                    person["persona_generation_plan_file_bytes"], 8 * limits.MIB
                )
                self.assertEqual(person["current_contract_chunks"], 120_000)
                self.assertEqual(
                    person["final_history_only_contract_chunks"], 60_000
                )

    def test_phase_ranges_are_allocation_derived_and_wave_drift_fails(self):
        person = self.persona_by_id["p01"]
        generation_plan = limits.generator.build_persona_generation_plan(
            "full", "p01"
        )
        event_plan = limits.generator.persona_event_plan_projection(
            generation_plan,
            expected_profile="full",
            expected_persona_id="p01",
        )
        history_plan = limits.history.build_history_allocation(
            event_plan, "full"
        )
        structural_plan = limits.structural.build_structural_allocation(
            event_plan, "full"
        )
        phases = limits._phase_ranges(history_plan, structural_plan)
        self.assertEqual(phases, person["phase_ranges"])
        self.assertEqual([value["rows"] for value in phases], [
            1_507, 20, 21, 20, 1_507, 20,
            754, 20, 603, 20, 602, 20,
        ])

        canonical_builder = limits.structural.build_structural_allocation

        def corrupt_per_wave_counts(plan, profile):
            value = copy.deepcopy(canonical_builder(plan, profile))
            value["event_counts_by_wave"]["W1"] += 1
            value["event_counts_by_wave"]["W3"] -= 1
            return value

        with mock.patch.object(
            limits.structural,
            "build_structural_allocation",
            side_effect=corrupt_per_wave_counts,
        ), self.assertRaises(limits.FullScaleLimitsError):
            limits._build_full_scale_limits_uncached()

    def test_caps_and_non_evidence_contract_are_exact(self):
        self.assertEqual(self.oracle["limits"], {
            "persona_plan_bytes": 8 * limits.MIB,
            "sources_per_persona": 16_000,
            "scopes_per_persona": 20,
            "managed_initial_materializations_per_persona": 2_500,
            "logical_event_bytes_per_persona": 64 * limits.MIB,
            "event_rows_per_persona": 6_000,
            "boundary_rows_per_persona": 600,
            "schedule_rows_per_persona": 6_600,
            "canonical_json_depth": 16,
            "event_row_bytes": 64 * 1024,
            "boundary_row_bytes": 64 * 1024,
            "initial_materialization_row_bytes": 64 * 1024,
            "schedule_row_bytes": 4 * 1024,
            "locator_row_bytes": 4 * 1024,
            "jsonl_shard_rows": 512,
            "jsonl_shard_bytes": 32 * limits.MIB,
            "suite_event_rows": 45_000,
            "suite_boundary_rows": 5_500,
            "suite_schedule_rows": 50_000,
            "suite_logical_file_bytes": 64 * limits.MIB,
            "artifact_bytes": 2 * limits.GIB,
            "workspace_bytes": 4 * limits.GIB,
            "worker_peak_rss_bytes": 384 * limits.MIB,
            "composer_peak_rss_bytes": 128 * limits.MIB,
            "process_tree_peak_rss_bytes": 512 * limits.MIB,
            "concurrent_persona_workers": 1,
        })
        self.assertEqual(self.oracle["contracts"], {
            "planned_counts_only": True,
            "builds_full_event_manifests": False,
            "phase_counts_derived_from_canonical_allocations": True,
            "actual_kio_evidence": False,
            "authorizes_physical_write": False,
        })
        self.assertTrue(limits.validate_full_scale_limits(self.oracle))
        self.assertEqual(
            json.loads(json.dumps(self.oracle, sort_keys=True)), self.oracle
        )
        self.assertEqual(len(limits.full_scale_limits_sha256(self.oracle)), 64)

    def test_oracle_rejects_unknown_bool_arithmetic_and_non_json_values(self):
        mutations = []
        extra = copy.deepcopy(self.oracle)
        extra["unexpected"] = 1
        mutations.append(extra)
        boolean = copy.deepcopy(self.oracle)
        boolean["schema_version"] = True
        mutations.append(boolean)
        arithmetic = copy.deepcopy(self.oracle)
        arithmetic["per_replay"]["events"] += 1
        mutations.append(arithmetic)
        cap = copy.deepcopy(self.oracle)
        cap["limits"]["worker_peak_rss_bytes"] += 1
        mutations.append(cap)
        non_json = copy.deepcopy(self.oracle)
        non_json["personas"] = tuple(non_json["personas"])
        mutations.append(non_json)
        for value in mutations:
            with self.subTest(case=mutations.index(value)), self.assertRaises(
                limits.FullScaleLimitsError
            ):
                limits.validate_full_scale_limits(value)

    def test_worker_receipt_binds_exact_rows_shards_plans_and_caps(self):
        person = self.persona_by_id["p02"]
        receipt = _worker(person, self.oracle)
        self.assertTrue(limits.validate_worker_capacity_receipt(
            receipt, oracle=self.oracle
        ))
        self.assertEqual(receipt["outputs"]["counts"], {
            "events": 5_087,
            "boundaries": 446,
            "schedule": 5_533,
        })
        self.assertEqual(
            receipt["outputs"]["shard_index_sha256"],
            limits._digest(receipt["outputs"]["shards"]),
        )
        self.assertEqual(receipt["contracts"], {
            "declared_projection_only": True,
            "artifact_readback_required": True,
            "supervisor_wait4_required": True,
            "formal_capacity_gate_satisfied": False,
            "planned_counts_only": True,
            "actual_kio_evidence": False,
            "authorizes_physical_write": False,
        })
        self.assertNotIn("canonical_validator_completed", receipt["contracts"])
        self.assertNotIn("all_limits_satisfied", receipt["contracts"])
        self.assertLessEqual(
            receipt["outputs"]["plan_cardinalities"][
                "managed_initial_materializations"
            ],
            limits.MAX_MANAGED_INITIAL_MATERIALIZATIONS_PER_PERSONA,
        )
        self.assertEqual(
            json.loads(json.dumps(receipt, sort_keys=True)), receipt
        )

    def test_worker_rejects_tampering_coercion_unknown_fields_and_overflow(self):
        person = self.persona_by_id["p01"]
        receipt = _worker(person, self.oracle)
        mutations = []

        extra = copy.deepcopy(receipt)
        extra["outputs"]["unexpected"] = 1
        mutations.append(extra)
        boolean = copy.deepcopy(receipt)
        boolean["outputs"]["shards"][0]["rows"] = True
        mutations.append(boolean)
        arithmetic = copy.deepcopy(receipt)
        arithmetic["outputs"]["shards"][0]["rows"] -= 1
        mutations.append(arithmetic)
        cap = copy.deepcopy(receipt)
        cap["outputs"]["shards"][0]["bytes"] = (
            limits.MAX_JSONL_SHARD_BYTES + 1
        )
        mutations.append(cap)
        total_cap = copy.deepcopy(receipt)
        for shard in total_cap["outputs"]["shards"][:3]:
            shard["bytes"] = limits.MAX_JSONL_SHARD_BYTES
            shard["declared_max_row_bytes"] = limits.MAX_EVENT_ROW_BYTES
        total_cap["outputs"]["shard_index_sha256"] = limits._digest(
            total_cap["outputs"]["shards"]
        )
        total_cap["outputs"]["logical_event_bytes"] = sum(
            shard["bytes"] for shard in total_cap["outputs"]["shards"]
        )
        mutations.append(total_cap)
        depth = copy.deepcopy(receipt)
        depth["outputs"]["max_json_depth"] = 17
        mutations.append(depth)
        row_cap = copy.deepcopy(receipt)
        row_cap["outputs"]["shards"][0]["declared_max_row_bytes"] = (
            limits.MAX_EVENT_ROW_BYTES + 1
        )
        mutations.append(row_cap)
        nonfinal = copy.deepcopy(receipt)
        nonfinal["outputs"]["shards"][0]["close_reason"] = "final"
        mutations.append(nonfinal)
        initial_row = copy.deepcopy(receipt)
        initial_row["outputs"][
            "declared_max_initial_materialization_row_bytes"
        ] = limits.MAX_INITIAL_MATERIALIZATION_ROW_BYTES + 1
        mutations.append(initial_row)
        phase_bool = copy.deepcopy(receipt)
        phase_bool["outputs"]["phase_ranges"][0]["start_ordinal"] = True
        mutations.append(phase_bool)
        plan = copy.deepcopy(receipt)
        plan["inputs"]["persona_event_plan_sha256"] = "0" * 64
        mutations.append(plan)
        rss = copy.deepcopy(receipt)
        rss["process"]["declared_peak_rss_bytes"] = (
            limits.MAX_WORKER_RSS_BYTES + 1
        )
        mutations.append(rss)
        exit_failure = copy.deepcopy(receipt)
        exit_failure["process"]["declared_child_exit_code"] = 1
        mutations.append(exit_failure)
        limit_bool = copy.deepcopy(receipt)
        limit_bool["limits"]["concurrent_persona_workers"] = True
        mutations.append(limit_bool)
        contract_int = copy.deepcopy(receipt)
        contract_int["contracts"]["planned_counts_only"] = 1
        mutations.append(contract_int)
        non_json = copy.deepcopy(receipt)
        non_json["outputs"]["shards"] = tuple(
            non_json["outputs"]["shards"]
        )
        mutations.append(non_json)

        for value in mutations:
            with self.subTest(case=mutations.index(value)), self.assertRaises(
                limits.FullScaleLimitsError
            ):
                limits.validate_worker_capacity_receipt(
                    value, oracle=self.oracle
                )

    def test_suite_receipt_binds_twenty_workers_and_conservative_tree(self):
        workers = [
            _worker(
                person,
                self.oracle,
                peak_rss_bytes=(16 * limits.MIB + ordinal),
            )
            for ordinal, person in enumerate(self.oracle["personas"], start=1)
        ]
        receipt = _suite(workers, self.oracle)
        self.assertTrue(limits.validate_suite_capacity_receipt(
            receipt, worker_receipts=workers, oracle=self.oracle
        ))
        self.assertEqual(
            [row["persona_id"] for row in receipt["inputs"]["worker_receipts"]],
            [f"p{ordinal:02d}" for ordinal in range(1, 21)],
        )
        process = receipt["process"]
        self.assertEqual(
            process["declared_conservative_process_tree_peak_rss_bytes"],
            process["declared_composer_peak_rss_bytes"]
            + process["declared_max_worker_peak_rss_bytes"],
        )
        self.assertEqual(receipt["outputs"]["counts"], {
            "events": 43_596,
            "boundaries": 5_175,
            "schedule_items": 48_771,
        })
        self.assertEqual(receipt["contracts"], {
            "declared_projection_only": True,
            "artifact_readback_required": True,
            "supervisor_wait4_required": True,
            "single_worker_no_grandchildren_required": True,
            "formal_capacity_gate_satisfied": False,
            "planned_counts_only": True,
            "actual_kio_evidence": False,
            "authorizes_physical_write": False,
        })
        self.assertNotIn("single_worker_no_grandchildren", receipt["contracts"])
        self.assertNotIn("all_limits_satisfied", receipt["contracts"])

        cases = []
        reordered = copy.deepcopy(receipt)
        reordered["inputs"]["worker_receipts"].reverse()
        cases.append(reordered)
        bool_leaf_count = copy.deepcopy(receipt)
        bool_leaf_count["outputs"]["schedule_mmr_leaf_count"] = True
        cases.append(bool_leaf_count)
        count = copy.deepcopy(receipt)
        count["outputs"]["counts"]["events"] += 1
        cases.append(count)
        tree = copy.deepcopy(receipt)
        tree["process"][
            "declared_conservative_process_tree_peak_rss_bytes"
        ] += 1
        cases.append(tree)
        locator_row = copy.deepcopy(receipt)
        locator_row["outputs"]["declared_max_locator_row_bytes"] = (
            limits.MAX_LOCATOR_ROW_BYTES + 1
        )
        cases.append(locator_row)
        suite_file = copy.deepcopy(receipt)
        suite_file["outputs"]["suite_logical_file_bytes"]["schedule"] = (
            limits.MAX_SUITE_LOGICAL_FILE_BYTES + 1
        )
        cases.append(suite_file)
        artifact = copy.deepcopy(receipt)
        artifact["outputs"]["declared_artifact_bytes"] = (
            artifact["outputs"]["minimum_artifact_bytes"] - 1
        )
        cases.append(artifact)
        workspace = copy.deepcopy(receipt)
        workspace["outputs"]["declared_workspace_bytes"] = (
            limits.MAX_WORKSPACE_BYTES + 1
        )
        cases.append(workspace)
        extra = copy.deepcopy(receipt)
        extra["contracts"]["observed_kio"] = True
        cases.append(extra)
        for value in cases:
            with self.subTest(case=cases.index(value)), self.assertRaises(
                limits.FullScaleLimitsError
            ):
                limits.validate_suite_capacity_receipt(
                    value, worker_receipts=workers, oracle=self.oracle
                )


if __name__ == "__main__":
    unittest.main()
