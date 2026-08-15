#!/usr/bin/env python3
"""Focused tests for the streaming storage filesystem primitives."""

import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import persona_storage as storage  # noqa: E402


@unittest.skipUnless(
    sys.platform == "darwin" or sys.platform.startswith("linux"),
    "requires platform atomic no-replace",
)
class StoragePrimitiveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="kio-stream-storage-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_metadata_predicates_reject_links_and_reparse_entries(self):
        directory = self.root / "directory"
        directory.mkdir()
        regular = self.root / "regular"
        regular.write_bytes(b"ok")
        self.assertTrue(storage.is_plain_directory_metadata(directory.lstat()))
        self.assertTrue(storage.is_plain_regular_file_metadata(regular.lstat()))
        link = self.root / "link"
        try:
            link.symlink_to(regular)
        except OSError as exc:  # pragma: no cover - platform policy
            self.skipTest(f"symlinks unavailable: {exc}")
        self.assertFalse(storage.is_plain_regular_file_metadata(link.lstat()))
        self.assertFalse(storage.is_plain_directory_metadata(link.lstat()))

    def test_atomic_write_creates_private_durable_file(self):
        target = self.root / "payload.json"
        storage.atomic_write_file(target, b'{"ok":true}\n')
        self.assertEqual(target.read_bytes(), b'{"ok":true}\n')
        self.assertTrue(storage.is_plain_regular_file_metadata(target.lstat()))
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)

    def test_atomic_write_refuses_existing_symlink_or_special_parent(self):
        target = self.root / "payload"
        target.write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(storage.PersonaStorageError, "replace"):
            storage.atomic_write_file(target, b"new")
        self.assertEqual(target.read_text(encoding="utf-8"), "keep")
        outside = self.root / "outside"
        outside.mkdir()
        alias = self.root / "alias"
        try:
            alias.symlink_to(outside, target_is_directory=True)
        except OSError as exc:  # pragma: no cover - platform policy
            self.skipTest(f"symlinks unavailable: {exc}")
        with self.assertRaises(storage.PersonaStorageError):
            storage.atomic_write_file(alias / "payload", b"new")
        self.assertFalse((outside / "payload").exists())

    def test_atomic_write_race_preserves_foreign_target_and_retains_stage(self):
        target = self.root / "raced"
        original = storage._rename_directory_noreplace

        def race(fd, parent, source, destination):
            if destination == target.name:
                target.write_bytes(b"foreign")
            return original(fd, parent, source, destination)

        with mock.patch.object(storage, "_rename_directory_noreplace", side_effect=race):
            with self.assertRaisesRegex(storage.PersonaStorageError, "appeared"):
                storage.atomic_write_file(target, b"ours")
        self.assertEqual(target.read_bytes(), b"foreign")
        self.assertEqual(len(list(self.root.glob(".raced.*.tmp"))), 1)

    def test_atomic_write_detects_parent_name_swap(self):
        parent = self.root / "parent"
        parent.mkdir()
        target = parent / "payload"
        original = storage._rename_directory_noreplace
        displaced = self.root / "parent-original"

        def swap(fd, path, source, destination):
            os.rename(parent, displaced)
            parent.mkdir()
            return original(fd, path, source, destination)

        with mock.patch.object(storage, "_rename_directory_noreplace", side_effect=swap):
            with self.assertRaisesRegex(storage.PersonaStorageError, "parent changed"):
                storage.atomic_write_file(target, b"ours")
        self.assertFalse((parent / "payload").exists())
        self.assertEqual((displaced / "payload").read_bytes(), b"ours")

    def test_noreplace_directory_primitive_preserves_existing_destination(self):
        source = self.root / "source"
        destination = self.root / "destination"
        source.mkdir()
        destination.mkdir()
        descriptor, _ = storage._open_plain_directory(self.root)
        try:
            with self.assertRaises(FileExistsError):
                storage._rename_directory_noreplace(
                    descriptor, self.root, source.name, destination.name
                )
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        self.assertTrue(source.is_dir())
        self.assertTrue(destination.is_dir())


if __name__ == "__main__":
    unittest.main()
