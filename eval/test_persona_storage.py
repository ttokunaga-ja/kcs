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


ARTIFACT_BUNDLE_SHA = "sha256:" + "1" * 64
ROOT_BINDING_SHA = "sha256:" + "2" * 64


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
            artifact_bundle_sha256=ARTIFACT_BUNDLE_SHA,
            root_binding_sha256=ROOT_BINDING_SHA,
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
            artifact_bundle_sha256=ARTIFACT_BUNDLE_SHA,
            root_binding_sha256=ROOT_BINDING_SHA,
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
                "artifact_bundle_sha256",
                "root_binding_sha256",
            },
        )
        self.assertEqual(building["fixture_id"], "kio-persona-pc-v2")
        self.assertEqual(building["state"], "building")

        ready = storage.make_owner_marker(
            profile="full",
            replay_id="replay-03",
            state="ready",
            artifact_bundle_sha256=ARTIFACT_BUNDLE_SHA,
            root_binding_sha256=ROOT_BINDING_SHA,
        )
        self.assertEqual(ready["root_binding_sha256"], ROOT_BINDING_SHA)
        self.assertEqual(storage.validate_owner_marker(ready), ready)

    def test_marker_validation_rejects_unknown_values_and_noncanonical_fields(self):
        cases = (
            {"profile": "unknown", "replay_id": "replay-01", "state": "building"},
            {"profile": "tiny", "replay_id": "replay-04", "state": "building"},
            {"profile": "tiny", "replay_id": "replay-01", "state": "complete"},
        )
        for values in cases:
            with self.subTest(values=values), self.assertRaises(storage.PersonaStorageError):
                storage.make_owner_marker(
                    artifact_bundle_sha256=ARTIFACT_BUNDLE_SHA,
                    root_binding_sha256=ROOT_BINDING_SHA,
                    **values,
                )
        invalid = storage.make_owner_marker(
            profile="tiny", replay_id="replay-01", state="building",
            artifact_bundle_sha256=ARTIFACT_BUNDLE_SHA,
            root_binding_sha256=ROOT_BINDING_SHA,
        )
        invalid["surprise"] = True
        with self.assertRaisesRegex(storage.PersonaStorageError, "field set"):
            storage.validate_owner_marker(invalid)
        for invalid_profile in ([], 3):
            invalid = storage.make_owner_marker(
                profile="tiny", replay_id="replay-01", state="building",
                artifact_bundle_sha256=ARTIFACT_BUNDLE_SHA,
                root_binding_sha256=ROOT_BINDING_SHA,
            )
            invalid["profile"] = invalid_profile
            with self.subTest(invalid_profile=invalid_profile), self.assertRaises(
                storage.PersonaStorageError
            ):
                storage.validate_owner_marker(invalid)
        invalid = storage.make_owner_marker(
            profile="tiny", replay_id="replay-01", state="building",
            artifact_bundle_sha256=ARTIFACT_BUNDLE_SHA,
            root_binding_sha256=ROOT_BINDING_SHA,
        )
        invalid["schema_version"] = True
        with self.assertRaisesRegex(storage.PersonaStorageError, "schema"):
            storage.validate_owner_marker(invalid)
        invalid = storage.make_owner_marker(
            profile="tiny", replay_id="replay-01", state="ready",
            artifact_bundle_sha256=ARTIFACT_BUNDLE_SHA,
            root_binding_sha256=ROOT_BINDING_SHA,
        )
        invalid["owner"] = "kio.persona.storage-owner/v1"
        with self.assertRaisesRegex(storage.PersonaStorageError, "not owned"):
            storage.validate_owner_marker(invalid)
        invalid["owner"] = storage.OWNER_ID
        invalid["schema_version"] = 1
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

    def test_hardlinked_owner_marker_is_rejected(self):
        self.output.parent.mkdir(parents=True)
        self.publish()
        marker = self.output / storage.OWNER_MARKER_NAME
        alias = self.home / "owner-marker-alias.json"
        try:
            os.link(marker, alias)
        except OSError as exc:  # pragma: no cover - platform policy
            self.skipTest(f"hard links unavailable: {exc}")
        with self.assertRaisesRegex(storage.PersonaStorageError, "single-link"):
            storage.load_owner_marker(self.output)
        self.assertEqual(alias.read_bytes(), marker.read_bytes())

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
            artifact_bundle_sha256=ARTIFACT_BUNDLE_SHA,
            root_binding_sha256=ROOT_BINDING_SHA,
        )
        self.assertEqual(loaded["state"], "ready")
        self.assertEqual(marker_path.stat().st_mtime_ns, before_time)
        with self.assertRaisesRegex(storage.PersonaStorageError, "requires a missing"):
            self.publish()
        self.assertEqual(marker_path.stat().st_mtime_ns, before_time)
        with self.assertRaisesRegex(storage.PersonaStorageError, "root binding"):
            storage.require_ready_owned_root(
                self.output,
                profile="tiny",
                replay_id="replay-01",
                artifact_bundle_sha256=ARTIFACT_BUNDLE_SHA,
                root_binding_sha256="sha256:" + "3" * 64,
            )

    def test_marker_mismatch_never_reuses_or_replaces_existing_ready_root(self):
        self.output.parent.mkdir(parents=True)
        self.publish()
        marker = self.output / storage.OWNER_MARKER_NAME
        before = marker.read_bytes()
        with self.assertRaisesRegex(storage.PersonaStorageError, "artifact bundle binding"):
            storage.require_ready_owned_root(
                self.output,
                profile="tiny",
                replay_id="replay-01",
                artifact_bundle_sha256="sha256:" + "3" * 64,
                root_binding_sha256=ROOT_BINDING_SHA,
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
                artifact_bundle_sha256=ARTIFACT_BUNDLE_SHA,
                root_binding_sha256=ROOT_BINDING_SHA,
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


if __name__ == "__main__":
    unittest.main()
