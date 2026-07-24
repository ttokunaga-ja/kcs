#!/usr/bin/env python3
"""Read-only tests for persona W0 runtime attestation primitives."""

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
import unicodedata
from unittest import mock

from eval import generate_persona_corpus as generator
from eval import persona_fixture_spec as fixture_spec
from eval import persona_history_attestation as attestation
from eval import persona_root_lock as root_lock
from eval import persona_storage as storage


def _semantic_evidence(
    kind,
    *,
    profile,
    persona_id,
    relative_path,
    content,
    scope_key=None,
    chunk_arithmetic=None,
):
    schema = (
        generator.RUNTIME_SCOPE_STORE_SEMANTIC_CONTRACT
        if kind == "scope_store"
        else generator.RUNTIME_DEVICE_STATE_SEMANTIC_CONTRACT
    )
    return attestation.KioSemanticEvidence(
        schema=attestation.KIO_SEMANTIC_EVIDENCE_SCHEMA,
        schema_version=1,
        kind=kind,
        attestor_schema=schema,
        profile=profile,
        persona_id=persona_id,
        scope_key=scope_key,
        relative_path=relative_path,
        content_root_sha256=content.content_root_sha256,
        chunk_arithmetic=chunk_arithmetic,
        semantics_attested=True,
    )


def _valid_arithmetic(target=7, incidental=3):
    return attestation.validate_chunk_arithmetic({
        "expected_contract_contributor_chunks": target,
        "contract_contributor_chunks": target,
        "incidental_searchable_chunks": incidental,
        "raw_only_chunks": 0,
        "all_current_eligible_chunks": target + incidental,
    })


def _scope_contract(persona_id="p01", profile="tiny", ordinal=0):
    persona = fixture_spec.get_persona(persona_id)
    scope = fixture_spec.scope_specs(persona)[ordinal]
    relative = (
        f"devices/{persona_id}-{persona['role']}/home/{scope['relative_path']}/.kio"
    )
    target = fixture_spec.scope_contributor_chunk_targets(
        persona, profile
    )[scope["scope_key"]]
    return scope["scope_key"], relative, _valid_arithmetic(target, 0)


def _write_owned_root_controls(root):
    plan_sha256 = "a" * 64
    binding = {
        "schema": generator.ROOT_BINDING_SCHEMA,
        "schema_version": 1,
        "fixture_id": fixture_spec.FIXTURE_ID,
        "profile": "tiny",
        "replay_id": "replay-01",
        "destination_root": str(root),
        "filesystem_device": root.lstat().st_dev,
        "plan_sha256": plan_sha256,
        "suite_manifest_sha256": "b" * 64,
        "capacity_receipt_sha256": "c" * 64,
        "persona_manifest_root_sha256": "d" * 64,
    }
    binding_bytes = (
        json.dumps(binding, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    binding_sha256 = hashlib.sha256(binding_bytes).hexdigest()
    owner = storage.make_owner_marker(
        profile="tiny",
        replay_id="replay-01",
        state="ready",
        plan_sha256=plan_sha256,
        manifest_sha256=binding_sha256,
    )
    owner_bytes = (
        json.dumps(owner, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    (root / storage.OWNER_MARKER_NAME).write_bytes(owner_bytes)
    (root / "w0-root-binding.json").write_bytes(binding_bytes)
    return plan_sha256, binding_sha256


class TestBoundedContentRoot(unittest.TestCase):
    def test_root_is_location_and_timestamp_independent_but_binds_tree_bytes(self):
        with tempfile.TemporaryDirectory(prefix="kio-attest-a-") as first_tmp, \
                tempfile.TemporaryDirectory(prefix="kio-attest-b-") as second_tmp:
            first = Path(first_tmp) / ".kio"
            second = Path(second_tmp) / ".kio"
            for root in (first, second):
                (root / "objects" / "aa").mkdir(parents=True)
                (root / "empty").mkdir()
                (root / "HEAD").write_bytes(b"sha256:" + b"1" * 64 + b"\n")
                (root / "objects" / "aa" / "object").write_bytes(b"payload")
            os.utime(second / "HEAD", ns=(1_000_000_000, 2_000_000_000))
            left = attestation.walk_directory_content_root(first)
            right = attestation.walk_directory_content_root(second)
            self.assertEqual(left.content_root_sha256, right.content_root_sha256)
            self.assertNotEqual(left.directory_inode, right.directory_inode)
            self.assertEqual(left.descendant_directories, 3)
            self.assertEqual(left.regular_files, 2)
            self.assertEqual(left.maximum_depth, 3)
            self.assertEqual(left.coverage, attestation.FILESYSTEM_COVERAGE)
            (second / "HEAD").write_bytes(b"sha256:" + b"2" * 64 + b"\n")
            changed = attestation.walk_directory_content_root(second)
            self.assertNotEqual(left.content_root_sha256, changed.content_root_sha256)

    @unittest.skipIf(os.name == "nt", "POSIX link/special semantics")
    def test_links_specials_noncanonical_names_and_collisions_fail_closed(self):
        builders = {
            "symlink": lambda root: (root / "link").symlink_to("target"),
            "hardlink": lambda root: (
                (root / "one").write_bytes(b"same"),
                os.link(root / "one", root / "two"),
            ),
            "fifo": lambda root: os.mkfifo(root / "pipe"),
            "case_collision": lambda root: (
                (root / "Name").write_bytes(b"a"),
                (root / "name").write_bytes(b"b"),
            ),
            "unicode_casefold_collision": lambda root: (
                (root / "Stra\u00dfe").write_bytes(b"a"),
                (root / "STRASSE").write_bytes(b"b"),
            ),
            "nfd": lambda root: (
                root / unicodedata.normalize("NFD", "café")
            ).write_bytes(b"x"),
            "c0": lambda root: (root / "bad\x01name").write_bytes(b"x"),
            "c1": lambda root: (root / "bad\u0085name").write_bytes(b"x"),
            "cf": lambda root: (root / "bad\u200bname").write_bytes(b"x"),
        }
        for label, build in builders.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / ".kio"
                root.mkdir()
                if label == "symlink":
                    (root / "target").write_bytes(b"x")
                build(root)
                if label in (
                    "case_collision", "unicode_casefold_collision"
                ) and len(tuple(root.iterdir())) < 2:
                    # The default macOS filesystem collapses these names; the
                    # collision guard is exercised on case-sensitive CI.
                    continue
                with self.assertRaises(attestation.PersonaHistoryAttestationError):
                    attestation.walk_directory_content_root(root)

    def test_merkle_walk_does_not_materialize_whole_tree_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / ".kio"
            root.mkdir()
            for index in range(100):
                (root / f"entry-{index:03d}").write_bytes(str(index).encode())
            with mock.patch.object(
                attestation.json,
                "dumps",
                side_effect=AssertionError("whole-tree JSON was materialized"),
            ):
                result = attestation.walk_directory_content_root(root)
            self.assertEqual(result.regular_files, 100)
            self.assertEqual(result.schema, attestation.CONTENT_ROOT_SCHEMA)

    def test_entry_byte_and_depth_limits_are_enforced(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / ".kio"
            (root / "one" / "two").mkdir(parents=True)
            (root / "one" / "two" / "value").write_bytes(b"12345")
            cases = (
                replace(
                    attestation.DEFAULT_LIMITS,
                    max_entries=2,
                    max_files=1,
                    max_directories=2,
                ),
                replace(
                    attestation.DEFAULT_LIMITS,
                    max_total_file_bytes=4,
                    max_file_bytes=4,
                ),
                replace(attestation.DEFAULT_LIMITS, max_depth=2),
            )
            for limits in cases:
                with self.subTest(limits=limits), self.assertRaises(
                    attestation.PersonaHistoryAttestationError
                ):
                    attestation.walk_directory_content_root(root, limits=limits)

    def test_direct_entry_limit_accepts_exact_cap_and_rejects_next_entry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / ".kio"
            root.mkdir()
            limits = replace(
                attestation.DEFAULT_LIMITS,
                max_entries=5,
                max_direct_entries=4,
                max_files=5,
                max_directories=1,
            )
            for index in range(4):
                (root / f"portable-{index}").write_bytes(b"value")
            exact = attestation.walk_directory_content_root(root, limits=limits)
            self.assertEqual(exact.regular_files, 4)

            (root / "portable-overflow").write_bytes(b"value")
            with self.assertRaisesRegex(
                attestation.PersonaHistoryAttestationError,
                "direct-entry bound",
            ):
                attestation.walk_directory_content_root(root, limits=limits)

    def test_invalid_limits_reject_bool_and_inconsistent_bounds(self):
        with self.assertRaises(attestation.PersonaHistoryAttestationError):
            attestation.AttestationLimits(max_entries=True)
        with self.assertRaises(attestation.PersonaHistoryAttestationError):
            attestation.AttestationLimits(max_entries=1)
        with self.assertRaisesRegex(
            attestation.PersonaHistoryAttestationError,
            "hard cap",
        ):
            attestation.AttestationLimits(
                max_entries=attestation.HARD_MAX_ENTRIES + 1,
                max_files=attestation.HARD_MAX_FILES,
                max_directories=attestation.HARD_MAX_DIRECTORIES,
            )
        with self.assertRaisesRegex(
            attestation.PersonaHistoryAttestationError,
            "hard cap",
        ):
            attestation.AttestationLimits(
                max_direct_entries=attestation.HARD_MAX_DIRECT_ENTRIES + 1,
            )

    @unittest.skipIf(os.name == "nt", "POSIX descriptor semantics")
    def test_concurrent_growth_never_reads_beyond_the_preopened_size(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "bounded"
            path.write_bytes(b"1234")
            expected = path.lstat()
            parent_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            read_sizes = []
            original_read = os.read
            grown = False

            def grow_then_read(descriptor, size):
                nonlocal grown
                read_sizes.append(size)
                if not grown:
                    grown = True
                    path.write_bytes(b"x" * 512)
                return original_read(descriptor, size)

            try:
                with mock.patch.object(
                    attestation.os,
                    "read",
                    side_effect=grow_then_read,
                ), self.assertRaisesRegex(
                    attestation.PersonaHistoryAttestationError,
                    "changed while reading",
                ):
                    attestation._read_regular_file(
                        parent_fd,
                        path.name,
                        expected,
                        replace(
                            attestation.DEFAULT_LIMITS,
                            max_file_bytes=4,
                        ),
                    )
            finally:
                os.close(parent_fd)
            self.assertEqual(read_sizes, [4])

    @unittest.skipIf(os.name == "nt", "POSIX safe-open flags")
    def test_missing_safe_open_flags_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / ".kio"
            root.mkdir()
            (root / "file").write_bytes(b"value")
            for flag in (
                "O_NOFOLLOW",
                "O_CLOEXEC",
                "O_DIRECTORY",
                "O_NONBLOCK",
            ):
                with self.subTest(flag=flag), mock.patch.object(
                    attestation.os, flag, 0
                ), self.assertRaisesRegex(
                    attestation.PersonaHistoryAttestationError,
                    "required safe-open flag",
                ):
                    attestation.walk_directory_content_root(root)

    @unittest.skipIf(os.name == "nt", "POSIX descriptor semantics")
    def test_root_descriptor_is_closed_when_post_open_fstat_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / ".kio"
            root.mkdir()
            closed = []
            real_close = os.close

            def recording_close(descriptor):
                closed.append(descriptor)
                real_close(descriptor)

            with mock.patch.object(
                attestation.os,
                "fstat",
                side_effect=OSError("injected fstat failure"),
            ), mock.patch.object(
                attestation.os,
                "close",
                side_effect=recording_close,
            ), self.assertRaises(attestation.PersonaHistoryAttestationError):
                attestation.walk_directory_content_root(root)
            self.assertEqual(len(closed), 1)

    @unittest.skipIf(os.name == "nt", "POSIX descriptor semantics")
    def test_root_descriptor_is_closed_on_base_exception(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / ".kio"
            root.mkdir()
            captured = []
            original_open = os.open

            def capture_open(*arguments, **keywords):
                descriptor = original_open(*arguments, **keywords)
                captured.append(descriptor)
                return descriptor

            with mock.patch.object(
                attestation.os,
                "open",
                side_effect=capture_open,
            ), mock.patch.object(
                attestation,
                "_require_noninheritable",
                side_effect=KeyboardInterrupt("injected root interruption"),
            ), self.assertRaisesRegex(
                KeyboardInterrupt, "injected root interruption"
            ):
                attestation._open_root_directory(root)
            self.assertEqual(len(captured), 1)
            with self.assertRaises(OSError):
                os.fstat(captured[0])


class TestRuntimeCallbackReceipt(unittest.TestCase):
    def test_path_checker_observation_cannot_enter_callback_protocol(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            scope_key, relative, arithmetic = _scope_contract()
            runtime = root / relative
            runtime.mkdir(parents=True)
            (runtime / "HEAD").write_bytes(b"head")
            descriptor = {"kind": "scope_store", "relative_path": relative}

            def checker(_path, observed_descriptor, content):
                self.assertEqual(observed_descriptor, descriptor)
                self.assertEqual(content.regular_files, 1)
                return _semantic_evidence(
                    "scope_store",
                    profile="tiny",
                    persona_id="p01",
                    scope_key=scope_key,
                    relative_path=relative,
                    content=content,
                    chunk_arithmetic=arithmetic,
                )

            receipt = attestation.build_runtime_directory_receipt(
                runtime,
                descriptor,
                trusted_root=root,
                semantic_checker=checker,
            )
            self.assertEqual(receipt.relative_path, relative)
            self.assertFalse(receipt.formal_transport_attested)
            with self.assertRaisesRegex(
                attestation.PersonaHistoryAttestationError,
                "cannot enter the callback protocol",
            ):
                receipt.to_callback_dict()
            with self.assertRaisesRegex(
                attestation.PersonaHistoryAttestationError,
                "cannot enter the callback protocol",
            ):
                attestation.make_runtime_attestor(checker, trusted_root=root)

    @unittest.skipIf(os.name == "nt", "POSIX descriptor semantics")
    def test_handle_bound_checker_reads_the_held_runtime_inode(self):
        with tempfile.TemporaryDirectory() as temporary:
            trusted = Path(temporary).resolve()
            scope_key, relative, arithmetic = _scope_contract()
            runtime = trusted / relative
            runtime.mkdir(parents=True)
            (runtime / "HEAD").write_bytes(b"held-head")
            descriptor = {"kind": "scope_store", "relative_path": relative}

            def checker(bound, observed_descriptor, content):
                self.assertIsInstance(
                    bound, attestation.BoundRuntimeDirectory
                )
                self.assertEqual(observed_descriptor, descriptor)
                self.assertEqual(bound.path, runtime)
                self.assertEqual(bound.relative_path, relative)
                self.assertFalse(os.get_inheritable(bound.directory_fd))
                descriptor_fd = os.open(
                    "HEAD",
                    os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                    dir_fd=bound.directory_fd,
                )
                try:
                    self.assertEqual(os.read(descriptor_fd, 64), b"held-head")
                finally:
                    os.close(descriptor_fd)
                return _semantic_evidence(
                    "scope_store",
                    profile="tiny",
                    persona_id="p01",
                    scope_key=scope_key,
                    relative_path=relative,
                    content=content,
                    chunk_arithmetic=arithmetic,
                )

            receipt = attestation.build_handle_bound_runtime_directory_receipt(
                runtime,
                descriptor,
                trusted_root=trusted,
                semantic_checker=checker,
            )
            self.assertEqual(receipt.relative_path, relative)
            self.assertFalse(receipt.formal_transport_attested)
            self.assertEqual(
                receipt.content_root_sha256,
                attestation.walk_directory_content_root(runtime).content_root_sha256,
            )
            with self.assertRaisesRegex(
                attestation.PersonaHistoryAttestationError,
                "cannot enter the callback protocol",
            ):
                attestation.make_handle_bound_runtime_attestor(
                    checker,
                    trusted_root=trusted,
                )

    @unittest.skipIf(os.name == "nt", "POSIX descriptor semantics")
    def test_lease_bound_checker_never_reopens_the_trusted_root_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            trusted = Path(temporary).resolve() / "replay-root"
            trusted.mkdir()
            plan_sha256, binding_sha256 = _write_owned_root_controls(trusted)
            scope_key, relative, arithmetic = _scope_contract()
            runtime = trusted / relative
            runtime.mkdir(parents=True)
            (runtime / "HEAD").write_bytes(b"lease-held-head")
            descriptor = {"kind": "scope_store", "relative_path": relative}

            def checker(bound, _observed_descriptor, content):
                head_fd = os.open(
                    "HEAD",
                    os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                    dir_fd=bound.directory_fd,
                )
                try:
                    self.assertEqual(
                        os.read(head_fd, 64), b"lease-held-head"
                    )
                finally:
                    os.close(head_fd)
                return _semantic_evidence(
                    "scope_store",
                    profile="tiny",
                    persona_id="p01",
                    scope_key=scope_key,
                    relative_path=relative,
                    content=content,
                    chunk_arithmetic=arithmetic,
                )

            with root_lock.replay_root_lock(
                trusted,
                expected_profile="tiny",
                expected_replay_id="replay-01",
                expected_plan_sha256=plan_sha256,
                expected_root_binding_sha256=binding_sha256,
            ) as lease:
                with mock.patch.object(
                    attestation,
                    "_open_root_directory",
                    side_effect=AssertionError("trusted path was reopened"),
                ):
                    receipt = (
                        attestation.build_lease_bound_runtime_directory_receipt(
                            runtime,
                            descriptor,
                            lease=lease,
                            semantic_checker=checker,
                        )
                    )
                self.assertEqual(receipt.relative_path, relative)
                self.assertFalse(receipt.formal_transport_attested)
                self.assertFalse(
                    attestation.HANDLE_BOUND_SEMANTIC_TRANSPORT_FORMAL
                )
                with self.assertRaisesRegex(
                    attestation.PersonaHistoryAttestationError,
                    "cannot enter the callback protocol",
                ):
                    attestation.make_lease_bound_runtime_attestor(
                        checker,
                        lease=lease,
                    )

            with self.assertRaisesRegex(
                attestation.PersonaHistoryAttestationError,
                "active replay-root lease",
            ):
                attestation.build_lease_bound_runtime_directory_receipt(
                    runtime,
                    descriptor,
                    lease=lease,
                    semantic_checker=checker,
                )

    @unittest.skipIf(os.name == "nt", "POSIX descriptor semantics")
    def test_cleanup_attempts_trusted_close_after_target_close_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            trusted = Path(temporary).resolve()
            scope_key, relative, arithmetic = _scope_contract()
            runtime = trusted / relative
            runtime.mkdir(parents=True)
            descriptor = {"kind": "scope_store", "relative_path": relative}
            root_fds = []
            target_fds = []
            close_calls = []
            injected = False
            original_open_root = attestation._open_root_directory
            original_open_relative = attestation._open_relative_directory
            original_close = os.close

            def capture_root(path):
                result = original_open_root(path)
                root_fds.append(result[0])
                return result

            def capture_relative(*arguments, **keywords):
                result = original_open_relative(*arguments, **keywords)
                target_fds.append(result[0])
                return result

            def fail_first_target_close(fd):
                nonlocal injected
                close_calls.append(fd)
                if target_fds and fd == target_fds[0] and not injected:
                    injected = True
                    original_close(fd)
                    raise OSError("injected target close failure")
                return original_close(fd)

            def checker(_bound, _observed_descriptor, content):
                return _semantic_evidence(
                    "scope_store",
                    profile="tiny",
                    persona_id="p01",
                    scope_key=scope_key,
                    relative_path=relative,
                    content=content,
                    chunk_arithmetic=arithmetic,
                )

            with mock.patch.object(
                attestation,
                "_open_root_directory",
                side_effect=capture_root,
            ), mock.patch.object(
                attestation,
                "_open_relative_directory",
                side_effect=capture_relative,
            ), mock.patch.object(
                attestation.os,
                "close",
                side_effect=fail_first_target_close,
            ), self.assertRaisesRegex(
                attestation.PersonaHistoryAttestationError,
                "cannot close owned contained runtime root",
            ):
                attestation.build_handle_bound_runtime_directory_receipt(
                    runtime,
                    descriptor,
                    trusted_root=trusted,
                    semantic_checker=checker,
                )
            self.assertTrue(injected)
            self.assertIn(root_fds[0], close_calls)
            with self.assertRaises(OSError):
                os.fstat(root_fds[0])

    @unittest.skipIf(os.name == "nt", "POSIX descriptor semantics")
    def test_relative_directory_walk_closes_all_fds_on_base_exception(self):
        with tempfile.TemporaryDirectory() as temporary:
            trusted = Path(temporary).resolve()
            (trusted / "child").mkdir()
            trusted_fd = os.open(trusted, os.O_RDONLY | os.O_DIRECTORY)
            trusted_metadata = os.fstat(trusted_fd)
            captured = []
            original_dup = os.dup
            original_open = os.open
            original_require = attestation._require_noninheritable

            def capture_dup(descriptor):
                result = original_dup(descriptor)
                captured.append(result)
                return result

            def capture_open(*arguments, **keywords):
                result = original_open(*arguments, **keywords)
                captured.append(result)
                return result

            def interrupt_child(descriptor, label):
                if label == "contained runtime directory":
                    raise KeyboardInterrupt("injected traversal interruption")
                return original_require(descriptor, label)

            try:
                with mock.patch.object(
                    attestation.os, "dup", side_effect=capture_dup
                ), mock.patch.object(
                    attestation.os, "open", side_effect=capture_open
                ), mock.patch.object(
                    attestation,
                    "_require_noninheritable",
                    side_effect=interrupt_child,
                ):
                    with self.assertRaisesRegex(
                        KeyboardInterrupt, "injected traversal interruption"
                    ):
                        attestation._open_relative_directory(
                            trusted_fd,
                            ("child",),
                            trusted_metadata.st_dev,
                        )
                self.assertEqual(len(captured), 2)
                for descriptor in captured:
                    with self.assertRaises(OSError):
                        os.fstat(descriptor)
            finally:
                os.close(trusted_fd)

    @unittest.skipIf(os.name == "nt", "POSIX descriptor semantics")
    def test_relative_directory_walk_closes_child_when_parent_close_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            trusted = Path(temporary).resolve()
            (trusted / "child").mkdir()
            trusted_fd = os.open(trusted, os.O_RDONLY | os.O_DIRECTORY)
            trusted_metadata = os.fstat(trusted_fd)
            captured = []
            original_dup = os.dup
            original_open = os.open
            original_close = os.close
            injected = False

            def capture_dup(descriptor):
                result = original_dup(descriptor)
                captured.append(result)
                return result

            def capture_open(*arguments, **keywords):
                result = original_open(*arguments, **keywords)
                captured.append(result)
                return result

            def fail_first_parent_close(descriptor):
                nonlocal injected
                if captured and descriptor == captured[0] and not injected:
                    injected = True
                    raise OSError("injected parent close failure")
                return original_close(descriptor)

            try:
                with mock.patch.object(
                    attestation.os, "dup", side_effect=capture_dup
                ), mock.patch.object(
                    attestation.os, "open", side_effect=capture_open
                ), mock.patch.object(
                    attestation.os,
                    "close",
                    side_effect=fail_first_parent_close,
                ):
                    with self.assertRaisesRegex(
                        OSError, "injected parent close failure"
                    ):
                        attestation._open_relative_directory(
                            trusted_fd,
                            ("child",),
                            trusted_metadata.st_dev,
                        )
                self.assertTrue(injected)
                self.assertEqual(len(captured), 2)
                for descriptor in captured:
                    with self.assertRaises(OSError):
                        os.fstat(descriptor)
            finally:
                os.close(trusted_fd)

    @unittest.skipIf(os.name == "nt", "POSIX descriptor semantics")
    def test_checker_setup_does_not_close_reused_foreign_fd_slot(self):
        with tempfile.TemporaryDirectory() as temporary:
            trusted = Path(temporary).resolve()
            _scope_key, relative, _arithmetic = _scope_contract()
            runtime = trusted / relative
            runtime.mkdir(parents=True)
            outside = trusted / "setup-outside-reuse"
            outside.mkdir()
            descriptor = {"kind": "scope_store", "relative_path": relative}
            replacement = []
            original_require = attestation._require_noninheritable

            def replace_checker_slot(candidate_fd, label):
                if label != "semantic checker runtime":
                    return original_require(candidate_fd, label)
                os.close(candidate_fd)
                replacement.append(
                    os.open(outside, os.O_RDONLY | os.O_DIRECTORY)
                )
                self.assertEqual(replacement[0], candidate_fd)
                raise attestation.PersonaHistoryAttestationError(
                    "injected checker setup failure"
                )

            try:
                with mock.patch.object(
                    attestation,
                    "_require_noninheritable",
                    side_effect=replace_checker_slot,
                ):
                    with self.assertRaisesRegex(
                        attestation.PersonaHistoryAttestationError,
                        "injected checker setup failure",
                    ):
                        attestation.build_handle_bound_runtime_directory_receipt(
                            runtime,
                            descriptor,
                            trusted_root=trusted,
                            semantic_checker=lambda *_arguments: self.fail(
                                "checker unexpectedly ran"
                            ),
                        )
                observed = os.fstat(replacement[0])
                expected = outside.lstat()
                self.assertEqual(
                    (observed.st_dev, observed.st_ino),
                    (expected.st_dev, expected.st_ino),
                )
            finally:
                if replacement:
                    os.close(replacement[0])

    @unittest.skipIf(os.name == "nt", "POSIX descriptor semantics")
    def test_checker_setup_rechecks_after_constructor_inheritable_query(self):
        with tempfile.TemporaryDirectory() as temporary:
            trusted = Path(temporary).resolve()
            _scope_key, relative, _arithmetic = _scope_contract()
            runtime = trusted / relative
            runtime.mkdir(parents=True)
            outside = trusted / "post-constructor-outside-reuse"
            outside.mkdir()
            descriptor = {"kind": "scope_store", "relative_path": relative}
            replacement = []
            original_require = attestation._require_noninheritable
            semantic_queries = 0

            def replace_on_constructor_query(candidate_fd, label):
                nonlocal semantic_queries
                if label != "semantic checker runtime":
                    return original_require(candidate_fd, label)
                semantic_queries += 1
                if semantic_queries == 1:
                    return original_require(candidate_fd, label)
                os.close(candidate_fd)
                replacement.append(
                    os.open(outside, os.O_RDONLY | os.O_DIRECTORY)
                )
                self.assertEqual(replacement[0], candidate_fd)
                return None

            try:
                with mock.patch.object(
                    attestation,
                    "_require_noninheritable",
                    side_effect=replace_on_constructor_query,
                ):
                    with self.assertRaisesRegex(
                        attestation.PersonaHistoryAttestationError,
                        "changed during setup",
                    ):
                        attestation.build_handle_bound_runtime_directory_receipt(
                            runtime,
                            descriptor,
                            trusted_root=trusted,
                            semantic_checker=lambda *_arguments: self.fail(
                                "checker unexpectedly ran"
                            ),
                        )
                observed = os.fstat(replacement[0])
                expected = outside.lstat()
                self.assertEqual(
                    (observed.st_dev, observed.st_ino),
                    (expected.st_dev, expected.st_ino),
                )
            finally:
                if replacement:
                    os.close(replacement[0])

    @unittest.skipIf(os.name == "nt", "POSIX descriptor semantics")
    def test_checker_constructor_failure_does_not_close_reused_foreign_slot(self):
        with tempfile.TemporaryDirectory() as temporary:
            trusted = Path(temporary).resolve()
            _scope_key, relative, _arithmetic = _scope_contract()
            runtime = trusted / relative
            runtime.mkdir(parents=True)
            outside = trusted / "constructor-outside-reuse"
            outside.mkdir()
            descriptor = {"kind": "scope_store", "relative_path": relative}
            replacement = []

            def replace_during_construction(**keywords):
                candidate_fd = keywords["directory_fd"]
                os.close(candidate_fd)
                replacement.append(
                    os.open(outside, os.O_RDONLY | os.O_DIRECTORY)
                )
                self.assertEqual(replacement[0], candidate_fd)
                raise RuntimeError("injected bound-directory construction failure")

            try:
                with mock.patch.object(
                    attestation,
                    "BoundRuntimeDirectory",
                    side_effect=replace_during_construction,
                ):
                    with self.assertRaisesRegex(
                        RuntimeError, "injected bound-directory construction failure"
                    ):
                        attestation.build_handle_bound_runtime_directory_receipt(
                            runtime,
                            descriptor,
                            trusted_root=trusted,
                            semantic_checker=lambda *_arguments: self.fail(
                                "checker unexpectedly ran"
                            ),
                        )
                observed = os.fstat(replacement[0])
                expected = outside.lstat()
                self.assertEqual(
                    (observed.st_dev, observed.st_ino),
                    (expected.st_dev, expected.st_ino),
                )
            finally:
                if replacement:
                    os.close(replacement[0])

    @unittest.skipIf(os.name == "nt", "POSIX descriptor semantics")
    def test_handle_bound_checker_cannot_be_redirected_by_scope_swap(self):
        with tempfile.TemporaryDirectory() as temporary:
            trusted = Path(temporary).resolve()
            scope_key, relative, arithmetic = _scope_contract()
            runtime = trusted / relative
            runtime.mkdir(parents=True)
            (runtime / "HEAD").write_bytes(b"inside")
            outside = trusted / "outside-store"
            outside.mkdir()
            (outside / "HEAD").write_bytes(b"outside")
            parked = runtime.with_name(".kio-parked")
            descriptor = {"kind": "scope_store", "relative_path": relative}

            def checker(bound, _observed_descriptor, content):
                runtime.rename(parked)
                runtime.symlink_to(outside, target_is_directory=True)
                descriptor_fd = os.open(
                    "HEAD",
                    os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                    dir_fd=bound.directory_fd,
                )
                try:
                    self.assertEqual(os.read(descriptor_fd, 64), b"inside")
                finally:
                    os.close(descriptor_fd)
                return _semantic_evidence(
                    "scope_store",
                    profile="tiny",
                    persona_id="p01",
                    scope_key=scope_key,
                    relative_path=relative,
                    content=content,
                    chunk_arithmetic=arithmetic,
                )

            with self.assertRaises(attestation.PersonaHistoryAttestationError):
                attestation.build_handle_bound_runtime_directory_receipt(
                    runtime,
                    descriptor,
                    trusted_root=trusted,
                    semantic_checker=checker,
                )
            self.assertEqual((outside / "HEAD").read_bytes(), b"outside")

    @unittest.skipIf(os.name == "nt", "POSIX descriptor semantics")
    def test_handle_bound_checker_must_not_close_its_ephemeral_descriptor(self):
        with tempfile.TemporaryDirectory() as temporary:
            trusted = Path(temporary).resolve()
            scope_key, relative, arithmetic = _scope_contract()
            runtime = trusted / relative
            runtime.mkdir(parents=True)
            descriptor = {"kind": "scope_store", "relative_path": relative}

            def checker(bound, _observed_descriptor, content):
                os.close(bound.directory_fd)
                return _semantic_evidence(
                    "scope_store",
                    profile="tiny",
                    persona_id="p01",
                    scope_key=scope_key,
                    relative_path=relative,
                    content=content,
                    chunk_arithmetic=arithmetic,
                )

            with self.assertRaisesRegex(
                attestation.PersonaHistoryAttestationError,
                "changed its supplied descriptor",
            ):
                attestation.build_handle_bound_runtime_directory_receipt(
                    runtime,
                    descriptor,
                    trusted_root=trusted,
                    semantic_checker=checker,
                )

    @unittest.skipIf(os.name == "nt", "POSIX descriptor semantics")
    def test_handle_bound_checker_cannot_rebind_its_descriptor_number(self):
        with tempfile.TemporaryDirectory() as temporary:
            trusted = Path(temporary).resolve()
            scope_key, relative, arithmetic = _scope_contract()
            runtime = trusted / relative
            runtime.mkdir(parents=True)
            outside = trusted / "outside-store"
            outside.mkdir()
            descriptor = {"kind": "scope_store", "relative_path": relative}
            supplied = []

            def checker(bound, _observed_descriptor, content):
                supplied.append(bound.directory_fd)
                replacement = os.open(
                    outside,
                    os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY,
                )
                try:
                    os.dup2(replacement, bound.directory_fd, inheritable=False)
                finally:
                    os.close(replacement)
                return _semantic_evidence(
                    "scope_store",
                    profile="tiny",
                    persona_id="p01",
                    scope_key=scope_key,
                    relative_path=relative,
                    content=content,
                    chunk_arithmetic=arithmetic,
                )

            try:
                with self.assertRaisesRegex(
                    attestation.PersonaHistoryAttestationError,
                    "changed its supplied descriptor",
                ):
                    attestation.build_handle_bound_runtime_directory_receipt(
                        runtime,
                        descriptor,
                        trusted_root=trusted,
                        semantic_checker=checker,
                    )
                observed = os.fstat(supplied[0])
                expected = outside.lstat()
                self.assertEqual(
                    (observed.st_dev, observed.st_ino),
                    (expected.st_dev, expected.st_ino),
                )
            finally:
                if supplied:
                    try:
                        os.close(supplied[0])
                    except OSError:
                        pass

    @unittest.skipIf(os.name == "nt", "POSIX descriptor semantics")
    def test_handle_bound_checker_does_not_close_reused_foreign_fd_slot(self):
        with tempfile.TemporaryDirectory() as temporary:
            trusted = Path(temporary).resolve()
            scope_key, relative, arithmetic = _scope_contract()
            runtime = trusted / relative
            runtime.mkdir(parents=True)
            outside = trusted / "outside-reuse"
            outside.mkdir()
            descriptor = {"kind": "scope_store", "relative_path": relative}
            replacement = []

            def checker(bound, _observed_descriptor, content):
                os.close(bound.directory_fd)
                replacement.append(os.open(outside, os.O_RDONLY | os.O_DIRECTORY))
                self.assertEqual(replacement[0], bound.directory_fd)
                return _semantic_evidence(
                    "scope_store",
                    profile="tiny",
                    persona_id="p01",
                    scope_key=scope_key,
                    relative_path=relative,
                    content=content,
                    chunk_arithmetic=arithmetic,
                )

            try:
                with self.assertRaisesRegex(
                    attestation.PersonaHistoryAttestationError,
                    "changed its supplied descriptor",
                ):
                    attestation.build_handle_bound_runtime_directory_receipt(
                        runtime,
                        descriptor,
                        trusted_root=trusted,
                        semantic_checker=checker,
                    )
                observed = os.fstat(replacement[0])
                expected = outside.lstat()
                self.assertEqual(
                    (observed.st_dev, observed.st_ino),
                    (expected.st_dev, expected.st_ino),
                )
            finally:
                if replacement:
                    os.close(replacement[0])

    @unittest.skipIf(os.name == "nt", "POSIX descriptor semantics")
    def test_handle_bound_checker_rejects_same_inode_reopen_without_closing_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            trusted = Path(temporary).resolve()
            scope_key, relative, arithmetic = _scope_contract()
            runtime = trusted / relative
            runtime.mkdir(parents=True)
            descriptor = {"kind": "scope_store", "relative_path": relative}
            replacement = []

            def checker(bound, _observed_descriptor, content):
                os.close(bound.directory_fd)
                replacement.append(
                    os.open(runtime, os.O_RDONLY | os.O_DIRECTORY)
                )
                self.assertEqual(replacement[0], bound.directory_fd)
                return _semantic_evidence(
                    "scope_store",
                    profile="tiny",
                    persona_id="p01",
                    scope_key=scope_key,
                    relative_path=relative,
                    content=content,
                    chunk_arithmetic=arithmetic,
                )

            try:
                with self.assertRaisesRegex(
                    attestation.PersonaHistoryAttestationError,
                    "changed its supplied descriptor",
                ):
                    attestation.build_handle_bound_runtime_directory_receipt(
                        runtime,
                        descriptor,
                        trusted_root=trusted,
                        semantic_checker=checker,
                    )
                observed = os.fstat(replacement[0])
                expected = runtime.lstat()
                self.assertEqual(
                    (observed.st_dev, observed.st_ino),
                    (expected.st_dev, expected.st_ino),
                )
            finally:
                if replacement:
                    os.close(replacement[0])

    @unittest.skipIf(os.name == "nt", "POSIX descriptor semantics")
    def test_handle_bound_checker_cannot_make_descriptor_inheritable(self):
        with tempfile.TemporaryDirectory() as temporary:
            trusted = Path(temporary).resolve()
            scope_key, relative, arithmetic = _scope_contract()
            runtime = trusted / relative
            runtime.mkdir(parents=True)
            descriptor = {"kind": "scope_store", "relative_path": relative}

            def checker(bound, _observed_descriptor, content):
                os.set_inheritable(bound.directory_fd, True)
                return _semantic_evidence(
                    "scope_store",
                    profile="tiny",
                    persona_id="p01",
                    scope_key=scope_key,
                    relative_path=relative,
                    content=content,
                    chunk_arithmetic=arithmetic,
                )

            with self.assertRaisesRegex(
                attestation.PersonaHistoryAttestationError,
                "changed its supplied descriptor",
            ):
                attestation.build_handle_bound_runtime_directory_receipt(
                    runtime,
                    descriptor,
                    trusted_root=trusted,
                    semantic_checker=checker,
                )

    @unittest.skipIf(os.name == "nt", "POSIX descriptor semantics")
    def test_handle_bound_checker_requires_exact_bounded_limits_type(self):
        class DerivedLimits(attestation.AttestationLimits):
            pass

        with tempfile.TemporaryDirectory() as temporary:
            trusted = Path(temporary).resolve()
            _scope_key, relative, _arithmetic = _scope_contract()
            runtime = trusted / relative
            runtime.mkdir(parents=True)
            descriptor = {"kind": "scope_store", "relative_path": relative}

            for limits in ({"read_size": 512}, DerivedLimits()):
                with self.subTest(limits=type(limits).__name__), self.assertRaisesRegex(
                    attestation.PersonaHistoryAttestationError,
                    "limits must be AttestationLimits",
                ):
                    attestation.build_handle_bound_runtime_directory_receipt(
                        runtime,
                        descriptor,
                        trusted_root=trusted,
                        semantic_checker=lambda *_args: self.fail(
                            "invalid limits reached the checker"
                        ),
                        limits=limits,
                    )

            self.assertFalse(attestation.HANDLE_BOUND_SEMANTIC_TRANSPORT_FORMAL)

    def test_runtime_descriptor_and_path_bounds_fail_before_expensive_normalization(self):
        oversized_descriptor = {
            f"field-{index}": "value" for index in range(10_000)
        }
        with self.assertRaisesRegex(
            attestation.PersonaHistoryAttestationError,
            "exactly kind and relative_path",
        ):
            attestation._validated_runtime_descriptor(oversized_descriptor)

        with mock.patch.object(
            attestation.unicodedata,
            "normalize",
            side_effect=AssertionError("oversized path was normalized"),
        ) as normalize, self.assertRaisesRegex(
            attestation.PersonaHistoryAttestationError,
            "relative_path is invalid",
        ):
            attestation._validate_relative_runtime_path(
                "a" * 4_097,
                "scope_store",
            )
        normalize.assert_not_called()

    def test_content_root_cannot_be_promoted_without_typed_semantic_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            trusted = Path(temporary).resolve()
            scope_key, relative, arithmetic = _scope_contract()
            root = trusted / relative
            root.mkdir(parents=True)
            descriptor = {"kind": "scope_store", "relative_path": relative}
            for checker in (None, lambda *_args: True):
                with self.subTest(checker=checker), self.assertRaises(
                    attestation.PersonaHistoryAttestationError
                ):
                    attestation.build_runtime_directory_receipt(
                        root,
                        descriptor,
                        trusted_root=trusted,
                        semantic_checker=checker,
                    )

    def test_checker_mutation_is_detected_by_the_second_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            trusted = Path(temporary).resolve()
            scope_key, relative, arithmetic = _scope_contract()
            root = trusted / relative
            root.mkdir(parents=True)
            descriptor = {"kind": "scope_store", "relative_path": relative}

            def checker(path, _descriptor, _content):
                (path / "sqlite-wal").write_bytes(b"mutation")
                return _semantic_evidence(
                    "scope_store",
                    profile="tiny",
                    persona_id="p01",
                    scope_key=scope_key,
                    relative_path=relative,
                    content=_content,
                    chunk_arithmetic=arithmetic,
                )

            with self.assertRaisesRegex(
                attestation.PersonaHistoryAttestationError,
                "changed during Kio semantic checking",
            ):
                attestation.build_runtime_directory_receipt(
                    root,
                    descriptor,
                    trusted_root=trusted,
                    semantic_checker=checker,
                )

    @unittest.skipIf(os.name == "nt", "POSIX containment semantics")
    def test_contained_callback_rejects_symlinked_ancestor_and_outside_same_basename(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            trusted = base / "trusted"
            scope_key, relative, arithmetic = _scope_contract()
            runtime = trusted / relative
            runtime.mkdir(parents=True)
            alias = base / "alias"
            alias.symlink_to(trusted, target_is_directory=True)
            descriptor = {"kind": "scope_store", "relative_path": relative}

            def checker(_path, _descriptor, content):
                return _semantic_evidence(
                    "scope_store",
                    profile="tiny",
                    persona_id="p01",
                    scope_key=scope_key,
                    relative_path=relative,
                    content=content,
                    chunk_arithmetic=arithmetic,
                )

            with self.assertRaisesRegex(
                attestation.PersonaHistoryAttestationError,
                "ancestor|canonical|descriptor child",
            ):
                attestation.build_runtime_directory_receipt(
                    alias / relative,
                    descriptor,
                    trusted_root=alias,
                    semantic_checker=checker,
                )
            outside = base / "outside" / ".kio"
            outside.mkdir(parents=True)
            with self.assertRaisesRegex(
                attestation.PersonaHistoryAttestationError,
                "descriptor child",
            ):
                attestation.build_runtime_directory_receipt(
                    outside,
                    descriptor,
                    trusted_root=trusted,
                    semantic_checker=checker,
                )


class TestChunkAndPartialReceipts(unittest.TestCase):
    def test_chunk_arithmetic_accepts_only_exact_role_equations(self):
        valid = _valid_arithmetic(120_000, 9)
        self.assertEqual(valid.contract_contributor_chunks, 120_000)
        cases = (
            {"contract_contributor_chunks": 119_999},
            {"raw_only_chunks": 1},
            {"all_current_eligible_chunks": 120_008},
            {"incidental_searchable_chunks": True},
        )
        baseline = {
            "expected_contract_contributor_chunks": 120_000,
            "contract_contributor_chunks": 120_000,
            "incidental_searchable_chunks": 9,
            "raw_only_chunks": 0,
            "all_current_eligible_chunks": 120_009,
        }
        for change in cases:
            value = {**baseline, **change}
            with self.subTest(change=change), self.assertRaises(
                attestation.PersonaHistoryAttestationError
            ):
                attestation.validate_chunk_arithmetic(value)
        with self.assertRaises(attestation.PersonaHistoryAttestationError):
            attestation.validate_chunk_arithmetic({**baseline, "extra": 0})

    def test_scope_and_person_receipts_are_irreducibly_partial(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            scope_path = base / "x" / ".kio"
            device_path = base / "device" / ".kio-eval-device"
            scope_path.mkdir(parents=True)
            device_path.mkdir(parents=True)
            scope = attestation.build_partial_scope_receipt(
                profile="tiny",
                persona_id="p01",
                scope_key="p01-primary-01",
                relative_path="devices/p01-software-engineer/home/x/.kio",
                directory_content=attestation.walk_directory_content_root(scope_path),
                chunk_arithmetic=_valid_arithmetic(),
            )
            person = attestation.build_partial_person_receipt(
                profile="tiny",
                persona_id="p01",
                expected_contract_contributor_chunks=7,
                device_relative_path=(
                    "devices/p01-software-engineer/.kio-eval-device"
                ),
                device_content=attestation.walk_directory_content_root(device_path),
                scopes=(scope,),
            )
            self.assertFalse(scope.history_ready_attested)
            self.assertFalse(scope.kio_semantics_attested)
            self.assertFalse(person.history_ready_attested)
            self.assertFalse(person.scope_coverage_complete)
            with self.assertRaises(TypeError):
                attestation.PartialScopeReceipt(
                    schema=attestation.PARTIAL_SCOPE_SCHEMA,
                    schema_version=1,
                    profile="tiny",
                    persona_id="p01",
                    scope_key="x",
                    relative_path="x/.kio",
                    directory_content=scope.directory_content,
                    chunk_arithmetic=scope.chunk_arithmetic,
                    history_ready_attested=True,
                )

    def test_scope_and_people_iterables_are_consumed_only_to_overflow_sentinel(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            scope_path = base / "x" / ".kio"
            device_path = base / "device" / ".kio-eval-device"
            scope_path.mkdir(parents=True)
            device_path.mkdir(parents=True)
            scope = attestation.build_partial_scope_receipt(
                profile="tiny",
                persona_id="p01",
                scope_key="p01-primary-01",
                relative_path="devices/p01-software-engineer/home/x/.kio",
                directory_content=attestation.walk_directory_content_root(scope_path),
                chunk_arithmetic=_valid_arithmetic(),
            )
            scope_counter = [0]

            def endless_scopes():
                while True:
                    scope_counter[0] += 1
                    yield scope

            with self.assertRaisesRegex(
                attestation.PersonaHistoryAttestationError,
                "20-item bound",
            ):
                attestation.build_partial_person_receipt(
                    profile="tiny",
                    persona_id="p01",
                    expected_contract_contributor_chunks=7,
                    device_relative_path=(
                        "devices/p01-software-engineer/.kio-eval-device"
                    ),
                    device_content=attestation.walk_directory_content_root(device_path),
                    scopes=endless_scopes(),
                )
            self.assertEqual(scope_counter[0], 21)

            person = attestation.build_partial_person_receipt(
                profile="tiny",
                persona_id="p01",
                expected_contract_contributor_chunks=7,
                device_relative_path="devices/p01-software-engineer/.kio-eval-device",
                device_content=attestation.walk_directory_content_root(device_path),
                scopes=(scope,),
            )
            people_counter = [0]

            def endless_people():
                while True:
                    people_counter[0] += 1
                    yield person

            with self.assertRaisesRegex(
                attestation.PersonaHistoryAttestationError,
                "20-item bound",
            ):
                attestation.build_suite_receipt(
                    profile="tiny",
                    people=endless_people(),
                )
            self.assertEqual(people_counter[0], 21)


class TestSuiteCoverageGate(unittest.TestCase):
    @staticmethod
    def _content(identity, relative):
        return attestation.DirectoryContentRoot(
            schema=attestation.CONTENT_ROOT_SCHEMA,
            schema_version=2,
            coverage=attestation.FILESYSTEM_COVERAGE,
            directory_device=1,
            directory_inode=identity,
            directory_nlink=2,
            descendant_directories=0,
            regular_files=0,
            total_file_bytes=0,
            maximum_depth=0,
            content_root_sha256=hashlib.sha256(relative.encode()).hexdigest(),
        )

    @classmethod
    def _runtime(
        cls,
        kind,
        identity,
        relative,
        *,
        profile,
        persona_id,
        scope_key=None,
        chunk_arithmetic=None,
    ):
        content = cls._content(identity, relative)
        schema = (
            generator.RUNTIME_SCOPE_STORE_SEMANTIC_CONTRACT
            if kind == "scope_store"
            else generator.RUNTIME_DEVICE_STATE_SEMANTIC_CONTRACT
        )
        return content, attestation.RuntimeDirectoryReceipt(
            schema=generator.RUNTIME_DIRECTORY_ATTESTATION_SCHEMA,
            schema_version=1,
            kind=kind,
            relative_path=relative,
            directory_device=content.directory_device,
            directory_inode=content.directory_inode,
            directory_nlink=content.directory_nlink,
            attestor_schema=schema,
            content_root_sha256=content.content_root_sha256,
            semantic_evidence=_semantic_evidence(
                kind,
                profile=profile,
                persona_id=persona_id,
                scope_key=scope_key,
                relative_path=relative,
                content=content,
                chunk_arithmetic=chunk_arithmetic,
            ),
        )

    @classmethod
    def _complete_people(cls, *, profile="tiny", include_runtime=True):
        identity = 10
        people = []
        for persona in fixture_spec.PERSONAS:
            persona_id = persona["id"]
            slug = f"{persona_id}-{persona['role']}"
            scope_targets = fixture_spec.scope_contributor_chunk_targets(
                persona, profile
            )
            scopes = []
            for scope_spec in fixture_spec.scope_specs(persona):
                identity += 1
                relative = (
                    f"devices/{slug}/home/{scope_spec['relative_path']}/.kio"
                )
                target = scope_targets[scope_spec["scope_key"]]
                arithmetic = _valid_arithmetic(target, 0)
                content, runtime = cls._runtime(
                    "scope_store",
                    identity,
                    relative,
                    profile=profile,
                    persona_id=persona_id,
                    scope_key=scope_spec["scope_key"],
                    chunk_arithmetic=arithmetic,
                )
                scopes.append(attestation.build_partial_scope_receipt(
                    profile=profile,
                    persona_id=persona_id,
                    scope_key=scope_spec["scope_key"],
                    relative_path=relative,
                    directory_content=content,
                    chunk_arithmetic=arithmetic,
                    runtime_callback_receipt=runtime if include_runtime else None,
                ))
            identity += 1
            device_relative = f"devices/{slug}/.kio-eval-device"
            device_content, device_runtime = cls._runtime(
                "device_state",
                identity,
                device_relative,
                profile=profile,
                persona_id=persona_id,
            )
            people.append(attestation.build_partial_person_receipt(
                profile=profile,
                persona_id=persona_id,
                expected_contract_contributor_chunks=(
                    fixture_spec.contributor_plan(persona, profile)["target_chunks"]
                ),
                device_relative_path=device_relative,
                device_content=device_content,
                scopes=scopes,
                device_runtime_callback_receipt=(
                    device_runtime if include_runtime else None
                ),
            ))
        return tuple(people)

    def test_exact_400_scope_20_device_shape_stays_unready_without_callback_flag(self):
        people = self._complete_people()
        receipt = attestation.build_suite_receipt(
            profile="tiny",
            people=people,
            kio_semantics_callback_attested=False,
        )
        self.assertEqual(receipt.personas, 20)
        self.assertEqual(receipt.scope_stores, 400)
        self.assertEqual(receipt.device_states, 20)
        self.assertTrue(receipt.filesystem_coverage_complete)
        self.assertFalse(receipt.semantic_coverage_attested)
        self.assertFalse(receipt.history_ready_attested)

        self.assertFalse(people[0].scopes[0].kio_semantics_attested)
        self.assertFalse(people[0].kio_semantics_attested)
        self.assertFalse(
            people[0].scopes[0]
            .runtime_callback_receipt.formal_transport_attested
        )
        with self.assertRaisesRegex(
            attestation.PersonaHistoryAttestationError,
            "non-formal",
        ):
            attestation.build_suite_receipt(
                profile="tiny",
                people=people,
                kio_semantics_callback_attested=True,
            )
        with self.assertRaises(attestation.PersonaHistoryAttestationError):
            replace(receipt, history_ready_attested=True)

    def test_semantic_claim_rejects_missing_scope_device_or_typed_runtime_receipt(self):
        people = self._complete_people()
        incomplete_scope = replace(people[0], scopes=people[0].scopes[:-1])
        missing_device = replace(
            people[0], device_runtime_callback_receipt=None
        )
        no_runtime = self._complete_people(include_runtime=False)
        cases = (
            (incomplete_scope, *people[1:]),
            (missing_device, *people[1:]),
            no_runtime,
            people[:-1],
        )
        for case in cases:
            with self.subTest(scopes=sum(len(p.scopes) for p in case)), \
                    self.assertRaises(attestation.PersonaHistoryAttestationError):
                attestation.build_suite_receipt(
                    profile="tiny",
                    people=case,
                    kio_semantics_callback_attested=True,
                )

    def test_profile_and_scope_quota_substitution_fail_closed(self):
        tiny_people = self._complete_people(include_runtime=False)
        for substituted_profile in ("pilot", "full"):
            with self.subTest(profile=substituted_profile), self.assertRaisesRegex(
                attestation.PersonaHistoryAttestationError,
                "receipt profile|canonical .* plan|canonical .* target|"
                "expected contributor total",
            ):
                attestation.build_suite_receipt(
                    profile=substituted_profile,
                    people=tiny_people,
                )

        first = tiny_people[0]
        left, right, *remaining = first.scopes
        left_target = left.chunk_arithmetic.contract_contributor_chunks
        right_target = right.chunk_arithmetic.contract_contributor_chunks
        shifted = replace(first, scopes=(
            replace(
                left,
                chunk_arithmetic=_valid_arithmetic(left_target + 1, 0),
            ),
            replace(
                right,
                chunk_arithmetic=_valid_arithmetic(right_target - 1, 0),
            ),
            *remaining,
        ))
        self.assertEqual(
            sum(
                scope.chunk_arithmetic.contract_contributor_chunks
                for scope in shifted.scopes
            ),
            first.expected_contract_contributor_chunks,
        )
        with self.assertRaisesRegex(
            attestation.PersonaHistoryAttestationError,
            "scope contributor chunks differ",
        ):
            attestation.build_suite_receipt(
                profile="tiny",
                people=(shifted, *tiny_people[1:]),
            )

    def test_valid_profile_bound_projections_are_distinct_and_still_unready(self):
        tiny = attestation.build_suite_receipt(
            profile="tiny",
            people=self._complete_people(profile="tiny", include_runtime=False),
        )
        pilot = attestation.build_suite_receipt(
            profile="pilot",
            people=self._complete_people(profile="pilot", include_runtime=False),
        )
        for receipt in (tiny, pilot):
            self.assertTrue(receipt.filesystem_coverage_complete)
            self.assertRegex(receipt.persona_plan_root_sha256, r"^[0-9a-f]{64}$")
            self.assertRegex(receipt.event_projection_root_sha256, r"^[0-9a-f]{64}$")
            self.assertFalse(receipt.history_ready_attested)
        self.assertNotEqual(
            tiny.persona_plan_root_sha256,
            pilot.persona_plan_root_sha256,
        )
        self.assertNotEqual(tiny.projection_root_sha256, pilot.projection_root_sha256)

    def test_scope_semantic_evidence_cannot_be_swapped_from_counts_or_identity(self):
        person = self._complete_people()[0]
        scope = person.scopes[0]
        runtime = scope.runtime_callback_receipt
        evidence = runtime.semantic_evidence
        target = scope.chunk_arithmetic.contract_contributor_chunks

        with self.assertRaisesRegex(
            attestation.PersonaHistoryAttestationError,
            "canonical plan",
        ):
            replace(
                evidence,
                chunk_arithmetic=_valid_arithmetic(target + 1, 0),
            )

        with self.assertRaisesRegex(
            attestation.PersonaHistoryAttestationError,
            "non-canonical scope",
        ):
            replace(evidence, scope_key="p01-primary-99")

        with self.assertRaisesRegex(
            attestation.PersonaHistoryAttestationError,
            "runtime directory callback receipt is invalid",
        ):
            replace(
                runtime,
                semantic_evidence=(
                    person.scopes[1]
                    .runtime_callback_receipt
                    .semantic_evidence
                ),
            )


if __name__ == "__main__":
    unittest.main()
