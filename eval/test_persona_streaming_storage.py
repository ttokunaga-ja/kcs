from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

try:
    from . import persona_streaming_storage as streaming
except ImportError:  # pragma: no cover
    import persona_streaming_storage as streaming


class _OneShotRows:
    def __init__(self, rows):
        self._rows = tuple(rows)
        self.iterations = 0
        self.yielded = 0

    def __iter__(self):
        self.iterations += 1
        if self.iterations != 1:
            raise AssertionError("row input was iterated more than once")
        for row in self._rows:
            self.yielded += 1
            yield row


class PersonaStreamingStorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        # macOS spells the temporary root through /var -> /private/var; use
        # the canonical spelling because production rejects symlinked path
        # components instead of silently following them.
        self.parent = Path(self.temporary.name).resolve()
        self.limits = streaming.ArtifactLimits(
            max_row_bytes=256,
            max_rows_per_shard=2,
            max_shard_bytes=512,
            max_shards=8,
            max_total_rows=12,
            max_total_bytes=4096,
        )
        self.rows = [
            {"item_id": f"item-{index:02d}", "ordinal": index, "text": "あ" * index}
            for index in range(5)
        ]

    def tearDown(self):
        self.temporary.cleanup()

    def _publish(self, name="artifact", rows=None, limits=None):
        return streaming.publish_jsonl_artifact(
            self.parent / name,
            self.rows if rows is None else rows,
            limits=self.limits if limits is None else limits,
        )

    def _canonical_file(self, value):
        return streaming.canonical_json_bytes(value) + b"\n"

    def test_streaming_round_trip_descriptors_and_locators(self):
        source = _OneShotRows(self.rows)
        result = self._publish(rows=source)
        self.assertTrue(result.published)
        self.assertFalse(result.formal_publication_attested)
        self.assertEqual(
            result.formal_publication_blockers,
            (streaming.FORMAL_PUBLICATION_BLOCKER,),
        )
        self.assertEqual(source.iterations, 1)
        self.assertEqual(source.yielded, len(self.rows))
        receipt = result.artifact
        self.assertFalse(receipt.formal_publication_attested)
        self.assertEqual(
            receipt.formal_publication_blockers,
            ("source_directory_inode_not_bound_by_rename",),
        )
        self.assertEqual(receipt.rows, 5)
        self.assertEqual(len(receipt.shards), 3)
        self.assertEqual([item.rows for item in receipt.shards], [2, 2, 1])
        self.assertEqual(
            [item.file for item in receipt.shards],
            [
                "shards/shard-000000.jsonl",
                "shards/shard-000001.jsonl",
                "shards/shard-000002.jsonl",
            ],
        )
        observed = list(
            streaming.iter_jsonl_records(self.parent / "artifact", limits=self.limits)
        )
        self.assertEqual([item.value for item in observed], self.rows)
        self.assertEqual(
            [item.shard_ordinal for item in observed], [0, 0, 1, 1, 2]
        )
        self.assertEqual(observed[0].byte_offset, 0)
        self.assertEqual(
            observed[1].byte_offset,
            len(self._canonical_file(self.rows[0])),
        )
        for record, row in zip(observed, self.rows):
            raw = self._canonical_file(row)
            self.assertEqual(record.byte_length, len(raw))
            self.assertEqual(record.row_sha256, hashlib.sha256(raw).hexdigest())
        verified = streaming.verify_jsonl_artifact(
            self.parent / "artifact",
            limits=self.limits,
            expected_envelope_sha256=receipt.storage_envelope_sha256,
        )
        self.assertEqual(verified, receipt)
        self.assertEqual(
            list(streaming.iter_jsonl_artifact(self.parent / "artifact", limits=self.limits)),
            self.rows,
        )

    def test_storage_envelope_is_canonical_and_ready_binds_it(self):
        receipt = self._publish().artifact
        root = self.parent / "artifact"
        envelope_raw = (root / streaming.STORAGE_ENVELOPE_NAME).read_bytes()
        self.assertEqual(
            hashlib.sha256(envelope_raw).hexdigest(),
            receipt.storage_envelope_sha256,
        )
        envelope = json.loads(envelope_raw)
        self.assertNotIn("logical_schema", envelope)
        self.assertNotIn("logical_sha256", envelope)
        self.assertEqual(envelope["limits"], self.limits.as_dict())
        self.assertEqual(
            envelope_raw, streaming.canonical_json_bytes(envelope) + b"\n"
        )
        ready = json.loads((root / streaming.READY_NAME).read_bytes())
        self.assertEqual(
            ready,
            {
                "schema": streaming.READY_SCHEMA,
                "schema_version": streaming.SCHEMA_VERSION,
                "storage_envelope_sha256": receipt.storage_envelope_sha256,
            },
        )
        self.assertEqual(
            set(item.name for item in root.iterdir()),
            {
                streaming.STORAGE_ENVELOPE_NAME,
                streaming.READY_NAME,
                streaming.SHARDS_DIRECTORY_NAME,
            },
        )

    def test_identical_existing_is_read_back_strict_noop(self):
        first = self._publish()
        root = self.parent / "artifact"
        before = {
            path.relative_to(root).as_posix(): (
                path.lstat().st_dev,
                path.lstat().st_ino,
                path.lstat().st_size,
                path.lstat().st_mtime_ns,
                path.read_bytes() if path.is_file() else None,
            )
            for path in (root, *sorted(root.rglob("*")))
        }
        source = _OneShotRows(self.rows)
        second = self._publish(rows=source)
        self.assertFalse(second.published)
        self.assertEqual(second.artifact, first.artifact)
        self.assertEqual(source.iterations, 1)
        after = {
            path.relative_to(root).as_posix(): (
                path.lstat().st_dev,
                path.lstat().st_ino,
                path.lstat().st_size,
                path.lstat().st_mtime_ns,
                path.read_bytes() if path.is_file() else None,
            )
            for path in (root, *sorted(root.rglob("*")))
        }
        self.assertEqual(after, before)

    def test_ambiguous_postrename_fsync_is_reconciled_by_exact_noop(self):
        destination = self.parent / "durability-retry"
        original_fsync = streaming.os.fsync
        injected = {"raised": False}

        def fail_first_postrename_parent_sync(descriptor):
            if destination.exists() and not injected["raised"]:
                opened = os.fstat(descriptor)
                parent = self.parent.stat()
                if (opened.st_dev, opened.st_ino) == (parent.st_dev, parent.st_ino):
                    injected["raised"] = True
                    raise OSError("injected post-rename parent fsync failure")
            return original_fsync(descriptor)

        with mock.patch.object(
            streaming.os, "fsync", side_effect=fail_first_postrename_parent_sync
        ):
            with self.assertRaisesRegex(OSError, "post-rename parent fsync"):
                self._publish(name="durability-retry")
        self.assertTrue(injected["raised"])
        self.assertTrue(destination.is_dir())

        synchronized_inodes = []

        def record_sync(descriptor):
            opened = os.fstat(descriptor)
            synchronized_inodes.append((opened.st_dev, opened.st_ino))
            return original_fsync(descriptor)

        with mock.patch.object(streaming.os, "fsync", side_effect=record_sync):
            retried = self._publish(name="durability-retry")
        self.assertFalse(retried.published)
        self.assertEqual(
            set(synchronized_inodes),
            {
                (self.parent.stat().st_dev, self.parent.stat().st_ino),
                (destination.stat().st_dev, destination.stat().st_ino),
                (
                    (destination / streaming.SHARDS_DIRECTORY_NAME).stat().st_dev,
                    (destination / streaming.SHARDS_DIRECTORY_NAME).stat().st_ino,
                ),
            },
        )

    def test_different_existing_artifact_is_never_replaced(self):
        first = self._publish().artifact
        root = self.parent / "artifact"
        before = (root / streaming.STORAGE_ENVELOPE_NAME).read_bytes()
        changed = list(self.rows)
        changed[-1] = {**changed[-1], "text": "different"}
        with self.assertRaisesRegex(
            streaming.PersonaStreamingStorageError, "differs from streamed input"
        ):
            self._publish(rows=_OneShotRows(changed))
        self.assertEqual(
            (root / streaming.STORAGE_ENVELOPE_NAME).read_bytes(), before
        )
        self.assertEqual(
            streaming.verify_jsonl_artifact(root, limits=self.limits), first
        )

    def test_partial_final_is_not_adopted_or_modified(self):
        root = self.parent / "partial"
        root.mkdir()
        (root / "foreign.txt").write_text("keep", encoding="utf-8")
        before = (root.lstat().st_ino, (root / "foreign.txt").read_bytes())
        source = _OneShotRows(self.rows)
        with self.assertRaises(streaming.PersonaStreamingStorageError):
            self._publish(name="partial", rows=source)
        self.assertEqual(source.iterations, 0)
        self.assertEqual(
            (root.lstat().st_ino, (root / "foreign.txt").read_bytes()), before
        )

    def test_failed_stream_retains_unpublished_stage_and_no_final(self):
        def broken():
            yield self.rows[0]
            raise RuntimeError("source failed")

        with self.assertRaisesRegex(RuntimeError, "source failed"):
            self._publish(name="broken", rows=broken())
        self.assertFalse((self.parent / "broken").exists())
        stages = list(self.parent.glob(".broken.stream-*.staging"))
        self.assertEqual(len(stages), 1)
        self.assertTrue((stages[0] / streaming.SHARDS_DIRECTORY_NAME).is_dir())
        self.assertNotIn(streaming.READY_NAME, {item.name for item in stages[0].iterdir()})

    def test_atomic_race_leaves_foreign_final_and_stage(self):
        destination = self.parent / "raced"
        original = streaming.storage._rename_directory_noreplace

        def race(fd, parent, source, target):
            # Commit-file publication uses the same primitive; inject only at
            # the final whole-directory publication boundary.
            if target != destination.name:
                return original(fd, parent, source, target)
            destination.mkdir()
            (destination / "foreign.txt").write_text("foreign", encoding="utf-8")
            raise FileExistsError("raced")

        with mock.patch.object(
            streaming.storage, "_rename_directory_noreplace", side_effect=race
        ):
            with self.assertRaisesRegex(
                streaming.PersonaStreamingStorageError, "left it and stage untouched"
            ):
                self._publish(name="raced")
        self.assertEqual((destination / "foreign.txt").read_text(), "foreign")
        self.assertEqual(len(list(self.parent.glob(".raced.stream-*.staging"))), 1)

    def test_source_name_swap_is_detected_only_after_nonformal_publication(self):
        destination = self.parent / "source-swapped"
        original = streaming.storage._rename_directory_noreplace
        retained = {}

        def replace_source(fd, parent, source, target):
            if target != destination.name:
                return original(fd, parent, source, target)
            original_stage = parent / f"{source}.verified-original"
            os.rename(parent / source, original_stage)
            replacement = parent / source
            replacement.mkdir()
            (replacement / "FOREIGN").write_text("foreign", encoding="utf-8")
            retained["original_stage"] = original_stage
            return original(fd, parent, source, target)

        with mock.patch.object(
            streaming.storage,
            "_rename_directory_noreplace",
            side_effect=replace_source,
        ):
            with self.assertRaisesRegex(
                streaming.PersonaStreamingStorageError,
                "published artifact inode differs from stage",
            ):
                self._publish(name="source-swapped")
        self.assertEqual((destination / "FOREIGN").read_text(), "foreign")
        self.assertTrue(retained["original_stage"].is_dir())
        # This unavoidable source-name race is why every successful receipt is
        # explicitly non-formal; no caller may promote READY into an attestation.
        clean = self._publish(name="nonformal-clean")
        self.assertFalse(clean.formal_publication_attested)
        self.assertEqual(
            clean.formal_publication_blockers,
            ("source_directory_inode_not_bound_by_rename",),
        )

    def test_row_total_and_shard_bounds_fail_before_publication(self):
        cases = (
            (
                "row-cap",
                streaming.ArtifactLimits(
                    max_row_bytes=20,
                    max_rows_per_shard=2,
                    max_shard_bytes=40,
                    max_shards=8,
                    max_total_rows=12,
                    max_total_bytes=4096,
                ),
                [{"value": "x" * 100}],
                "max_row_bytes",
            ),
            (
                "total-rows",
                streaming.ArtifactLimits(
                    max_row_bytes=256,
                    max_rows_per_shard=2,
                    max_shard_bytes=512,
                    max_shards=8,
                    max_total_rows=2,
                    max_total_bytes=4096,
                ),
                self.rows,
                "max_total_rows",
            ),
            (
                "shard-cap",
                streaming.ArtifactLimits(
                    max_row_bytes=256,
                    max_rows_per_shard=1,
                    max_shard_bytes=256,
                    max_shards=2,
                    max_total_rows=12,
                    max_total_bytes=4096,
                ),
                self.rows,
                "max_shards",
            ),
        )
        for name, limits, rows, message in cases:
            with self.subTest(name=name):
                with self.assertRaisesRegex(
                    streaming.PersonaStreamingStorageError, message
                ):
                    self._publish(name=name, rows=iter(rows), limits=limits)
                self.assertFalse((self.parent / name).exists())
                self.assertEqual(
                    len(list(self.parent.glob(f".{name}.stream-*.staging"))), 1
                )

    def test_floats_nonobjects_and_out_of_range_integers_are_rejected(self):
        bad = (
            [{"value": 1.25}],
            [["not", "an", "object"]],
            [{"value": 2**63}],
        )
        for index, rows in enumerate(bad):
            with self.subTest(index=index):
                with self.assertRaises(streaming.PersonaStreamingStorageError):
                    self._publish(name=f"bad-{index}", rows=iter(rows))
                self.assertFalse((self.parent / f"bad-{index}").exists())

    def test_tamper_hardlink_symlink_and_wrong_expected_digest_fail_closed(self):
        for kind in ("tamper", "hardlink", "symlink", "fifo", "ready"):
            with self.subTest(kind=kind):
                root = self.parent / kind
                receipt = self._publish(name=kind).artifact
                shard = root / streaming.SHARDS_DIRECTORY_NAME / "shard-000000.jsonl"
                if kind == "tamper":
                    raw = bytearray(shard.read_bytes())
                    raw[5] = ord("X")
                    shard.write_bytes(raw)
                elif kind == "hardlink":
                    os.link(shard, self.parent / f"{kind}-extra-link")
                elif kind == "symlink":
                    target = self.parent / "symlink-target"
                    target.write_bytes(shard.read_bytes())
                    shard.unlink()
                    shard.symlink_to(target)
                elif kind == "fifo":
                    shard.unlink()
                    os.mkfifo(shard)
                else:
                    (root / streaming.READY_NAME).write_bytes(
                        self._canonical_file(
                            {
                                "schema": streaming.READY_SCHEMA,
                                "schema_version": streaming.SCHEMA_VERSION,
                                "storage_envelope_sha256": "0" * 64,
                            }
                        )
                    )
                with self.assertRaises(streaming.PersonaStreamingStorageError):
                    streaming.verify_jsonl_artifact(root, limits=self.limits)
                if kind == "hardlink":
                    (self.parent / f"{kind}-extra-link").unlink()
                self.assertTrue(root.exists())
        clean = self._publish(name="wrong-digest").artifact
        with self.assertRaisesRegex(
            streaming.PersonaStreamingStorageError, "digest mismatch"
        ):
            streaming.verify_jsonl_artifact(
                self.parent / "wrong-digest",
                limits=self.limits,
                expected_envelope_sha256=(
                    "0" * 64
                    if clean.storage_envelope_sha256 != "0" * 64
                    else "1" * 64
                ),
            )

    def test_coherent_premature_shard_split_is_rejected(self):
        one_row_limits = streaming.ArtifactLimits(
            max_row_bytes=256,
            max_rows_per_shard=1,
            max_shard_bytes=512,
            max_shards=8,
            max_total_rows=12,
            max_total_bytes=4096,
        )
        root = self.parent / "premature"
        receipt = self._publish(
            name="premature", rows=self.rows[:3], limits=one_row_limits
        ).artifact
        envelope_path = root / streaming.STORAGE_ENVELOPE_NAME
        envelope = json.loads(envelope_path.read_bytes())
        envelope["limits"] = self.limits.as_dict()
        envelope_raw = self._canonical_file(envelope)
        envelope_path.write_bytes(envelope_raw)
        ready = {
            "schema": streaming.READY_SCHEMA,
            "schema_version": streaming.SCHEMA_VERSION,
            "storage_envelope_sha256": hashlib.sha256(envelope_raw).hexdigest(),
        }
        (root / streaming.READY_NAME).write_bytes(self._canonical_file(ready))
        with self.assertRaisesRegex(
            streaming.PersonaStreamingStorageError, "split before"
        ):
            streaming.verify_jsonl_artifact(root, limits=self.limits)
        self.assertNotEqual(
            receipt.storage_envelope_sha256, ready["storage_envelope_sha256"]
        )

    def test_envelope_metadata_change_during_iteration_is_detected(self):
        self._publish(name="metadata-race")
        root = self.parent / "metadata-race"
        stream = streaming.iter_jsonl_records(root, limits=self.limits)
        next(stream)
        envelope = root / streaming.STORAGE_ENVELOPE_NAME
        os.chmod(envelope, 0o640)
        with self.assertRaisesRegex(
            streaming.PersonaStreamingStorageError, "changed during verification"
        ):
            list(stream)

    def test_already_read_shard_metadata_change_is_detected_at_completion(self):
        self._publish(name="old-shard-race")
        root = self.parent / "old-shard-race"
        stream = streaming.iter_jsonl_records(root, limits=self.limits)
        # The third row comes from shard 1, so shard 0 has been closed and
        # locally verified before this mutation.
        for _ in range(3):
            next(stream)
        first = root / streaming.SHARDS_DIRECTORY_NAME / "shard-000000.jsonl"
        os.chmod(first, 0o640)
        with self.assertRaisesRegex(
            streaming.PersonaStreamingStorageError, "before verification completed"
        ):
            list(stream)

    def test_empty_artifact_is_valid_and_deterministic(self):
        first = self._publish(name="empty-a", rows=iter(())).artifact
        second = self._publish(name="empty-b", rows=iter(())).artifact
        self.assertEqual(first.rows, 0)
        self.assertEqual(first.bytes, 0)
        self.assertEqual(first.shards, ())
        self.assertEqual(
            first.storage_envelope_sha256, second.storage_envelope_sha256
        )
        self.assertEqual(
            first.canonical_rows_sha256, hashlib.sha256(b"").hexdigest()
        )
        self.assertEqual(
            list(streaming.iter_jsonl_artifact(first.root, limits=self.limits)), []
        )

    def test_verifier_uses_bounded_fd_scans_instead_of_listdir(self):
        receipt = self._publish(name="bounded-scan").artifact
        with mock.patch.object(
            streaming.os,
            "listdir",
            side_effect=AssertionError("unbounded listdir must not be used"),
        ):
            observed = streaming.verify_jsonl_artifact(
                self.parent / "bounded-scan",
                limits=self.limits,
                expected_envelope_sha256=receipt.storage_envelope_sha256,
            )
        self.assertEqual(observed, receipt)

    def test_windows_and_missing_safe_primitives_fail_closed(self):
        with mock.patch.object(streaming.os, "name", "nt"):
            with self.assertRaisesRegex(
                streaming.PersonaStreamingStorageError, "Windows"
            ):
                self._publish(name="windows")
        with mock.patch.object(streaming.os, "supports_dir_fd", frozenset()):
            with self.assertRaisesRegex(
                streaming.PersonaStreamingStorageError, "directory-fd"
            ):
                self._publish(name="no-dirfd")
        self.assertFalse((self.parent / "windows").exists())
        self.assertFalse((self.parent / "no-dirfd").exists())

    def test_symlinked_ancestor_is_rejected_on_read(self):
        real_parent = self.parent / "real-parent"
        real_parent.mkdir()
        real_root = real_parent / "artifact"
        streaming.publish_jsonl_artifact(real_root, iter(self.rows), limits=self.limits)
        alias = self.parent / "alias-parent"
        alias.symlink_to(real_parent, target_is_directory=True)
        with self.assertRaisesRegex(
            streaming.PersonaStreamingStorageError, "cannot safely traverse"
        ):
            streaming.verify_jsonl_artifact(alias / "artifact", limits=self.limits)

    def test_ancestor_symlink_swap_between_stat_and_open_is_rejected(self):
        safe_parent = self.parent / "swap-parent"
        other_parent = self.parent / "other-parent"
        safe_parent.mkdir()
        other_parent.mkdir()
        streaming.publish_jsonl_artifact(
            safe_parent / "artifact", iter(self.rows), limits=self.limits
        )
        streaming.publish_jsonl_artifact(
            other_parent / "artifact", iter(self.rows), limits=self.limits
        )
        original_stat = streaming.os.stat
        swapped = {"done": False}

        def swap_after_component_stat(path, *args, **kwargs):
            metadata = original_stat(path, *args, **kwargs)
            if (
                path == safe_parent.name
                and kwargs.get("dir_fd") is not None
                and kwargs.get("follow_symlinks") is False
                and not swapped["done"]
            ):
                swapped["done"] = True
                os.rename(safe_parent, self.parent / "swap-parent-original")
                safe_parent.symlink_to(other_parent, target_is_directory=True)
            return metadata

        with mock.patch.object(
            streaming, "_require_supported_platform", return_value=None
        ), mock.patch.object(
            streaming.os, "stat", side_effect=swap_after_component_stat
        ):
            with self.assertRaisesRegex(
                streaming.PersonaStreamingStorageError, "cannot safely traverse"
            ):
                streaming.verify_jsonl_artifact(
                    safe_parent / "artifact", limits=self.limits
                )
        self.assertTrue(swapped["done"])

    def test_limits_are_strictly_typed_and_exact_on_read(self):
        with self.assertRaises(streaming.PersonaStreamingStorageError):
            streaming.ArtifactLimits(max_row_bytes=True)
        self._publish()
        other = streaming.ArtifactLimits(
            max_row_bytes=256,
            max_rows_per_shard=3,
            max_shard_bytes=512,
            max_shards=8,
            max_total_rows=12,
            max_total_bytes=4096,
        )
        with self.assertRaisesRegex(
            streaming.PersonaStreamingStorageError, "limits differ"
        ):
            streaming.verify_jsonl_artifact(self.parent / "artifact", limits=other)


if __name__ == "__main__":
    unittest.main()
