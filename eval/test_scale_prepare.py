#!/usr/bin/env python3
"""Focused recovery and safety tests for scale-corpus preparation."""

from contextlib import contextmanager, redirect_stdout
import io
import os
from pathlib import Path
import sqlite3
import stat
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import attest_scale_corpus as attestor  # noqa: E402
import generate_scale_corpus as generator  # noqa: E402
import prepare_scale_corpus as preparer  # noqa: E402
import scale_fixture_spec as spec  # noqa: E402


def _scope_report(root, name, index):
    scope = root / name
    (scope / ".kcs").mkdir(parents=True, exist_ok=True)
    return {
        "name": name,
        "scope_id": f"{index:026d}",
        "root_path": str(scope.resolve()),
        "head": "sha256:" + f"{index:064x}",
    }


def _create_registry(root, reports):
    path = preparer._registry_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE scopes ("
            "scope_id TEXT NOT NULL, kcs_path TEXT NOT NULL, "
            "root_path TEXT NOT NULL, "
            "participates_in_global_search INTEGER NOT NULL, "
            "indexed INTEGER NOT NULL, last_seen_at TEXT NOT NULL)"
        )
        for report in reports:
            conn.execute(
                "INSERT INTO scopes VALUES (?, ?, ?, 1, 1, ?)",
                (
                    report["scope_id"],
                    str((Path(report["root_path"]) / ".kcs").resolve()),
                    report["root_path"],
                    "2026-07-13T00:00:00Z",
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return path


class TestRegistryRecovery(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="kcs-scale-prepare-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "corpus"
        self.root.mkdir()
        self.reports = [
            _scope_report(self.root, "scope-a", 1),
            _scope_report(self.root, "scope-b", 2),
        ]

    def test_only_an_exact_current_registry_allows_skip(self):
        registry = _create_registry(self.root, self.reports)
        self.assertTrue(
            preparer._registry_matches_attested_scopes(self.root, self.reports)
        )

        conn = sqlite3.connect(registry)
        try:
            conn.execute(
                "INSERT INTO scopes VALUES (?, ?, ?, 1, 1, ?)",
                (
                    "9" * 26,
                    str((self.root / "extra" / ".kcs").absolute()),
                    str((self.root / "extra").absolute()),
                    "2026-07-13T00:00:00Z",
                ),
            )
            conn.commit()
        finally:
            conn.close()
        self.assertFalse(
            preparer._registry_matches_attested_scopes(self.root, self.reports)
        )

    def test_nonattested_crash_recovery_accepts_only_a_strict_noop(self):
        value = {
            "status": "noop",
            "failed_files": 0,
            "pending_files": 0,
            "skipped_oversized_files": 0,
            "skipped_unrecognized_binary_files": 0,
            "normalized_files": 1,
            "commit_hash": None,
        }
        scope = {"name": "scope-a", "expected_files": 1}
        self.assertEqual(preparer._validate_index_result(value, scope), "noop")

        value["commit_hash"] = "sha256:" + "1" * 64
        with self.assertRaisesRegex(
            preparer.ScalePreparationError, "noop.*commit_hash"
        ):
            preparer._validate_index_result(value, scope)

    def test_missing_and_corrupt_registry_require_recovery(self):
        self.assertFalse(
            preparer._registry_matches_attested_scopes(self.root, self.reports)
        )
        registry = preparer._registry_path(self.root)
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_bytes(b"not a sqlite database")
        self.assertFalse(
            preparer._registry_matches_attested_scopes(self.root, self.reports)
        )

    def test_malformed_registry_path_values_require_recovery(self):
        registry = preparer._registry_path(self.root)
        registry.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(registry)
        try:
            conn.execute(
                "CREATE TABLE scopes ("
                "scope_id, kcs_path, root_path, "
                "participates_in_global_search, indexed)"
            )
            conn.execute(
                "INSERT INTO scopes VALUES (?, NULL, ?, 1, 1)",
                (self.reports[0]["scope_id"], self.reports[0]["root_path"]),
            )
            conn.commit()
        finally:
            conn.close()
        self.assertFalse(
            preparer._registry_matches_attested_scopes(
                self.root, [self.reports[0]]
            )
        )

    def test_oversized_registry_path_is_rejected_before_materialization(self):
        registry = _create_registry(self.root, self.reports)
        conn = sqlite3.connect(registry)
        try:
            conn.execute(
                "UPDATE scopes SET kcs_path = ? WHERE scope_id = ?",
                (
                    "x" * (preparer.MAX_REGISTRY_PATH_BYTES + 1),
                    self.reports[0]["scope_id"],
                ),
            )
            conn.commit()
        finally:
            conn.close()
        self.assertFalse(
            preparer._registry_matches_attested_scopes(self.root, self.reports)
        )

    def test_registry_reset_preflights_every_sidecar_before_deletion(self):
        registry = preparer._registry_path(self.root)
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_bytes(b"corrupt")
        wal = Path(str(registry) + "-wal")
        wal.write_bytes(b"wal")
        unsafe = Path(str(registry) + "-shm")
        unsafe.mkdir()

        with self.assertRaises(preparer.ScalePreparationError):
            preparer._reset_isolated_registry(self.root)
        self.assertTrue(registry.is_file())
        self.assertTrue(wal.is_file())

        unsafe.rmdir()
        unrelated = registry.parent / "keep.txt"
        unrelated.write_text("keep", encoding="utf-8")
        preparer._reset_isolated_registry(self.root)
        self.assertFalse(registry.exists())
        self.assertFalse(wal.exists())
        self.assertEqual(unrelated.read_text(encoding="utf-8"), "keep")

    def test_invalid_registry_reregisters_every_locally_attested_scope(self):
        manifest = {
            "profile": "tiny",
            "scopes": [
                {"name": "scope-a", "expected_files": 1},
                {"name": "scope-b", "expected_files": 1},
            ],
        }
        noop = {
            "status": "noop",
            "failed_files": 0,
            "pending_files": 0,
            "skipped_oversized_files": 0,
            "skipped_unrecognized_binary_files": 0,
            "normalized_files": 1,
            "commit_hash": None,
        }
        attestation = {"totals": {"current_eligible_chunks": 6}}
        with (
            mock.patch.object(
                generator,
                "load_owned_manifest",
                return_value=(self.root, {}, manifest),
            ),
            mock.patch.object(attestor, "verify_source_files", return_value=2),
            mock.patch.object(preparer, "_resolve_binary", return_value=Path("/kcs")),
            mock.patch.object(preparer, "_validate_isolated_device_root"),
            mock.patch.object(preparer, "subprocess_env", return_value={}),
            mock.patch.object(
                preparer,
                "_existing_scope_attestations",
                return_value={
                    report["name"]: report for report in self.reports
                },
            ),
            mock.patch.object(
                preparer, "_registry_matches_attested_scopes", return_value=False
            ),
            mock.patch.object(preparer, "_reset_isolated_registry") as reset,
            mock.patch.object(preparer, "_run_kcs", return_value=noop) as run_kcs,
            mock.patch.object(
                attestor,
                "attest_scope",
                side_effect=lambda _root, scope: next(
                    report
                    for report in self.reports
                    if report["name"] == scope["name"]
                ),
            ),
            mock.patch.object(
                attestor, "attest_corpus", return_value=attestation
            ),
        ):
            report, returned_attestation = preparer._prepare_corpus_locked(
                self.root, "/kcs"
            )

        reset.assert_called_once_with(self.root)
        self.assertEqual(run_kcs.call_count, 2)
        self.assertTrue(
            all(
                call.args[2] == preparer._OFFLINE_INDEX_ARGS
                for call in run_kcs.call_args_list
            )
        )
        self.assertEqual(report["indexed_scopes"], ["scope-a", "scope-b"])
        self.assertEqual(report["reregistered_scopes"], ["scope-a", "scope-b"])
        self.assertEqual(report["already_attested_scopes"], [])
        self.assertIs(returned_attestation, attestation)

    def test_current_registry_skips_without_indexing(self):
        manifest = {
            "profile": "tiny",
            "scopes": [
                {"name": "scope-a", "expected_files": 1},
                {"name": "scope-b", "expected_files": 1},
            ],
        }
        attestation = {"totals": {"current_eligible_chunks": 6}}
        with (
            mock.patch.object(
                generator,
                "load_owned_manifest",
                return_value=(self.root, {}, manifest),
            ),
            mock.patch.object(attestor, "verify_source_files", return_value=2),
            mock.patch.object(preparer, "_resolve_binary", return_value=Path("/kcs")),
            mock.patch.object(preparer, "_validate_isolated_device_root"),
            mock.patch.object(preparer, "subprocess_env", return_value={}),
            mock.patch.object(
                preparer,
                "_existing_scope_attestations",
                return_value={
                    report["name"]: report for report in self.reports
                },
            ),
            mock.patch.object(
                preparer, "_registry_matches_attested_scopes", return_value=True
            ),
            mock.patch.object(preparer, "_reset_isolated_registry") as reset,
            mock.patch.object(preparer, "_run_kcs") as run_kcs,
            mock.patch.object(
                attestor, "attest_corpus", return_value=attestation
            ),
        ):
            report, _ = preparer._prepare_corpus_locked(self.root, "/kcs")

        reset.assert_not_called()
        run_kcs.assert_not_called()
        self.assertEqual(report["indexed_scopes"], [])
        self.assertEqual(report["reregistered_scopes"], [])
        self.assertEqual(
            report["already_attested_scopes"], ["scope-a", "scope-b"]
        )


class TestPreparationBoundsAndLock(unittest.TestCase):
    def test_subprocess_capture_rejects_output_over_bound(self):
        with mock.patch.object(preparer, "MAX_SUBPROCESS_OUTPUT_BYTES", 128):
            with self.assertRaisesRegex(
                preparer.ScalePreparationError, "output exceeded 128 bytes"
            ):
                preparer._run_process_bounded(
                    [sys.executable, "-c", "import sys; sys.stdout.write('x' * 4096)"],
                    Path.cwd(),
                    os.environ.copy(),
                )

    def test_subprocess_capture_does_not_wait_for_inherited_output_handle(self):
        code = (
            "import subprocess, sys; "
            "subprocess.Popen([sys.executable, '-c', "
            "'import time; time.sleep(2)']); "
            "print('{}')"
        )
        started = time.monotonic()
        returncode, stdout, _ = preparer._run_process_bounded(
            [sys.executable, "-c", code], Path.cwd(), os.environ.copy()
        )
        self.assertEqual(returncode, 0)
        self.assertEqual(stdout.strip(), b"{}")
        self.assertLess(time.monotonic() - started, 1.0)

    def test_device_tree_enumeration_is_bounded(self):
        with tempfile.TemporaryDirectory(prefix="kcs-device-bound-") as temp:
            root = Path(temp)
            device = root / spec.DEVICE_DIR_NAME
            device.mkdir()
            for index in range(3):
                (device / f"entry-{index}").write_bytes(b"")
            with mock.patch.object(preparer, "MAX_DEVICE_TREE_ENTRIES", 2):
                with self.assertRaisesRegex(
                    preparer.ScalePreparationError, "exceeds 2 entries"
                ):
                    preparer._validate_isolated_device_root(root)

    def test_reparse_metadata_is_never_a_plain_file_or_directory(self):
        directory = SimpleNamespace(
            st_mode=stat.S_IFDIR,
            st_file_attributes=preparer.WINDOWS_REPARSE_POINT_ATTRIBUTE,
            st_reparse_tag=0,
        )
        regular = SimpleNamespace(
            st_mode=stat.S_IFREG,
            st_file_attributes=0,
            st_reparse_tag=1,
        )
        self.assertFalse(preparer._is_plain_directory(directory))
        self.assertFalse(preparer._is_plain_regular_file(regular))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO requires POSIX")
    def test_device_tree_rejects_special_files(self):
        with tempfile.TemporaryDirectory(prefix="kcs-device-special-") as temp:
            root = Path(temp)
            device = root / spec.DEVICE_DIR_NAME
            device.mkdir()
            os.mkfifo(device / "blocked")
            with self.assertRaisesRegex(
                preparer.ScalePreparationError, "must be plain files"
            ):
                preparer._validate_isolated_device_root(root)

    def test_main_holds_fixture_lock_through_atomic_reports(self):
        with tempfile.TemporaryDirectory(prefix="kcs-scale-lock-") as temp:
            root = Path(temp) / "corpus"
            active = {"value": False}

            @contextmanager
            def fake_lock(path):
                self.assertEqual(Path(path), root)
                self.assertFalse(active["value"])
                active["value"] = True
                try:
                    yield
                finally:
                    active["value"] = False

            report = {
                "profile": "tiny",
                "indexed_scopes": [],
                "resumed_noop_scopes": [],
                "already_attested_scopes": [],
                "totals": {"current_eligible_chunks": 60},
            }
            attestation = {"passed": True}

            def locked_core(*_args):
                self.assertTrue(active["value"])
                return report, attestation

            writes = []

            def locked_write(path, value):
                self.assertTrue(active["value"])
                writes.append((path, value))

            with (
                mock.patch.object(
                    generator, "fixture_lock", fake_lock, create=True
                ),
                mock.patch.object(
                    preparer, "_prepare_corpus_locked", side_effect=locked_core
                ),
                mock.patch.object(
                    attestor, "_write_json_atomic", side_effect=locked_write
                ),
                redirect_stdout(io.StringIO()),
            ):
                result = preparer.main(["--corpus", str(root), "--bin", "/kcs"])

            self.assertEqual(result, 0)
            self.assertFalse(active["value"])
            self.assertEqual(
                [path.name for path, _ in writes],
                [spec.ATTESTATION_NAME, spec.PREPARE_REPORT_NAME],
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
