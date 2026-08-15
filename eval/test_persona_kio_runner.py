#!/usr/bin/env python3
"""Focused tests for the bounded, unbound persona W0 Kio runner core."""

import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

from eval import persona_kio_runner as runner
from eval import persona_root_lock as root_lock
from eval import persona_storage as storage


PLAN_SHA = "sha256:" + "a" * 64
SCHEDULE_SHA = "sha256:" + "b" * 64
RENDER_SHA = "sha256:" + "c" * 64
ARTIFACT_BUNDLE_SHA = "sha256:" + hashlib.sha256(
    storage.canonical_json_bytes(
        {
            "schema": "kio.persona.artifact-bundle/v2",
            "fixture_id": storage.FIXTURE_ID,
            "profile": "tiny",
            "plan_digest": PLAN_SHA,
            "plan_sha256": PLAN_SHA,
            "schedule_sha256": SCHEDULE_SHA,
            "render_sha256": RENDER_SHA,
        }
    )
).hexdigest()


def _canonical_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _expected_counts():
    # pdf_text-like overlap means these three disposition counters need not be
    # a partition of physical_files.
    return {
        "physical_files": 10,
        "normalized_files": 6,
        "pending_online_tasks": 5,
        "skipped_unrecognized_binary_files": 1,
        "failed_files": 0,
        "pending_files": 0,
        "skipped_oversized_files": 0,
        "completed_online_tasks": 0,
        "external_cost_microusd": 0,
    }


def _valid_commit(counts=None):
    counts = _expected_counts() if counts is None else counts
    return {
        "commit_type": "auto",
        "created_at": "2026-07-14T00:00:00Z",
        "message": "kio index auto snapshot",
        "object_type": "commit",
        "parents": [],
        "stats": {
            "files_added": counts["physical_files"],
            "files_modified": 0,
            "files_deleted": 0,
        },
        "tool_lock_hash": "sha256:" + "2" * 64,
        "tree": "sha256:" + "3" * 64,
    }


def _valid_index_result(counts=None, status="indexed"):
    counts = _expected_counts() if counts is None else counts
    commit = _valid_commit(counts) if status == "indexed" else None
    commit_hash = (
        "sha256:" + hashlib.sha256(_canonical_json(commit)).hexdigest()
        if commit is not None
        else None
    )
    return {
        "status": status,
        "approval_method": "yes",
        "network_allowed": False,
        "network_opt_in": False,
        "pending_online_tasks": counts["pending_online_tasks"],
        "paused_tasks": 0,
        "failed_files": counts["failed_files"],
        "normalized_files": counts["normalized_files"],
        "pending_files": counts["pending_files"],
        "skipped_oversized_files": counts["skipped_oversized_files"],
        "skipped_unrecognized_binary_files": counts[
            "skipped_unrecognized_binary_files"
        ],
        "embedding_tasks_executed": 0,
        "embedding_tasks_failed": 0,
        "tree_hash": "sha256:" + "3" * 64,
        "commit_hash": commit_hash,
        "commit": commit,
        "budget_warning": None,
        "skipped_units": [],
    }


def _write_executable(path, body):
    path.write_text("#!/bin/sh\nset -eu\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return path.resolve()


def _unbound_index_receipt(persona_id, scope_id, scope_path, counts=None):
    counts = _expected_counts() if counts is None else counts
    return {
        "schema": runner.OFFLINE_INDEX_RECEIPT_SCHEMA,
        "schema_version": 1,
        "persona_id": persona_id,
        "scope_id": scope_id,
        "scope_path": str(scope_path),
        "command": ["index", "--offline", "--yes"],
        "binary_identity_sha256": "1" * 64,
        "environment_receipt_sha256": "2" * 64,
        "expected_counts": counts,
        "execution": {
            "returncode": 0,
            "stdout_sha256": "3" * 64,
            "stderr_sha256": hashlib.sha256(b"").hexdigest(),
        },
        "validated_result": _valid_index_result(counts),
        "external_api_calls_attested": False,
        "network_observation": "unavailable",
        "receipt_binding_status": runner.UNBOUND_COMMAND_RECEIPTS_STATUS,
        "actual_kio_chunks_attested": False,
        "opaque_runtime_contents_attested": False,
        "history_ready_attested": False,
        "history_assignment_executable": False,
    }


class PersonaRunnerTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="persona-kio-runner-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.replay = self.base / "replay-root"
        self.replay.mkdir()
        binding = {
            "schema": "kio.persona.storage-root-binding/v2",
            "fixture_id": "kio-persona-pc-v2",
            "profile": "tiny",
            "replay_id": "replay-01",
            "destination_root": str(self.replay),
            "filesystem_device": self.replay.lstat().st_dev,
            "plan_digest": PLAN_SHA,
            "plan_sha256": PLAN_SHA,
            "schedule_sha256": SCHEDULE_SHA,
            "render_sha256": RENDER_SHA,
            "artifact_bundle_sha256": ARTIFACT_BUNDLE_SHA,
            "sources_materialized": False,
            "actual_kio_evidence": False,
            "history_ready": False,
        }
        binding_bytes = (
            json.dumps(binding, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        self.binding_sha = "sha256:" + hashlib.sha256(binding_bytes).hexdigest()
        owner = storage.make_owner_marker(
            profile="tiny",
            replay_id="replay-01",
            state="ready",
            artifact_bundle_sha256=ARTIFACT_BUNDLE_SHA,
            root_binding_sha256=self.binding_sha,
        )
        (self.replay / storage.OWNER_MARKER_NAME).write_bytes(
            (
                json.dumps(owner, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n"
            ).encode("utf-8")
        )
        (self.replay / "persona-root-binding.json").write_bytes(binding_bytes)
        self.person = self.replay / "devices" / "person"
        self.home = self.person / "home"
        self.scope = self.home / "documents" / "scope-a"
        self.scope.mkdir(parents=True)

    def make_binary(self, body=None):
        if body is None:
            body = (
                'if [ "${1-}" = "--version" ]; then\n'
                '  printf "kio 0.1.0\\n"\n'
                "  exit 0\n"
                "fi\n"
                "printf '{}\\n'\n"
            )
        return _write_executable(self.base / "fake-kio", body)

    def external_binary_identity(self, binary, *, version="kio 0.1.0"):
        snapshot = runner._read_binary_snapshot(binary)
        stdout = (version + "\n").encode("utf-8")
        return {
            "schema": runner.BINARY_IDENTITY_SCHEMA,
            "schema_version": 1,
            **snapshot,
            "version": version,
            "version_stdout_sha256": hashlib.sha256(stdout).hexdigest(),
            "version_stderr_sha256": hashlib.sha256(b"").hexdigest(),
        }

    def lease(self):
        return root_lock.replay_root_lock(
            self.replay,
            expected_profile="tiny",
            expected_replay_id="replay-01",
            expected_artifact_bundle_sha256=ARTIFACT_BUNDLE_SHA,
            expected_root_binding_sha256=self.binding_sha,
        )

    def precreated_environment(self):
        device = self.person / ".kio-eval-device"
        config = device / "config"
        data = device / "data"
        cache = device / "cache"
        temporary = cache / "tmp"
        for path in (config, data, cache, temporary):
            path.mkdir(parents=True, exist_ok=True)
        environment = {
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(config),
            "XDG_DATA_HOME": str(data),
            "XDG_CACHE_HOME": str(cache),
            "TMPDIR": str(temporary),
            "PATH": os.defpath,
            "LANG": "C",
            "LC_ALL": "C",
            "TZ": "UTC",
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "ALL_PROXY": "http://127.0.0.1:9",
            "NO_PROXY": "",
        }
        return runner.validate_person_subprocess_environment(
            environment, self.person
        )


class TestBinaryIdentity(PersonaRunnerTestCase):
    def test_read_only_snapshot_binds_path_mode_and_hash(self):
        binary = self.make_binary()
        snapshot = runner._read_binary_snapshot(binary)
        metadata = binary.lstat()
        self.assertEqual(snapshot["canonical_path"], str(binary))
        self.assertEqual(snapshot["device"], metadata.st_dev)
        self.assertEqual(snapshot["inode"], metadata.st_ino)
        self.assertEqual(snapshot["mode"], stat.S_IMODE(metadata.st_mode))
        self.assertEqual(snapshot["size"], metadata.st_size)
        self.assertEqual(
            snapshot["sha256"], hashlib.sha256(binary.read_bytes()).hexdigest()
        )
        identity = self.external_binary_identity(binary)
        self.assertRegex(runner.binary_identity_sha256(identity), r"^[0-9a-f]{64}$")
        self.assertFalse(runner.TRUSTED_BINARY_EXECUTION_AVAILABLE)
        with self.assertRaisesRegex(
            runner.PersonaKioRunnerError, "trusted.*execution.*unavailable"
        ):
            runner.attest_kio_binary(binary)

    def test_symlink_hardlink_noncanonical_and_writable_binary_are_rejected(self):
        binary = self.make_binary()
        symlink = self.base / "fake-link"
        symlink.symlink_to(binary)
        with self.assertRaises(runner.PersonaKioRunnerError):
            runner.attest_kio_binary(symlink)

        hardlink = self.base / "fake-hardlink"
        os.link(binary, hardlink)
        with self.assertRaisesRegex(runner.PersonaKioRunnerError, "hard link"):
            runner.attest_kio_binary(binary)
        hardlink.unlink()

        binary.chmod(0o775)
        with self.assertRaisesRegex(runner.PersonaKioRunnerError, "group/world writable"):
            runner.attest_kio_binary(binary)
        binary.chmod(0o755)
        relative = Path(os.path.relpath(binary, Path.cwd()))
        with self.assertRaisesRegex(runner.PersonaKioRunnerError, "absolute canonical"):
            runner.attest_kio_binary(relative)

    def test_binary_change_after_external_identity_is_detected(self):
        binary = self.make_binary()
        identity = self.external_binary_identity(binary)
        binary.write_bytes(binary.read_bytes() + b"# changed\n")
        binary.chmod(0o755)
        with self.assertRaisesRegex(runner.PersonaKioRunnerError, "no longer matches"):
            runner.require_stable_kio_binary(identity)

    def test_matching_external_identity_cannot_claim_local_version_revalidation(self):
        binary = self.make_binary()
        identity = self.external_binary_identity(binary, version="kio 9.9.9")
        with self.assertRaisesRegex(
            runner.PersonaKioRunnerError, "trusted.*execution.*unavailable"
        ):
            runner.require_stable_kio_binary(identity)

    def test_attestation_never_executes_side_effecting_version_command(self):
        counter = self.base / "counter"
        body = (
            'if [ "${1-}" = "--version" ]; then\n'
            f'  n=$(cat "{counter}" 2>/dev/null || printf 0)\n'
            "  n=$((n + 1))\n"
            f'  printf "%s" "$n" > "{counter}"\n'
            '  printf "kio 0.1.%s\\n" "$n"\n'
            "  exit 0\n"
            "fi\n"
            "printf '{}\\n'\n"
        )
        binary = self.make_binary(body)
        with self.assertRaisesRegex(
            runner.PersonaKioRunnerError, "trusted.*execution.*unavailable"
        ):
            runner.attest_kio_binary(binary)
        self.assertFalse(counter.exists())

    def test_private_version_probe_is_also_fail_closed(self):
        binary = self.make_binary()
        with mock.patch.object(runner, "_run_process_bounded") as execute:
            with self.assertRaisesRegex(
                runner.PersonaKioRunnerError, "trusted.*execution.*unavailable"
            ):
                runner._version_probe(binary)
            execute.assert_not_called()
        with mock.patch.object(runner.subprocess, "Popen") as popen:
            with self.assertRaisesRegex(
                runner.PersonaKioRunnerError, "trusted.*execution.*unavailable"
            ):
                runner._run_process_bounded(
                    [str(binary), "--version"],
                    binary.parent,
                    {},
                    runner.VERSION_LIMITS,
                )
            popen.assert_not_called()

    def test_missing_required_descriptor_flags_fail_closed(self):
        binary = self.make_binary()
        for name in ("O_NOFOLLOW", "O_CLOEXEC"):
            with self.subTest(name=name), mock.patch.object(runner.os, name, 0):
                with self.assertRaisesRegex(
                    runner.PersonaKioRunnerError, f"{name}.*unavailable"
                ):
                    runner.attest_kio_binary(binary)


class TestEnvironment(PersonaRunnerTestCase):
    def test_precreated_environment_is_minimal_per_person(self):
        environment = self.precreated_environment()
        self.assertEqual(set(environment), runner._CONTROLLED_ENVIRONMENT_KEYS)
        self.assertEqual(environment["HOME"], str(self.home))
        self.assertEqual(
            environment["XDG_DATA_HOME"],
            str(self.person / ".kio-eval-device" / "data"),
        )
        self.assertFalse(any(name.startswith("KIO_") for name in environment))
        self.assertFalse(any(name.endswith("_API_KEY") for name in environment))
        self.assertNotIn("UNRELATED_VALUE", environment)
        receipt = runner.environment_receipt(environment, self.person)
        self.assertFalse(
            receipt["effective_environment_forbidden_credentials_present"]
        )
        self.assertFalse(receipt["external_api_execution_authorized"])
        self.assertFalse(receipt["history_ready_attested"])
        self.assertFalse(receipt["history_assignment_executable"])

    def test_environment_builder_fails_closed_before_creation(self):
        device = self.person / ".kio-eval-device"
        with self.lease() as lease:
            with self.assertRaisesRegex(
                runner.PersonaKioRunnerError, "filesystem mutation.*unavailable"
            ):
                runner.build_person_subprocess_environment(self.person, lease=lease)
        self.assertFalse(device.exists())

    def test_effective_environment_rejects_extra_kio_or_api_keys(self):
        environment = self.precreated_environment()
        for name in ("KIO_FIXED_NOW", "OPENAI_API_KEY"):
            with self.subTest(name=name):
                tampered = dict(environment)
                tampered[name] = "unsafe"
                with self.assertRaises(runner.PersonaKioRunnerError):
                    runner.validate_person_subprocess_environment(tampered, self.person)

    def test_precreated_environment_rejects_unsafe_device_symlink(self):
        outside = self.base / "outside"
        outside.mkdir()
        device = self.person / ".kio-eval-device"
        device.symlink_to(outside, target_is_directory=True)
        environment = {
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(device / "config"),
            "XDG_DATA_HOME": str(device / "data"),
            "XDG_CACHE_HOME": str(device / "cache"),
            "TMPDIR": str(device / "cache" / "tmp"),
            "PATH": os.defpath,
            "LANG": "C",
            "LC_ALL": "C",
            "TZ": "UTC",
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "ALL_PROXY": "http://127.0.0.1:9",
            "NO_PROXY": "",
        }
        with self.assertRaisesRegex(
            runner.PersonaKioRunnerError, "canonical path|missing or inaccessible"
        ):
            runner.validate_person_subprocess_environment(environment, self.person)
        self.assertEqual(list(outside.iterdir()), [])

    def test_environment_swap_seam_cannot_escape_the_leased_root(self):
        outside = self.base / "outside-device"
        outside.mkdir()
        device = self.person / ".kio-eval-device"
        original = runner.eval_env.subprocess_env

        def swap_device_then_prepare(*arguments, **keywords):
            device.symlink_to(outside, target_is_directory=True)
            return original(*arguments, **keywords)

        with self.lease() as lease:
            with mock.patch.object(
                runner.eval_env,
                "subprocess_env",
                side_effect=swap_device_then_prepare,
            ) as prepare:
                with self.assertRaisesRegex(
                    runner.PersonaKioRunnerError,
                    "filesystem mutation.*unavailable",
                ):
                    runner.build_person_subprocess_environment(
                        self.person, lease=lease
                    )
                prepare.assert_not_called()
        self.assertFalse(device.exists())
        self.assertEqual(list(outside.iterdir()), [])

    def test_environment_mutation_requires_active_lease_and_exact_person_child(self):
        device = self.person / ".kio-eval-device"
        with self.assertRaisesRegex(runner.PersonaKioRunnerError, "active replay-root lease"):
            runner.build_person_subprocess_environment(self.person, lease=None)
        self.assertFalse(device.exists())

        outside = self.replay / "not-devices" / "person"
        (outside / "home").mkdir(parents=True)
        with self.lease() as lease:
            with self.assertRaisesRegex(
                runner.PersonaKioRunnerError, "devices/<slug>"
            ):
                runner.build_person_subprocess_environment(outside, lease=lease)
        self.assertFalse((outside / ".kio-eval-device").exists())


class TestStrictJsonAndValidators(PersonaRunnerTestCase):
    def test_strict_json_rejects_duplicate_nested_keys_scalars_nan_and_bom(self):
        bad_values = (
            b'{"a":1,"a":2}\n',
            b'{"outer":{"x":1,"x":2}}\n',
            b'[1,2]\n',
            b'{"x":NaN}\n',
            b'{"x":1.5}\n',
            b'{"x":1e2}\n',
            b'{"x":' + b'9' * 5_000 + b'}\n',
            b'\xef\xbb\xbf{}\n',
            b'\xff',
        )
        for raw in bad_values:
            with self.subTest(raw=raw):
                with self.assertRaises(runner.PersonaKioRunnerError):
                    runner.parse_strict_json_object(raw)
        self.assertEqual(
            runner.parse_strict_json_object(b'{"outer":{"x":1}}\n'),
            {"outer": {"x": 1}},
        )

    def test_fresh_init_validator_is_exact_and_path_bound(self):
        value = {
            "status": "initialized",
            "repaired": [],
            "path": str(self.scope),
            "kio_path": str(self.scope / ".kio"),
        }
        self.assertEqual(runner.validate_init_result(value, self.scope), value)
        for field, invalid in (
            ("status", "already initialized"),
            ("repaired", ["HEAD"]),
            ("path", str(self.home)),
        ):
            with self.subTest(field=field):
                tampered = dict(value)
                tampered[field] = invalid
                with self.assertRaises(runner.PersonaKioRunnerError):
                    runner.validate_init_result(tampered, self.scope)
        with self.assertRaisesRegex(runner.PersonaKioRunnerError, "unexpected shape"):
            runner.validate_init_result({**value, "extra": 1}, self.scope)

    def test_mixed_offline_index_validator_accepts_overlap_oracle_and_noop(self):
        counts = _expected_counts()
        value = _valid_index_result(counts)
        self.assertEqual(runner.validate_offline_index_result(value, counts), value)
        noop = _valid_index_result(counts, status="noop")
        self.assertEqual(
            runner.validate_offline_index_result(
                noop, counts, expected_status="noop"
            ),
            noop,
        )

    def test_offline_validator_rejects_counter_network_cost_commit_and_extra_fields(self):
        counts = _expected_counts()
        mutations = (
            ("pending_online_tasks", 4),
            ("network_allowed", True),
            ("embedding_tasks_executed", 1),
            ("skipped_units", [{"raw_hash": "x"}]),
        )
        for field, invalid in mutations:
            with self.subTest(field=field):
                value = _valid_index_result(counts)
                value[field] = invalid
                with self.assertRaises(runner.PersonaKioRunnerError):
                    runner.validate_offline_index_result(value, counts)
        value = _valid_index_result(counts)
        value["extra"] = 1
        with self.assertRaisesRegex(runner.PersonaKioRunnerError, "unexpected shape"):
            runner.validate_offline_index_result(value, counts)
        value = _valid_index_result(counts)
        value["commit"]["stats"]["files_added"] = 9
        with self.assertRaisesRegex(runner.PersonaKioRunnerError, "commit stats"):
            runner.validate_offline_index_result(value, counts)
        bad_oracle = dict(counts)
        bad_oracle["external_cost_microusd"] = 1
        with self.assertRaisesRegex(runner.PersonaKioRunnerError, "online cost"):
            runner.validate_offline_index_result(_valid_index_result(counts), bad_oracle)


class TestFakeExecutableIntegration(PersonaRunnerTestCase):
    def test_fresh_init_and_offline_index_fail_closed_before_execution(self):
        counts = _expected_counts()
        invoked = self.base / "unsafe-command-invoked"
        identity = {"untrusted": True}

        def mark_command_invoked(*_arguments, **_keywords):
            invoked.write_bytes(b"invoked")
            raise AssertionError("unsafe command seam was reached")

        self.assertFalse(runner.HANDLE_RELATIVE_EXECUTION_AVAILABLE)
        self.assertFalse(runner.PERSONA_FILESYSTEM_MUTATION_AVAILABLE)
        self.assertFalse(runner.TRUSTED_BINARY_EXECUTION_AVAILABLE)
        with self.lease() as lease:
            environment = self.precreated_environment()
            with mock.patch.object(
                runner, "_run_kio_json", side_effect=mark_command_invoked
            ) as command:
                with self.assertRaisesRegex(
                    runner.PersonaKioRunnerError, "handle-relative.*unavailable"
                ):
                    runner.run_scope_init(
                        identity,
                        self.person,
                        self.scope,
                        lease=lease,
                        persona_id="p01",
                        scope_id="p01-s01",
                        environment=environment,
                        limits=runner.SubprocessLimits(2, 64 * 1024, 0.005),
                    )
                command.assert_not_called()
            self.assertFalse((self.scope / ".kio").exists())
            (self.scope / ".kio").mkdir()
            with mock.patch.object(
                runner, "_run_kio_json", side_effect=mark_command_invoked
            ) as command:
                with self.assertRaisesRegex(
                    runner.PersonaKioRunnerError, "handle-relative.*unavailable"
                ):
                    runner.run_scope_offline_index(
                        identity,
                        self.person,
                        self.scope,
                        counts,
                        lease=lease,
                        persona_id="p01",
                        scope_id="p01-s01",
                        environment=environment,
                        limits=runner.SubprocessLimits(2, 64 * 1024, 0.005),
                    )
                command.assert_not_called()
        self.assertFalse(invoked.exists())

    def test_scope_swap_seam_cannot_escape_the_leased_root(self):
        outside = self.base / "outside-scope"
        outside.mkdir()
        identity = {"untrusted": True}
        original = runner._run_kio_json

        def swap_scope_then_run(*arguments, **keywords):
            parked = self.scope.with_name("scope-a-parked")
            self.scope.rename(parked)
            self.scope.symlink_to(outside, target_is_directory=True)
            return original(*arguments, **keywords)

        with self.lease() as lease:
            environment = self.precreated_environment()
            with mock.patch.object(
                runner, "_run_kio_json", side_effect=swap_scope_then_run
            ) as command:
                with self.assertRaisesRegex(
                    runner.PersonaKioRunnerError, "handle-relative.*unavailable"
                ):
                    runner.run_scope_init(
                        identity,
                        self.person,
                        self.scope,
                        lease=lease,
                        persona_id="p01",
                        scope_id="p01-s01",
                        environment=environment,
                    )
                command.assert_not_called()
        self.assertFalse((outside / ".kio").exists())
        self.assertTrue(self.scope.is_dir())
        self.assertFalse(self.scope.is_symlink())

    def test_init_refuses_existing_store_without_invoking_binary(self):
        marker = self.scope / ".kio" / "keep"
        marker.parent.mkdir()
        marker.write_bytes(b"unchanged")
        identity = {"untrusted": True}
        before = (marker.read_bytes(), marker.lstat().st_ino)
        with self.lease() as lease:
            environment = self.precreated_environment()
            with self.assertRaisesRegex(runner.PersonaKioRunnerError, "classify resume"):
                runner.run_scope_init(
                    identity,
                    self.person,
                    self.scope,
                    lease=lease,
                    persona_id="p01",
                    scope_id="p01-s01",
                    environment=environment,
                )
        self.assertEqual((marker.read_bytes(), marker.lstat().st_ino), before)

    def test_command_mutation_requires_active_lease(self):
        identity = {"untrusted": True}
        with self.assertRaisesRegex(runner.PersonaKioRunnerError, "active replay-root lease"):
            runner.run_scope_init(
                identity,
                self.person,
                self.scope,
                lease=None,
                persona_id="p01",
                scope_id="p01-s01",
                environment={},
            )
        self.assertFalse((self.scope / ".kio").exists())


class TestResumeClassification(PersonaRunnerTestCase):
    def make_scope_rows(self):
        second = self.home / "documents" / "scope-b"
        second.mkdir(parents=True, exist_ok=True)
        return second, [
            {"scope_id": "p01-s01", "relative_path": "home/documents/scope-a"},
            {"scope_id": "p01-s02", "relative_path": "home/documents/scope-b"},
        ]

    def test_existing_stores_and_absent_registry_only_declare_reset(self):
        second, scopes = self.make_scope_rows()
        first_store = self.scope / ".kio"
        second_store = second / ".kio"
        first_store.mkdir()
        second_store.mkdir()
        first_marker = first_store / "keep"
        second_marker = second_store / "keep"
        first_marker.write_bytes(b"first")
        second_marker.write_bytes(b"second")
        receipts = [
            _unbound_index_receipt("p01", "p01-s01", self.scope),
            _unbound_index_receipt("p01", "p01-s02", second),
        ]
        before = {
            path: (path.read_bytes(), path.lstat().st_ino, path.stat().st_mtime_ns)
            for path in (first_marker, second_marker)
        }
        result = runner.classify_person_resume(
            self.person,
            persona_id="p01",
            scopes=scopes,
            completed_index_receipts=receipts,
            registry_state="absent",
        )
        self.assertEqual(result["classification"], "registry_reset_required")
        self.assertTrue(result["registry"]["reset_required"])
        self.assertFalse(result["registry"]["reset_implemented"])
        self.assertFalse(result["registry"]["reset_performed"])
        self.assertEqual(result["scope_store_deletions_performed"], 0)
        self.assertEqual(result["filesystem_mutations_performed"], 0)
        self.assertFalse(result["history_ready_attested"])
        after = {
            path: (path.read_bytes(), path.lstat().st_ino, path.stat().st_mtime_ns)
            for path in (first_marker, second_marker)
        }
        self.assertEqual(after, before)

    def test_valid_registry_distinguishes_unbound_fresh_and_unattested_stores(self):
        second, scopes = self.make_scope_rows()
        self.scope.joinpath(".kio").mkdir()
        second.joinpath(".kio").mkdir()
        receipts = [
            _unbound_index_receipt("p01", "p01-s01", self.scope),
            _unbound_index_receipt("p01", "p01-s02", second),
        ]
        unbound = runner.classify_person_resume(
            self.person,
            persona_id="p01",
            scopes=scopes,
            completed_index_receipts=receipts,
            registry_state="valid",
        )
        self.assertEqual(
            unbound["classification"], runner.UNBOUND_COMMAND_RECEIPTS_STATUS
        )
        self.assertTrue(
            all(
                row["state"] == "unbound_command_receipt_present"
                for row in unbound["scopes"]
            )
        )
        self.assertFalse(unbound["history_ready_attested"])

        unattested = runner.classify_person_resume(
            self.person,
            persona_id="p01",
            scopes=scopes,
            completed_index_receipts=receipts[:1],
            registry_state="valid",
        )
        self.assertEqual(
            unattested["classification"], "semantic_attestation_required"
        )

        second.joinpath(".kio").rmdir()
        fresh = runner.classify_person_resume(
            self.person,
            persona_id="p01",
            scopes=scopes,
            completed_index_receipts=receipts[:1],
            registry_state="valid",
        )
        self.assertEqual(fresh["classification"], "fresh_prepare_required")

    def test_receipt_without_store_and_unsafe_store_fail_closed(self):
        second, scopes = self.make_scope_rows()
        receipt = _unbound_index_receipt("p01", "p01-s01", self.scope)
        with self.assertRaisesRegex(runner.PersonaKioRunnerError, "receipt exists"):
            runner.classify_person_resume(
                self.person,
                persona_id="p01",
                scopes=scopes,
                completed_index_receipts=[receipt],
                registry_state="valid",
            )

        outside = self.base / "outside-store"
        outside.mkdir()
        self.scope.joinpath(".kio").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(runner.PersonaKioRunnerError, "not a plain directory"):
            runner.classify_person_resume(
                self.person,
                persona_id="p01",
                scopes=scopes,
                registry_state="valid",
            )

    def test_tampered_receipt_and_invalid_registry_state_are_rejected(self):
        second, scopes = self.make_scope_rows()
        self.scope.joinpath(".kio").mkdir()
        for field, invalid in (
            ("history_ready_attested", True),
            ("external_api_calls_attested", True),
            ("network_observation", "observed"),
        ):
            with self.subTest(field=field):
                receipt = _unbound_index_receipt("p01", "p01-s01", self.scope)
                receipt[field] = invalid
                with self.assertRaisesRegex(
                    runner.PersonaKioRunnerError, "unbound.*claims are invalid"
                ):
                    runner.classify_person_resume(
                        self.person,
                        persona_id="p01",
                        scopes=scopes,
                        completed_index_receipts=[receipt],
                        registry_state="valid",
                    )
        with self.assertRaisesRegex(runner.PersonaKioRunnerError, "registry_state"):
            runner.classify_person_resume(
                self.person,
                persona_id="p01",
                scopes=scopes,
                registry_state="unknown",
            )


if __name__ == "__main__":
    unittest.main()
