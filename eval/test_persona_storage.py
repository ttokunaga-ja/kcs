#!/usr/bin/env python3
"""Focused standard-library tests for persona generator storage safety."""

import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import persona_storage as storage  # noqa: E402


PLAN_SHA = "1" * 64
MANIFEST_SHA = "2" * 64


class StorageTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="kio-persona-storage-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.home = self.base / "users" / "test-user"
        self.repo = self.home / "dev" / "kio"
        self.home.mkdir(parents=True)
        self.repo.mkdir(parents=True)
        self.output = self.home / "persona-runs" / "replay-01"

    def preflight(self, path, **kwargs):
        return storage.preflight_destination(
            path, home=self.home, repo_root=self.repo, **kwargs
        )

    def publish(self, path=None, populate=None, validate=None, **kwargs):
        def default_populate(staging):
            storage.atomic_write_file(staging / "payload.txt", b"complete W0\n")

        def default_validate(staging):
            self.assertEqual((staging / "payload.txt").read_bytes(), b"complete W0\n")
            self.assertFalse((self.output).exists())

        return storage.atomic_publish_owned_root(
            self.output if path is None else path,
            profile="tiny",
            replay_id="replay-01",
            plan_sha256=PLAN_SHA,
            manifest_sha256=MANIFEST_SHA,
            populate=default_populate if populate is None else populate,
            validate=default_validate if validate is None else validate,
            home=self.home,
            repo_root=self.repo,
            **kwargs,
        )


class TestOwnerMarker(StorageTestCase):
    def test_marker_carries_identity_profile_replay_state_and_bindings(self):
        building = storage.make_owner_marker(
            profile="tiny",
            replay_id="replay-01",
            state="building",
            plan_sha256=PLAN_SHA,
        )
        self.assertEqual(
            set(building),
            {
                "schema_version",
                "owner",
                "fixture_id",
                "profile",
                "replay_id",
                "state",
                "plan_sha256",
            },
        )
        self.assertEqual(building["fixture_id"], "kio-persona-pc-v1")
        self.assertEqual(building["state"], "building")

        ready = storage.make_owner_marker(
            profile="full",
            replay_id="replay-03",
            state="ready",
            plan_sha256=PLAN_SHA,
            manifest_sha256=MANIFEST_SHA,
        )
        self.assertEqual(ready["manifest_sha256"], MANIFEST_SHA)
        self.assertEqual(storage.validate_owner_marker(ready), ready)

    def test_marker_validation_rejects_unknown_values_and_noncanonical_fields(self):
        cases = (
            {"profile": "unknown", "replay_id": "replay-01", "state": "building"},
            {"profile": "tiny", "replay_id": "replay-04", "state": "building"},
            {"profile": "tiny", "replay_id": "replay-01", "state": "complete"},
        )
        for values in cases:
            with self.subTest(values=values), self.assertRaises(storage.PersonaStorageError):
                storage.make_owner_marker(plan_sha256=PLAN_SHA, **values)
        with self.assertRaisesRegex(storage.PersonaStorageError, "requires manifest"):
            storage.make_owner_marker(
                profile="tiny",
                replay_id="replay-01",
                state="ready",
                plan_sha256=PLAN_SHA,
            )
        invalid = storage.make_owner_marker(
            profile="tiny", replay_id="replay-01", state="building",
            plan_sha256=PLAN_SHA,
        )
        invalid["surprise"] = True
        with self.assertRaisesRegex(storage.PersonaStorageError, "field set"):
            storage.validate_owner_marker(invalid)
        for invalid_profile in ([], 3):
            invalid = storage.make_owner_marker(
                profile="tiny", replay_id="replay-01", state="building",
                plan_sha256=PLAN_SHA,
            )
            invalid["profile"] = invalid_profile
            with self.subTest(invalid_profile=invalid_profile), self.assertRaises(
                storage.PersonaStorageError
            ):
                storage.validate_owner_marker(invalid)
        invalid = storage.make_owner_marker(
            profile="tiny", replay_id="replay-01", state="building",
            plan_sha256=PLAN_SHA,
        )
        invalid["schema_version"] = True
        with self.assertRaisesRegex(storage.PersonaStorageError, "schema"):
            storage.validate_owner_marker(invalid)

    def test_invalid_and_duplicate_key_markers_are_rejected_without_writes(self):
        self.output.mkdir(parents=True)
        marker = self.output / storage.OWNER_MARKER_NAME
        marker.write_text(
            '{"schema_version":1,"schema_version":1}\n', encoding="utf-8"
        )
        before = marker.read_bytes()
        with self.assertRaises(storage.PersonaStorageError):
            self.preflight(self.output)
        self.assertEqual(marker.read_bytes(), before)
        self.assertEqual(list(self.output.iterdir()), [marker])


class TestDestinationSafety(StorageTestCase):
    def test_refuses_root_home_repository_their_ancestors_and_repo_descendants(self):
        unsafe = (
            Path(self.base.anchor),
            self.home,
            self.home.parent,
            self.repo,
            self.repo.parent,
            self.repo / "generated",
        )
        for path in unsafe:
            with self.subTest(path=path), self.assertRaises(storage.PersonaStorageError):
                self.preflight(path)

        allowed = self.preflight(self.output)
        self.assertEqual(allowed.disposition, "missing")

    def test_refuses_symlink_reparse_regular_and_special_path_components(self):
        real = self.home / "real-output-parent"
        real.mkdir()
        alias = self.home / "output-alias"
        try:
            alias.symlink_to(real, target_is_directory=True)
        except OSError as exc:  # pragma: no cover - platform policy
            self.skipTest(f"directory symlink unavailable: {exc}")
        with self.assertRaisesRegex(storage.PersonaStorageError, "plain directory"):
            self.preflight(alias / "child")

        regular = self.home / "regular-target"
        regular.write_text("not a directory", encoding="utf-8")
        with self.assertRaisesRegex(storage.PersonaStorageError, "plain directory"):
            self.preflight(regular)

        if hasattr(os, "mkfifo"):
            fifo = self.home / "fifo-target"
            os.mkfifo(fifo)
            with self.assertRaisesRegex(storage.PersonaStorageError, "plain directory"):
                self.preflight(fifo)

        metadata = SimpleNamespace(
            st_mode=stat.S_IFDIR,
            st_file_attributes=storage.WINDOWS_REPARSE_POINT_ATTRIBUTE,
            st_reparse_tag=0xA000000C,
        )
        self.assertFalse(storage._is_plain_directory(metadata))

    def test_symlink_owner_marker_is_rejected_and_target_is_untouched(self):
        self.output.mkdir(parents=True)
        outside = self.home / "outside-marker.json"
        outside.write_text("user bytes", encoding="utf-8")
        marker = self.output / storage.OWNER_MARKER_NAME
        marker.symlink_to(outside)
        with self.assertRaisesRegex(storage.PersonaStorageError, "plain regular"):
            self.preflight(self.output)
        self.assertTrue(marker.is_symlink())
        self.assertEqual(outside.read_text(encoding="utf-8"), "user bytes")

    def test_direct_owner_load_rejects_a_symlink_root(self):
        self.output.parent.mkdir(parents=True)
        self.publish()
        alias = self.home / "owned-alias"
        try:
            alias.symlink_to(self.output, target_is_directory=True)
        except OSError as exc:  # pragma: no cover - Windows policy
            self.skipTest(f"directory symlink unavailable: {exc}")
        with self.assertRaisesRegex(storage.PersonaStorageError, "plain directory"):
            storage.load_owner_marker(alias)

    def test_nonempty_unowned_root_is_rejected_without_modification(self):
        self.output.mkdir(parents=True)
        sentinel = self.output / "keep.txt"
        sentinel.write_text("belongs to user", encoding="utf-8")
        before = sentinel.stat().st_mtime_ns
        with self.assertRaisesRegex(storage.PersonaStorageError, "non-empty unowned"):
            self.publish()
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "belongs to user")
        self.assertEqual(sentinel.stat().st_mtime_ns, before)
        self.assertFalse((self.output / storage.OWNER_MARKER_NAME).exists())

    def test_plan_only_publish_does_not_create_output_or_any_parent(self):
        populate = mock.Mock()
        validate = mock.Mock()
        result = self.publish(
            plan_only=True, populate=populate, validate=validate
        )
        self.assertTrue(result.plan_only)
        self.assertFalse(result.published)
        self.assertEqual(result.owner["replay_id"], "replay-01")
        self.assertEqual(result.owner["state"], "ready")
        self.assertFalse(self.output.exists())
        self.assertFalse(self.output.parent.exists())
        populate.assert_not_called()
        validate.assert_not_called()

    def test_root_is_invisible_until_validated_then_published_ready_for_strict_reuse(self):
        self.output.parent.mkdir(parents=True)
        callback_states = []

        def populate(staging):
            callback_states.append(("populate", self.output.exists()))
            staging_owner = json.loads(
                (staging / storage.STAGING_OWNER_MARKER_NAME).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(staging_owner["state"], "staging_bound")
            storage.atomic_write_file(staging / "payload.txt", b"complete W0\n")

        def validate(staging):
            callback_states.append(("validate", self.output.exists()))
            self.assertEqual((staging / "payload.txt").read_bytes(), b"complete W0\n")

        first = self.publish(populate=populate, validate=validate)
        self.assertTrue(first.published)
        self.assertTrue(first.durability_confirmed)
        self.assertTrue(first.identity_confirmed)
        self.assertIsNone(first.warning)
        self.assertEqual(callback_states, [("populate", False), ("validate", False)])
        self.assertTrue((self.output / "payload.txt").is_file())
        self.assertEqual(
            storage.load_staging_owner_marker(self.output)["state"],
            "staging_bound",
        )
        self.assertTrue((self.output / storage.NOREPLACE_PROBE_SOURCE).is_dir())
        self.assertTrue((self.output / storage.NOREPLACE_PROBE_DESTINATION).is_dir())
        marker_path = self.output / storage.OWNER_MARKER_NAME
        before_time = marker_path.stat().st_mtime_ns
        loaded = storage.require_ready_owned_root(
            self.output,
            profile="tiny",
            replay_id="replay-01",
            plan_sha256=PLAN_SHA,
            manifest_sha256=MANIFEST_SHA,
        )
        self.assertEqual(loaded["state"], "ready")
        self.assertEqual(marker_path.stat().st_mtime_ns, before_time)
        with self.assertRaisesRegex(storage.PersonaStorageError, "requires a missing"):
            self.publish()
        self.assertEqual(marker_path.stat().st_mtime_ns, before_time)
        with self.assertRaisesRegex(storage.PersonaStorageError, "manifest binding"):
            storage.require_ready_owned_root(
                self.output,
                profile="tiny",
                replay_id="replay-01",
                plan_sha256=PLAN_SHA,
                manifest_sha256="3" * 64,
            )

    def test_marker_mismatch_never_reuses_or_replaces_existing_ready_root(self):
        self.output.parent.mkdir(parents=True)
        self.publish()
        marker = self.output / storage.OWNER_MARKER_NAME
        before = marker.read_bytes()
        with self.assertRaisesRegex(storage.PersonaStorageError, "plan binding"):
            storage.require_ready_owned_root(
                self.output,
                profile="tiny",
                replay_id="replay-01",
                plan_sha256="3" * 64,
                manifest_sha256=MANIFEST_SHA,
            )
        self.assertEqual(marker.read_bytes(), before)

    def test_concurrent_final_creation_is_never_replaced_or_deleted(self):
        self.output.parent.mkdir(parents=True)
        original = storage._rename_directory_noreplace

        def create_foreign_final_then_rename(*args, **kwargs):
            if args[3] == self.output.name:
                self.output.mkdir()
                sentinel = self.output / "user.txt"
                sentinel.write_text("foreign final", encoding="utf-8")
            return original(*args, **kwargs)

        with mock.patch.object(
            storage,
            "_rename_directory_noreplace",
            side_effect=create_foreign_final_then_rename,
        ):
            with self.assertRaisesRegex(storage.PersonaStorageError, "left final untouched"):
                self.publish()
        self.assertEqual(
            (self.output / "user.txt").read_text(encoding="utf-8"), "foreign final"
        )
        stages = list(self.output.parent.glob(f".{self.output.name}.persona-*.staging"))
        self.assertEqual(len(stages), 1)
        self.assertEqual(storage.load_owner_marker(stages[0])["state"], "ready")

    def test_concurrent_empty_final_is_not_replaced_by_posix_directory_rename(self):
        self.output.parent.mkdir(parents=True)
        original = storage._rename_directory_noreplace
        foreign_identity = None

        def create_empty_foreign_final_then_rename(*args, **kwargs):
            nonlocal foreign_identity
            if args[3] == self.output.name:
                self.output.mkdir()
                metadata = self.output.lstat()
                foreign_identity = (metadata.st_dev, metadata.st_ino)
            return original(*args, **kwargs)

        with mock.patch.object(
            storage,
            "_rename_directory_noreplace",
            side_effect=create_empty_foreign_final_then_rename,
        ):
            with self.assertRaisesRegex(storage.PersonaStorageError, "left final untouched"):
                self.publish()
        current = self.output.lstat()
        self.assertEqual((current.st_dev, current.st_ino), foreign_identity)
        self.assertEqual(list(self.output.iterdir()), [])
        stages = list(self.output.parent.glob(f".{self.output.name}.persona-*.staging"))
        self.assertEqual(len(stages), 1)
        self.assertEqual(storage.load_owner_marker(stages[0])["state"], "ready")

    def test_missing_platform_capability_fails_before_any_output_write(self):
        populate = mock.Mock()
        validate = mock.Mock()
        with mock.patch.object(
            storage,
            "_require_noreplace_directory_support",
            side_effect=storage.PersonaStorageError("unsupported"),
        ):
            with self.assertRaisesRegex(storage.PersonaStorageError, "unsupported"):
                self.publish(populate=populate, validate=validate)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.output.parent.exists())
        populate.assert_not_called()
        validate.assert_not_called()

    def test_post_rename_fsync_failure_returns_published_uncertain_result(self):
        self.output.parent.mkdir(parents=True)
        original_rename = storage._rename_directory_noreplace
        original_fsync = os.fsync
        root_was_renamed = False

        def tracked_rename(*args, **kwargs):
            nonlocal root_was_renamed
            result = original_rename(*args, **kwargs)
            if args[3] == self.output.name:
                root_was_renamed = True
            return result

        def fail_after_root_rename(descriptor):
            if root_was_renamed:
                raise OSError("injected post-rename fsync failure")
            return original_fsync(descriptor)

        with mock.patch.object(
            storage, "_rename_directory_noreplace", side_effect=tracked_rename
        ), mock.patch.object(os, "fsync", side_effect=fail_after_root_rename):
            result = self.publish()
        self.assertTrue(result.published)
        self.assertFalse(result.durability_confirmed)
        self.assertTrue(result.identity_confirmed)
        self.assertIn("fsync failed", result.warning)
        self.assertEqual(
            storage.require_ready_owned_root(
                self.output,
                profile="tiny",
                replay_id="replay-01",
                plan_sha256=PLAN_SHA,
                manifest_sha256=MANIFEST_SHA,
            )["state"],
            "ready",
        )
        before = {
            path.relative_to(self.output).as_posix(): path.lstat().st_mtime_ns
            for path in (self.output, *self.output.rglob("*"))
        }
        storage.confirm_ready_root_durability(self.output)
        after = {
            path.relative_to(self.output).as_posix(): path.lstat().st_mtime_ns
            for path in (self.output, *self.output.rglob("*"))
        }
        self.assertEqual(after, before)

    def test_failed_population_leaves_owned_staging_and_no_final(self):
        self.output.parent.mkdir(parents=True)

        def fail(staging):
            storage.atomic_write_file(staging / "partial.txt", b"partial\n")
            raise RuntimeError("injected population failure")

        with self.assertRaisesRegex(RuntimeError, "injected"):
            self.publish(populate=fail)
        self.assertFalse(self.output.exists())
        stages = list(self.output.parent.glob(f".{self.output.name}.persona-*.staging"))
        self.assertEqual(len(stages), 1)
        staging_owner = storage.load_staging_owner_marker(stages[0])
        self.assertEqual(staging_owner["state"], "staging_bound")
        self.assertEqual((stages[0] / "partial.txt").read_bytes(), b"partial\n")


class TestAtomicHelpers(StorageTestCase):
    def test_atomic_directory_creation_and_plan_only_are_non_destructive(self):
        planned = self.home / "new" / "nested"
        self.assertTrue(
            storage.atomic_create_directory(planned, parents=True, plan_only=True)
        )
        self.assertFalse(planned.parent.exists())
        self.assertTrue(storage.atomic_create_directory(planned, parents=True))
        self.assertTrue(planned.is_dir())
        self.assertFalse(storage.atomic_create_directory(planned, parents=True))

        alias = self.home / "nested-alias"
        try:
            alias.symlink_to(planned, target_is_directory=True)
        except OSError as exc:  # pragma: no cover - Windows policy
            self.skipTest(f"directory symlink unavailable: {exc}")
        with self.assertRaisesRegex(storage.PersonaStorageError, "plain directory"):
            storage.atomic_create_directory(alias / "unsafe")

    def test_atomic_file_create_is_no_clobber(self):
        directory = self.home / "atomic"
        directory.mkdir()
        target = directory / "receipt.json"
        storage.atomic_write_file(target, b"one\n", plan_only=True)
        self.assertFalse(target.exists())
        storage.atomic_write_file(target, b"one\n")
        self.assertEqual(target.read_bytes(), b"one\n")
        with self.assertRaisesRegex(storage.PersonaStorageError, "replace existing"):
            storage.atomic_write_file(target, b"unknown overwrite\n")
        self.assertEqual(target.read_bytes(), b"one\n")
        self.assertEqual([path.name for path in directory.iterdir()], [target.name])

    def test_racing_file_creation_is_not_clobbered_and_temp_is_retained(self):
        directory = self.home / "atomic-race"
        directory.mkdir()
        target = directory / "new.txt"
        original = storage._rename_directory_noreplace

        def create_foreign_then_rename(*args, **kwargs):
            if args[3] == target.name:
                target.write_bytes(b"foreign\n")
            return original(*args, **kwargs)

        with mock.patch.object(
            storage,
            "_rename_directory_noreplace",
            side_effect=create_foreign_then_rename,
        ):
            with self.assertRaisesRegex(storage.PersonaStorageError, "appeared"):
                storage.atomic_write_file(target, b"new\n")
        self.assertEqual(target.read_bytes(), b"foreign\n")
        names = sorted(path.name for path in directory.iterdir())
        self.assertIn(target.name, names)
        self.assertEqual(len(names), 2)
        self.assertTrue(names[0].startswith(f".{target.name}."))

    def test_module_exposes_no_destructive_root_reset_primitive(self):
        self.assertFalse(hasattr(storage, "reset_owned_root"))
        self.assertFalse(hasattr(storage, "delete_owned_root"))
        self.assertFalse(hasattr(storage, "cleanup_unknown_root"))


class TestCapacityPlanning(unittest.TestCase):
    def inputs(self, **changes):
        values = {
            "physical_files": 195_000,
            "logical_members": 210_000,
            "current_chunks": 2_400_000,
            "history_only_chunks": 1_200_000,
            "raw_bytes": 100,
            "cas_bytes": 50,
            "index_bytes": 25,
            "inodes": 250_000,
            "staging_peak_bytes": 10,
            "staging_peak_inodes": 20,
            "filesystem_allocation_unit_bytes": 1,
            "allocation_overhead_bytes": 250_000,
            "replay_count": 3,
        }
        values.update(changes)
        return storage.CapacityInputs(**values)

    def test_projection_multiplies_every_retained_replay_and_adds_one_staging_peak(self):
        plan = storage.project_capacity(self.inputs())
        self.assertEqual(plan.projected_physical_files, 585_000)
        self.assertEqual(plan.retained_bytes_per_replay, 250_175)
        self.assertEqual(plan.projected_retained_bytes, 750_525)
        self.assertEqual(plan.required_peak_bytes, 750_535)
        self.assertEqual(plan.projected_retained_inodes, 750_000)
        self.assertEqual(plan.required_peak_inodes, 750_020)
        rendered = plan.as_dict()
        self.assertEqual(rendered["replay_count"], 3)
        self.assertEqual(rendered["all_replays"]["current_chunks"], 7_200_000)
        self.assertEqual(
            rendered["all_replays"]["current_plus_history_chunks"], 10_800_000
        )
        self.assertEqual(rendered["required_peak"]["sequential_staging_replays"], 1)
        digest = storage.capacity_plan_sha256(plan)
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        changed = storage.project_capacity(self.inputs(raw_bytes=101))
        self.assertNotEqual(digest, storage.capacity_plan_sha256(changed))

    def test_projection_rejects_negative_boolean_and_incomplete_cardinalities(self):
        cases = (
            {"raw_bytes": -1},
            {"physical_files": True},
            {"logical_members": 194_999},
            {"inodes": 194_999},
            {"replay_count": 0},
            {"replay_count": 1},
            {"replay_count": 2},
            {"replay_count": 4},
        )
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(storage.PersonaStorageError):
                self.inputs(**changes)

        tiny_partial = self.inputs(profile="tiny", replay_count=2)
        self.assertEqual(tiny_partial.replay_count, 2)

    def test_capacity_caps_and_reserves_pass_at_exact_boundary(self):
        plan = storage.project_capacity(self.inputs())
        availability = storage.AvailableCapacity(
            free_bytes=750_635, free_inodes=750_220
        )
        limits = storage.CapacityLimits(
            byte_cap=750_535,
            inode_cap=750_020,
            reserve_bytes=100,
            reserve_inodes=200,
        )
        result = storage.check_capacity(plan, availability, limits)
        self.assertEqual(result.free_bytes_after, 100)
        self.assertEqual(result.free_inodes_after, 200)
        self.assertTrue(result.as_dict()["passed"])

    def test_capacity_rejects_each_cap_and_reserve_shortfall(self):
        plan = storage.project_capacity(self.inputs())
        failures = (
            (
                storage.AvailableCapacity(10_000_000, 10_000_000),
                storage.CapacityLimits(750_534, 1_000_000, 0, 0),
                "peak bytes",
            ),
            (
                storage.AvailableCapacity(10_000_000, 10_000_000),
                storage.CapacityLimits(1_000_000, 750_019, 0, 0),
                "peak inodes",
            ),
            (
                storage.AvailableCapacity(750_635, 1_000_000),
                storage.CapacityLimits(1_000_000, 1_000_000, 101, 0),
                "free-byte reserve",
            ),
            (
                storage.AvailableCapacity(10_000_000, 750_220),
                storage.CapacityLimits(1_000_000, 1_000_000, 0, 201),
                "free-inode reserve",
            ),
        )
        for availability, limits, message in failures:
            with self.subTest(message=message), self.assertRaisesRegex(
                storage.PersonaStorageError, message
            ):
                storage.check_capacity(plan, availability, limits)

    def test_probe_uses_nearest_existing_plain_ancestor(self):
        with tempfile.TemporaryDirectory(prefix="kio-persona-probe-") as temporary:
            existing = Path(temporary).resolve()
            destination = existing / "not-yet" / "replay-01"
            statvfs = SimpleNamespace(f_favail=456)
            with mock.patch.object(
                storage.shutil, "disk_usage", return_value=SimpleNamespace(free=123)
            ) as disk_usage, mock.patch.object(
                storage.os, "statvfs", return_value=statvfs, create=True
            ) as statvfs_call:
                measured = storage.probe_available_capacity(destination)
            self.assertEqual(measured.free_bytes, 123)
            self.assertEqual(measured.free_inodes, 456)
            self.assertEqual(measured.probe_path, existing)
            self.assertEqual(measured.inode_source, "statvfs")
            disk_usage.assert_called_once_with(existing)
            statvfs_call.assert_called_once_with(existing)

    def test_explicit_inode_budget_supports_platforms_without_statvfs(self):
        with tempfile.TemporaryDirectory(prefix="kio-persona-probe-") as temporary:
            destination = Path(temporary).resolve() / "replay-01"
            with mock.patch.object(
                storage.shutil, "disk_usage", return_value=SimpleNamespace(free=123)
            ), mock.patch.object(
                storage.os,
                "statvfs",
                side_effect=AttributeError("unavailable"),
                create=True,
            ):
                with self.assertRaisesRegex(
                    storage.PersonaStorageError, "explicit_free_inodes"
                ):
                    storage.probe_available_capacity(destination)
                measured = storage.probe_available_capacity(
                    destination, explicit_free_inodes=456
                )
            self.assertEqual(measured.free_inodes, 456)
            self.assertEqual(measured.inode_source, "explicit_no_statvfs")

    def test_scope_limits_match_file_scope_and_direct_child_contract(self):
        exact = storage.check_scope_limits([storage.MAX_FILE_BYTES] * 8)
        self.assertEqual(exact["scope_bytes"], storage.MAX_SCOPE_BYTES)
        with self.assertRaisesRegex(storage.PersonaStorageError, r"file_sizes\[0\]"):
            storage.check_scope_limits([storage.MAX_FILE_BYTES + 1])
        with self.assertRaisesRegex(storage.PersonaStorageError, "scope bytes"):
            storage.check_scope_limits([storage.MAX_FILE_BYTES] * 9)
        with self.assertRaisesRegex(storage.PersonaStorageError, "limit"):
            storage.check_scope_limits(
                [0] * (storage.MAX_DIRECT_FILES_PER_SCOPE + 1)
            )


if __name__ == "__main__":
    unittest.main()
