#!/usr/bin/env python3
"""Read-only safety tests for the persona replay-root lease."""

import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock
import warnings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import persona_root_lock as root_lock  # noqa: E402
import persona_storage as storage  # noqa: E402


PLAN_SHA = "1" * 64
SUITE_SHA = "2" * 64
CAPACITY_SHA = "3" * 64
PERSONA_ROOT_SHA = "4" * 64


def canonical_bytes(value):
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


class PersonaRootLockTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="kio-persona-lock-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()

    def make_owned_root(self, name="replay-root", *, binding_updates=None):
        root = self.base / name
        root.mkdir()
        binding = {
            "schema": "kio.persona.w0.root-binding/v1",
            "schema_version": 1,
            "fixture_id": "kio-persona-pc-v1",
            "profile": "tiny",
            "replay_id": "replay-01",
            "destination_root": str(root),
            "filesystem_device": root.lstat().st_dev,
            "plan_sha256": PLAN_SHA,
            "suite_manifest_sha256": SUITE_SHA,
            "capacity_receipt_sha256": CAPACITY_SHA,
            "persona_manifest_root_sha256": PERSONA_ROOT_SHA,
        }
        if binding_updates:
            binding.update(binding_updates)
        binding_bytes = canonical_bytes(binding)
        binding_sha = hashlib.sha256(binding_bytes).hexdigest()
        marker = storage.make_owner_marker(
            profile="tiny",
            replay_id="replay-01",
            state="ready",
            plan_sha256=PLAN_SHA,
            manifest_sha256=binding_sha,
        )
        (root / storage.OWNER_MARKER_NAME).write_bytes(canonical_bytes(marker))
        (root / "w0-root-binding.json").write_bytes(binding_bytes)
        return root, binding_sha

    def acquire(self, root, binding_sha, **overrides):
        values = {
            "expected_profile": "tiny",
            "expected_replay_id": "replay-01",
            "expected_plan_sha256": PLAN_SHA,
            "expected_root_binding_sha256": binding_sha,
        }
        values.update(overrides)
        return root_lock.replay_root_lock(root, **values)

    def run_contender(self, root, binding_sha):
        script = """
import sys
sys.path.insert(0, sys.argv[1])
import persona_root_lock as lock
try:
    with lock.replay_root_lock(
        sys.argv[2], expected_profile='tiny', expected_replay_id='replay-01',
        expected_plan_sha256=sys.argv[3],
        expected_root_binding_sha256=sys.argv[4],
    ):
        raise SystemExit(9)
except lock.PersonaRootLockError as error:
    if 'contended' not in str(error):
        raise
"""
        return subprocess.run(
            [
                sys.executable,
                "-c",
                script,
                str(Path(__file__).parent),
                str(root),
                PLAN_SHA,
                binding_sha,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )


class TestReplayRootLease(PersonaRootLockTestCase):
    def test_active_root_descriptor_reads_from_held_root_and_is_closed(self):
        root, binding_sha = self.make_owned_root()
        payload = b"read through the lease-held root descriptor\n"
        (root / "payload.txt").write_bytes(payload)
        supplied = None

        with self.acquire(root, binding_sha) as lease:
            with root_lock.active_root_descriptor(lease, root) as descriptor:
                supplied = descriptor
                metadata = os.fstat(descriptor)
                self.assertEqual(
                    (metadata.st_dev, metadata.st_ino, metadata.st_nlink),
                    (lease.root_device, lease.root_inode, root.lstat().st_nlink),
                )
                self.assertFalse(os.get_inheritable(descriptor))
                payload_fd = os.open("payload.txt", os.O_RDONLY, dir_fd=descriptor)
                try:
                    self.assertEqual(os.read(payload_fd, len(payload) + 1), payload)
                finally:
                    os.close(payload_fd)
            with self.assertRaises(OSError):
                os.fstat(supplied)
            self.assertIs(root_lock.require_active_lease(lease, root), lease)

    def test_active_root_descriptor_rejects_expired_wrong_and_foreign_lease(self):
        root, binding_sha = self.make_owned_root()
        with self.acquire(root, binding_sha) as lease:
            with self.assertRaisesRegex(
                root_lock.PersonaRootLockError, "path differs"
            ):
                with root_lock.active_root_descriptor(lease, self.base / "wrong"):
                    self.fail("wrong-root descriptor unexpectedly yielded")
            with self.assertRaisesRegex(
                root_lock.PersonaRootLockError, "invalid replay root lease"
            ):
                with root_lock.active_root_descriptor(object()):
                    self.fail("foreign lease unexpectedly yielded")
        with self.assertRaisesRegex(
            root_lock.PersonaRootLockError, "not active"
        ):
            with root_lock.active_root_descriptor(lease):
                self.fail("expired lease unexpectedly yielded")

    def test_active_root_descriptor_rejects_caller_close(self):
        root, binding_sha = self.make_owned_root()
        with self.acquire(root, binding_sha) as lease:
            with self.assertRaisesRegex(
                root_lock.PersonaRootLockError,
                "not open|closed|cannot close",
            ):
                with root_lock.active_root_descriptor(lease) as descriptor:
                    os.close(descriptor)
            self.assertIs(root_lock.require_active_lease(lease), lease)

    def test_active_root_descriptor_does_not_close_reused_foreign_slot(self):
        root, binding_sha = self.make_owned_root()
        foreign = self.base / "foreign-reuse"
        foreign.mkdir()
        replacement_fd = -1
        with self.acquire(root, binding_sha) as lease:
            try:
                with self.assertRaisesRegex(
                    root_lock.PersonaRootLockError,
                    "closed|changed|identity|rebound",
                ):
                    with root_lock.active_root_descriptor(lease) as descriptor:
                        os.close(descriptor)
                        replacement_fd = os.open(foreign, os.O_RDONLY)
                        self.assertEqual(replacement_fd, descriptor)
                replacement = os.fstat(replacement_fd)
                self.assertEqual(
                    (replacement.st_dev, replacement.st_ino),
                    (foreign.lstat().st_dev, foreign.lstat().st_ino),
                )
            finally:
                if replacement_fd >= 0:
                    os.close(replacement_fd)
            self.assertIs(root_lock.require_active_lease(lease), lease)

    def test_open_description_probe_distinguishes_dup_from_same_inode_open(self):
        root, _binding_sha = self.make_owned_root()
        anchor_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        duplicate_fd = os.dup(anchor_fd)
        fresh_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            self.assertTrue(
                root_lock._shares_open_directory_description(
                    anchor_fd, duplicate_fd
                )
            )
            self.assertFalse(
                root_lock._shares_open_directory_description(
                    anchor_fd, fresh_fd
                )
            )
        finally:
            os.close(fresh_fd)
            os.close(duplicate_fd)
            os.close(anchor_fd)

    def test_active_root_descriptor_rejects_same_inode_reopen_without_closing_it(self):
        root, binding_sha = self.make_owned_root()
        replacement_fd = -1
        with self.acquire(root, binding_sha) as lease:
            try:
                with self.assertRaisesRegex(
                    root_lock.PersonaRootLockError,
                    "rebound|changed|ownership",
                ):
                    with root_lock.active_root_descriptor(lease) as descriptor:
                        os.close(descriptor)
                        replacement_fd = os.open(
                            root, os.O_RDONLY | os.O_DIRECTORY
                        )
                        self.assertEqual(replacement_fd, descriptor)
                replacement = os.fstat(replacement_fd)
                expected = root.lstat()
                self.assertEqual(
                    (replacement.st_dev, replacement.st_ino),
                    (expected.st_dev, expected.st_ino),
                )
            finally:
                if replacement_fd >= 0:
                    os.close(replacement_fd)
            self.assertIs(root_lock.require_active_lease(lease), lease)

    def test_active_root_descriptor_setup_does_not_close_reused_foreign_slot(self):
        root, binding_sha = self.make_owned_root()
        foreign = self.base / "setup-foreign-reuse"
        foreign.mkdir()
        replacement = []

        def replace_before_inheritable_check(descriptor, _inheritable):
            os.close(descriptor)
            replacement.append(
                os.open(foreign, os.O_RDONLY | os.O_DIRECTORY)
            )
            self.assertEqual(replacement[0], descriptor)
            raise OSError("injected setup failure")

        with self.acquire(root, binding_sha) as lease:
            try:
                with mock.patch.object(
                    root_lock.os,
                    "set_inheritable",
                    side_effect=replace_before_inheritable_check,
                ):
                    with self.assertRaisesRegex(
                        root_lock.PersonaRootLockError, "cannot duplicate"
                    ):
                        with root_lock.active_root_descriptor(lease):
                            self.fail("tampered setup unexpectedly yielded")
                observed = os.fstat(replacement[0])
                expected = foreign.lstat()
                self.assertEqual(
                    (observed.st_dev, observed.st_ino),
                    (expected.st_dev, expected.st_ino),
                )
            finally:
                if replacement:
                    os.close(replacement[0])

    def test_active_root_descriptor_rechecks_after_inheritable_query(self):
        root, binding_sha = self.make_owned_root()
        foreign = self.base / "query-foreign-reuse"
        foreign.mkdir()
        replacement = []
        original_get_inheritable = os.get_inheritable
        query_count = 0

        def replace_on_final_query(descriptor):
            nonlocal query_count
            query_count += 1
            if query_count == 1:
                os.close(descriptor)
                replacement.append(
                    os.open(foreign, os.O_RDONLY | os.O_DIRECTORY)
                )
                self.assertEqual(replacement[0], descriptor)
                return False
            return original_get_inheritable(descriptor)

        with self.acquire(root, binding_sha) as lease:
            try:
                with mock.patch.object(
                    root_lock.os,
                    "get_inheritable",
                    side_effect=replace_on_final_query,
                ):
                    with self.assertRaisesRegex(
                        root_lock.PersonaRootLockError,
                        "private non-inheritable duplicate",
                    ):
                        with root_lock.active_root_descriptor(lease):
                            self.fail("reused setup descriptor unexpectedly yielded")
                observed = os.fstat(replacement[0])
                expected = foreign.lstat()
                self.assertEqual(
                    (observed.st_dev, observed.st_ino),
                    (expected.st_dev, expected.st_ino),
                )
            finally:
                if replacement:
                    os.close(replacement[0])

    def test_active_root_descriptor_rejects_caller_rebind(self):
        root, binding_sha = self.make_owned_root()
        foreign = self.base / "foreign"
        foreign.mkdir()
        foreign_fd = os.open(foreign, os.O_RDONLY)
        supplied = None
        try:
            with self.acquire(root, binding_sha) as lease:
                with self.assertRaisesRegex(
                    root_lock.PersonaRootLockError,
                    "identity changed|rebound",
                ):
                    with root_lock.active_root_descriptor(lease) as descriptor:
                        supplied = descriptor
                        os.dup2(foreign_fd, descriptor, inheritable=False)
                supplied_metadata = os.fstat(supplied)
                foreign_metadata = os.fstat(foreign_fd)
                self.assertEqual(
                    (supplied_metadata.st_dev, supplied_metadata.st_ino),
                    (foreign_metadata.st_dev, foreign_metadata.st_ino),
                )
                os.close(supplied)
                supplied = None
                self.assertIs(root_lock.require_active_lease(lease), lease)
        finally:
            if supplied is not None:
                try:
                    os.close(supplied)
                except OSError:
                    pass
            os.close(foreign_fd)

    def test_active_root_descriptor_rejects_inheritable_tamper(self):
        root, binding_sha = self.make_owned_root()
        supplied = None
        with self.acquire(root, binding_sha) as lease:
            with self.assertRaisesRegex(
                root_lock.PersonaRootLockError, "inheritable"
            ):
                with root_lock.active_root_descriptor(lease) as descriptor:
                    supplied = descriptor
                    os.set_inheritable(descriptor, True)
            with self.assertRaises(OSError):
                os.fstat(supplied)
            self.assertIs(root_lock.require_active_lease(lease), lease)

    def test_active_root_descriptor_namespace_swap_overrides_body_failure(self):
        root, binding_sha = self.make_owned_root()
        parked = self.base / "parked"
        with self.acquire(root, binding_sha) as lease:
            try:
                with self.assertRaisesRegex(
                    root_lock.PersonaRootLockError, "root identity changed"
                ) as caught:
                    with root_lock.active_root_descriptor(lease):
                        root.rename(parked)
                        root.mkdir()
                        raise ValueError("body failure")
                self.assertIsInstance(caught.exception.__cause__, ValueError)
            finally:
                if root.exists():
                    root.rmdir()
                if parked.exists():
                    parked.rename(root)
            self.assertIs(root_lock.require_active_lease(lease), lease)

    def test_active_root_descriptor_preserves_clean_body_failure(self):
        root, binding_sha = self.make_owned_root()
        with self.acquire(root, binding_sha) as lease:
            with self.assertRaisesRegex(ValueError, "body failure"):
                with root_lock.active_root_descriptor(lease):
                    raise ValueError("body failure")
            self.assertIs(root_lock.require_active_lease(lease), lease)

    def test_active_root_descriptor_normalizes_stateful_pathlike_once(self):
        root, binding_sha = self.make_owned_root()

        class StatefulPath:
            def __init__(self, value):
                self.value = value
                self.calls = 0

            def __fspath__(self):
                self.calls += 1
                if self.calls > 1:
                    raise RuntimeError("path was evaluated twice")
                return str(self.value)

        expected_root = StatefulPath(root)
        with self.acquire(root, binding_sha) as lease:
            with root_lock.active_root_descriptor(lease, expected_root):
                pass
            self.assertEqual(expected_root.calls, 1)
            self.assertIs(root_lock.require_active_lease(lease), lease)

    def test_success_is_read_only_and_lease_expires(self):
        root, binding_sha = self.make_owned_root()
        marker_path = root / storage.OWNER_MARKER_NAME
        binding_path = root / "w0-root-binding.json"
        before = {
            root: (None, root.lstat()),
            marker_path: (marker_path.read_bytes(), marker_path.lstat()),
            binding_path: (binding_path.read_bytes(), binding_path.lstat()),
        }

        with self.acquire(root, binding_sha) as lease:
            self.assertIs(root_lock.require_active_lease(lease, root), lease)
            self.assertEqual(lease.root, root)
            with self.assertRaisesRegex(
                root_lock.PersonaRootLockError, "path differs"
            ):
                root_lock.require_active_lease(lease, self.base / "other")

        for path, (expected_bytes, expected_stat) in before.items():
            if path == root:
                self.assertTrue(path.is_dir())
            else:
                self.assertEqual(path.read_bytes(), expected_bytes)
            actual = path.lstat()
            self.assertEqual(
                (actual.st_dev, actual.st_ino, actual.st_size, actual.st_mtime_ns),
                (
                    expected_stat.st_dev,
                    expected_stat.st_ino,
                    expected_stat.st_size,
                    expected_stat.st_mtime_ns,
                ),
            )
        with self.assertRaisesRegex(root_lock.PersonaRootLockError, "not active"):
            root_lock.require_active_lease(lease)

    def test_same_process_reentry_is_rejected(self):
        root, binding_sha = self.make_owned_root()
        with self.acquire(root, binding_sha) as lease:
            identity = (lease.root_device, lease.root_inode)
            with self.assertRaisesRegex(
                root_lock.PersonaRootLockError, "already held"
            ):
                with self.acquire(root, binding_sha):
                    self.fail("nested lease unexpectedly succeeded")
            self.assertIn(identity, root_lock._ACTIVE_ROOT_IDENTITIES)
            with self.assertRaisesRegex(
                root_lock.PersonaRootLockError, "already held"
            ):
                with self.acquire(root, binding_sha):
                    self.fail("second nested lease unexpectedly succeeded")

    @unittest.skipIf(os.name == "nt", "POSIX flock contract")
    def test_other_process_contends_on_same_root(self):
        root, binding_sha = self.make_owned_root()
        with self.acquire(root, binding_sha):
            completed = self.run_contender(root, binding_sha)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    @unittest.skipUnless(hasattr(os, "fork"), "fork safety is POSIX-only")
    def test_forked_child_cannot_use_or_unlock_parent_lease(self):
        root, binding_sha = self.make_owned_root()
        read_fd, write_fd = os.pipe()
        pid = None
        child_result = b""
        guard_held = threading.Event()
        release_guard = threading.Event()

        def hold_process_guard():
            with root_lock._PROCESS_GUARD:
                guard_held.set()
                release_guard.wait(10)

        guard_thread = None
        try:
            try:
                with self.acquire(root, binding_sha) as lease:
                    guard_thread = threading.Thread(target=hold_process_guard)
                    guard_thread.start()
                    self.assertTrue(guard_held.wait(5))
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", DeprecationWarning)
                        pid = os.fork()
                    if pid == 0:
                        os.close(read_fd)
                        read_fd = -1
                        child_guard_usable = root_lock._PROCESS_GUARD.acquire(
                            timeout=1
                        )
                        if child_guard_usable:
                            root_lock._PROCESS_GUARD.release()
                        try:
                            root_lock.require_active_lease(lease)
                        except root_lock.PersonaRootLockError as error:
                            if (
                                child_guard_usable
                                and "different process" in str(error)
                            ):
                                child_result = b"lease-rejected"
                            else:
                                child_result = b"wrong-lease-error"
                        else:
                            child_result = b"lease-accepted"
                    else:
                        release_guard.set()
                        guard_thread.join(5)
                        self.assertFalse(guard_thread.is_alive())
                        os.close(write_fd)
                        write_fd = -1
                        ready, _writable, _exceptional = select.select(
                            [read_fd], [], [], 10
                        )
                        self.assertEqual(ready, [read_fd], "fork child timed out")
                        child_result = os.read(read_fd, 4096)
                        self.assertEqual(child_result, b"safe-child-exit")
                        completed = self.run_contender(root, binding_sha)
                        self.assertEqual(
                            completed.returncode, 0, completed.stderr
                        )
            except root_lock.PersonaRootLockError as error:
                if pid != 0:
                    raise
                if (
                    child_result == b"lease-rejected"
                    and "different process" in str(error)
                ):
                    child_result = b"safe-child-exit"
                else:
                    child_result = b"unsafe-child-error"
            if pid == 0:
                os.write(write_fd, child_result)
                os.close(write_fd)
                os._exit(0)
        finally:
            if pid != 0:
                release_guard.set()
                if guard_thread is not None:
                    guard_thread.join(5)
                if read_fd >= 0:
                    os.close(read_fd)
                if write_fd >= 0:
                    os.close(write_fd)
                if pid is not None:
                    waited, status = os.waitpid(pid, 0)
                    self.assertEqual(waited, pid)
                    self.assertEqual(status, 0)

    def test_wrong_expected_bindings_are_rejected(self):
        root, binding_sha = self.make_owned_root()
        cases = (
            {"expected_profile": "pilot"},
            {"expected_replay_id": "replay-02"},
            {"expected_plan_sha256": "a" * 64},
            {"expected_root_binding_sha256": "b" * 64},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides), self.assertRaises(
                root_lock.PersonaRootLockError
            ):
                with self.acquire(root, binding_sha, **overrides):
                    self.fail("mismatched lease unexpectedly succeeded")

    def test_binding_schema_and_canonical_form_are_enforced(self):
        invalid_cases = (
            {"schema": "kio.persona.w0.root-binding/v2"},
            {"schema_version": True},
            {"fixture_id": "foreign-fixture"},
            {"suite_manifest_sha256": "not-a-digest"},
            {"unexpected": "field"},
        )
        for index, updates in enumerate(invalid_cases):
            root, binding_sha = self.make_owned_root(
                f"invalid-{index}", binding_updates=updates
            )
            with self.subTest(updates=updates), self.assertRaises(
                root_lock.PersonaRootLockError
            ):
                with self.acquire(root, binding_sha):
                    self.fail("invalid root binding unexpectedly succeeded")

        root, _binding_sha = self.make_owned_root("noncanonical")
        binding_path = root / "w0-root-binding.json"
        value = json.loads(binding_path.read_bytes())
        noncanonical = json.dumps(value, sort_keys=True).encode("utf-8")
        binding_path.write_bytes(noncanonical)
        binding_sha = hashlib.sha256(noncanonical).hexdigest()
        marker = storage.make_owner_marker(
            profile="tiny", replay_id="replay-01", state="ready",
            plan_sha256=PLAN_SHA, manifest_sha256=binding_sha,
        )
        (root / storage.OWNER_MARKER_NAME).write_bytes(canonical_bytes(marker))
        with self.assertRaisesRegex(
            root_lock.PersonaRootLockError, "canonical JSON"
        ):
            with self.acquire(root, binding_sha):
                self.fail("noncanonical root binding unexpectedly succeeded")

    def test_self_consistent_binding_semantic_mismatches_are_rejected(self):
        cases = (
            {"destination_root": str(self.base / "different-root")},
            {"filesystem_device": self.base.lstat().st_dev + 1},
            {"profile": "pilot"},
            {"replay_id": "replay-02"},
            {"plan_sha256": "a" * 64},
        )
        for index, updates in enumerate(cases):
            root, binding_sha = self.make_owned_root(
                f"semantic-{index}", binding_updates=updates
            )
            with self.subTest(updates=updates), self.assertRaisesRegex(
                root_lock.PersonaRootLockError, "does not bind this root"
            ):
                with self.acquire(root, binding_sha):
                    self.fail("semantically wrong binding unexpectedly succeeded")

    def test_symlink_and_hardlink_control_files_are_rejected(self):
        for filename in (storage.OWNER_MARKER_NAME, "w0-root-binding.json"):
            root, binding_sha = self.make_owned_root(f"hardlink-{filename[0]}")
            path = root / filename
            alias = root / f"{filename}.alias"
            try:
                os.link(path, alias)
            except OSError as error:  # pragma: no cover - filesystem policy.
                self.skipTest(f"hard links unavailable: {error}")
            with self.subTest(kind="hardlink", filename=filename), self.assertRaises(
                root_lock.PersonaRootLockError
            ):
                with self.acquire(root, binding_sha):
                    self.fail("hard-linked control file unexpectedly succeeded")

            root, binding_sha = self.make_owned_root(f"symlink-{filename[0]}")
            path = root / filename
            target = root / f"{filename}.target"
            path.rename(target)
            try:
                path.symlink_to(target.name)
            except OSError as error:  # pragma: no cover - platform policy.
                self.skipTest(f"symlinks unavailable: {error}")
            with self.subTest(kind="symlink", filename=filename), self.assertRaises(
                root_lock.PersonaRootLockError
            ):
                with self.acquire(root, binding_sha):
                    self.fail("symlinked control file unexpectedly succeeded")

    def test_release_detects_control_file_replacement_without_rewriting_it(self):
        root, binding_sha = self.make_owned_root()
        binding_path = root / "w0-root-binding.json"
        original = binding_path.read_bytes()
        with self.assertRaisesRegex(
            root_lock.PersonaRootLockError,
            "single-link file|namespace identity changed",
        ):
            with self.acquire(root, binding_sha):
                binding_path.unlink()
                binding_path.write_bytes(original)
                foreign_stat = binding_path.lstat()
        self.assertEqual(binding_path.read_bytes(), original)
        self.assertEqual(binding_path.lstat().st_ino, foreign_stat.st_ino)

    def test_release_detects_owner_replacement_and_in_place_tamper(self):
        for action in ("replace", "rewrite"):
            root, binding_sha = self.make_owned_root(f"owner-{action}")
            marker_path = root / storage.OWNER_MARKER_NAME
            original = marker_path.read_bytes()
            with self.subTest(action=action), self.assertRaises(
                root_lock.PersonaRootLockError
            ):
                with self.acquire(root, binding_sha):
                    if action == "replace":
                        marker_path.unlink()
                        marker_path.write_bytes(original)
                    else:
                        marker_path.write_bytes(b"{}\n")
                    changed = marker_path.read_bytes()
            self.assertEqual(marker_path.read_bytes(), changed)

    @unittest.skipIf(os.name == "nt", "POSIX flock contract")
    def test_each_lock_carrier_independently_causes_contention(self):
        import fcntl

        root, binding_sha = self.make_owned_root()
        carriers = (root, root / storage.OWNER_MARKER_NAME)
        for carrier in carriers:
            descriptor = os.open(carrier, os.O_RDONLY)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.subTest(carrier=carrier), self.assertRaisesRegex(
                    root_lock.PersonaRootLockError, "contended"
                ):
                    with self.acquire(root, binding_sha):
                        self.fail("carrier contention unexpectedly succeeded")
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                os.close(descriptor)
            with self.acquire(root, binding_sha):
                pass

    def test_release_detects_root_path_replacement_without_touching_foreign_root(self):
        root, binding_sha = self.make_owned_root()
        parked = self.base / "parked-root"
        foreign_payload = b"foreign root must remain unchanged\n"
        with self.assertRaisesRegex(
            root_lock.PersonaRootLockError, "root identity changed"
        ):
            with self.acquire(root, binding_sha):
                root.rename(parked)
                root.mkdir()
                (root / "foreign.txt").write_bytes(foreign_payload)
                foreign_stat = (root / "foreign.txt").lstat()
        self.assertEqual((root / "foreign.txt").read_bytes(), foreign_payload)
        self.assertEqual((root / "foreign.txt").lstat().st_ino, foreign_stat.st_ino)

    def test_windows_is_fail_closed_before_filesystem_access(self):
        root, binding_sha = self.make_owned_root()
        with mock.patch.object(root_lock.os, "name", "nt"):
            with self.assertRaisesRegex(
                root_lock.PersonaRootLockError, "unavailable on Windows"
            ):
                with self.acquire(root, binding_sha):
                    self.fail("Windows lease unexpectedly succeeded")

    def test_missing_descriptor_flags_fail_closed(self):
        for name in ("O_CLOEXEC", "O_NOFOLLOW", "O_DIRECTORY"):
            with self.subTest(name=name), mock.patch.object(
                root_lock.os, name, None
            ), self.assertRaisesRegex(
                root_lock.PersonaRootLockError, name
            ):
                root_lock._open_flags(directory=True)

    def test_close_failure_does_not_skip_remaining_cleanup(self):
        root, binding_sha = self.make_owned_root()
        real_close = os.close
        failed = False

        def close_then_report(descriptor):
            nonlocal failed
            real_close(descriptor)
            if not failed:
                failed = True
                raise OSError(5, "injected close failure")

        with self.assertRaisesRegex(
            root_lock.PersonaRootLockError, "cannot close"
        ):
            with mock.patch.object(
                root_lock.os, "close", side_effect=close_then_report
            ):
                with self.acquire(root, binding_sha):
                    pass
        self.assertFalse(root_lock._ACTIVE_ROOT_IDENTITIES)
        with self.acquire(root, binding_sha):
            pass


if __name__ == "__main__":
    unittest.main()
