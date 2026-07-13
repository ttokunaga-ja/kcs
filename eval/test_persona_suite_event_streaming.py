#!/usr/bin/env python3
"""Differential tests for bounded persona event/suite streaming artifacts."""

from __future__ import annotations

import copy
import os
from pathlib import Path
import tempfile
import unittest

from eval import generate_persona_corpus as generator
from eval import persona_event_manifest as persona_events
from eval import persona_fixture_spec as spec
from eval import persona_streaming_storage as stream_storage
from eval import persona_suite_event_manifest as suite_events
from eval import persona_suite_event_streaming as streaming


TINY_SCHEDULE_SHA256 = (
    "3f64675b1b8b83455b6eb18d9a2592b8e8b882621ad3f1b735cd233b6ef437c0"
)
TINY_SUITE_MANIFEST_SHA256 = (
    "d76ca8d55e92ff77eec98aaac69cab2bc3e35f3cd392c4ae681e5a7972afac3a"
)


class TestPersonaSuiteEventStreaming(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        repository_root = Path(__file__).resolve().parent.parent
        cls.temporary = tempfile.TemporaryDirectory(
            prefix=".persona-suite-event-streaming-test-",
            dir=repository_root,
        )
        cls.root = Path(cls.temporary.name)
        cls.wrappers = {}
        cls.event_plans = {}
        cls.manifests = {}
        cls.person_roots = {}
        cls.person_summaries = {}
        ordered_manifests = []
        ordered_plans = []
        for persona in spec.PERSONAS:
            persona_id = persona["id"]
            wrapper = generator.build_persona_generation_plan("tiny", persona_id)
            event_plan = generator.persona_event_plan_projection(
                wrapper,
                expected_profile="tiny",
                expected_persona_id=persona_id,
            )
            manifest = persona_events.build_event_manifest(event_plan, "tiny")
            person_root = cls.root / "persons" / persona_id
            cls.wrappers[persona_id] = wrapper
            cls.event_plans[persona_id] = event_plan
            cls.manifests[persona_id] = manifest
            cls.person_roots[persona_id] = person_root
            cls.person_summaries[persona_id] = (
                streaming.build_persona_event_artifact(
                    person_root,
                    "tiny",
                    persona_id,
                    generation_plan=wrapper,
                    event_manifest=manifest,
                )
            )
            ordered_manifests.append(manifest)
            ordered_plans.append(event_plan)
        cls.legacy = suite_events.build_suite_event_manifest(
            ordered_manifests, ordered_plans, "tiny"
        )
        cls.suite_root = cls.root / "suite"
        cls.summary = streaming.compose_suite_event_artifact(
            cls.suite_root, "tiny", cls.person_roots
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @staticmethod
    def _artifact_rows(root, limits):
        receipt = stream_storage.verify_jsonl_artifact(root, limits=limits)
        return list(stream_storage.iter_jsonl_artifact(
            root,
            limits=limits,
            expected_envelope_sha256=receipt.storage_envelope_sha256,
        ))

    def test_tiny_streaming_is_exact_legacy_differential(self):
        self.assertEqual(self.legacy["totals"]["events"], 1_076)
        self.assertEqual(self.legacy["totals"]["boundaries"], 908)
        self.assertEqual(self.legacy["totals"]["schedule_items"], 1_984)
        self.assertEqual(self.legacy["schedule_sha256"], TINY_SCHEDULE_SHA256)
        self.assertEqual(
            streaming._digest(self.legacy), TINY_SUITE_MANIFEST_SHA256
        )

        stored_schedule = self._artifact_rows(
            self.suite_root / streaming.SUITE_SCHEDULE_DIRECTORY,
            streaming._SUITE_SCHEDULE_LIMITS,
        )
        self.assertEqual(stored_schedule, self.legacy["schedule"])
        self.assertEqual(self.summary.schedule_items, 1_984)
        self.assertEqual(self.summary.schedule_sha256, TINY_SCHEDULE_SHA256)
        self.assertEqual(
            self.summary.suite_event_manifest_sha256,
            TINY_SUITE_MANIFEST_SHA256,
        )

    def test_external_locators_resolve_exact_rows_and_reject_tampering(self):
        locator_rows = self._artifact_rows(
            self.suite_root / streaming.SUITE_LOCATORS_DIRECTORY,
            streaming._SUITE_LOCATOR_LIMITS,
        )
        expected_by_id = {}
        for manifest in self.manifests.values():
            expected_by_id.update(
                (row["event_id"], row) for row in manifest["events"]
            )
            expected_by_id.update(
                (row["boundary_id"], row) for row in manifest["boundaries"]
            )
        samples = [
            next(row for row in locator_rows if row["kind"] == "event"),
            next(row for row in locator_rows if row["kind"] == "boundary"),
        ]
        for row in samples:
            locator = row["target_locator"]
            self.assertNotIn("root", locator)
            self.assertFalse(Path(locator["shard_file"]).is_absolute())
            actual = streaming.pread_scheduled_item(
                self.person_roots[row["persona_id"]], row
            )
            self.assertEqual(actual, expected_by_id[row["item_id"]])

        corrupt = copy.deepcopy(samples[0])
        corrupt["target_locator"]["stored_row_sha256"] = "0" * 64
        with self.assertRaises(streaming.PersonaSuiteEventStreamingError):
            streaming.pread_scheduled_item(
                self.person_roots[samples[0]["persona_id"]], corrupt
            )

        substituted = copy.deepcopy(samples[0])
        other_event = next(
            row for row in locator_rows
            if row["kind"] == "event"
            and row["persona_id"] == samples[0]["persona_id"]
            and row["item_id"] != samples[0]["item_id"]
        )
        substituted["target_locator"] = other_event["target_locator"]
        with self.assertRaises(streaming.PersonaSuiteEventStreamingError):
            streaming.pread_scheduled_item(
                self.person_roots[samples[0]["persona_id"]], substituted
            )

    def test_readback_is_order_independent_and_never_formal(self):
        reversed_roots = dict(reversed(tuple(self.person_roots.items())))
        verified = streaming.verify_suite_event_artifact(
            self.suite_root, "tiny", reversed_roots
        )
        self.assertEqual(verified, self.summary)
        self.assertFalse(verified.formal_publication_attested)
        for summary in self.person_summaries.values():
            self.assertFalse(summary.formal_publication_attested)
            self.assertIsNone(summary.worker_capacity_receipt)

        control, _receipt = streaming._one_control_row(
            self.suite_root / streaming.SUITE_CONTROL_DIRECTORY
        )
        self.assertFalse(control["contracts"]["formal_publication_attested"])
        self.assertEqual(
            control["contracts"]["formal_publication_blocker"],
            streaming.FORMAL_PUBLICATION_BLOCKER,
        )
        self.assertEqual(
            control["contracts"]["formal_publication_blockers"],
            list(stream_storage.FORMAL_PUBLICATION_BLOCKERS),
        )
        self.assertFalse(
            control["contracts"]["contains_all_twenty_full_manifest_objects"]
        )
        self.assertNotIn("schedule", control["logical_manifest_static"])
        self.assertIsNone(control["suite_capacity_receipt"])

    def test_identical_person_publication_is_a_strict_noop(self):
        persona_id = "p01"
        person_root = self.person_roots[persona_id]

        def fingerprints():
            result = {}
            for current_root, directories, files in os.walk(person_root):
                for name in directories + files:
                    path = Path(current_root) / name
                    metadata = path.lstat()
                    result[str(path.relative_to(person_root))] = (
                        metadata.st_dev,
                        metadata.st_ino,
                        metadata.st_size,
                        metadata.st_mtime_ns,
                    )
            return result

        before = fingerprints()
        repeated = streaming.build_persona_event_artifact(
            person_root,
            "tiny",
            persona_id,
            generation_plan=self.wrappers[persona_id],
            event_manifest=self.manifests[persona_id],
        )
        self.assertEqual(fingerprints(), before)
        self.assertEqual(repeated, self.person_summaries[persona_id])


if __name__ == "__main__":
    unittest.main()
