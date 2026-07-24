#!/usr/bin/env python3
"""Bounded-read regression tests for the scale attestor."""

from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import attest_scale_corpus as attestor  # noqa: E402
import scale_fixture_spec as spec  # noqa: E402


class _NamedChild:
    def __init__(self, name):
        self.name = name


class _OverflowDirectory:
    def iterdir(self):
        yield _NamedChild("one")
        yield _NamedChild("two")
        yield _NamedChild("overflow")
        raise AssertionError("bounded enumeration consumed past expected + 1")

    def __str__(self):
        return "overflow-directory"


class _NonemptyRuntimeTree:
    def lstat(self):
        return SimpleNamespace(
            st_mode=stat.S_IFDIR,
            st_file_attributes=0,
            st_reparse_tag=0,
        )

    def rglob(self, _pattern):
        yield object()
        raise AssertionError("empty-tree check consumed past its first entry")

    def __str__(self):
        return "nonempty-runtime-tree"


class _WindowsReparsePath:
    def __init__(self, mode, label):
        self.mode = mode
        self.label = label

    def lstat(self):
        return SimpleNamespace(
            st_mode=self.mode,
            st_size=0,
            st_file_attributes=attestor.generator.WINDOWS_REPARSE_POINT_ATTRIBUTE,
            st_reparse_tag=0xA0000003,
        )

    def open(self, *_args, **_kwargs):
        raise AssertionError("reparse file must be rejected before open")

    def rglob(self, _pattern):
        raise AssertionError("reparse directory must be rejected before traversal")

    def __str__(self):
        return self.label


class TestFilesystemReadBounds(unittest.TestCase):
    def test_scope_enumeration_consumes_only_expected_plus_one(self):
        with self.assertRaises(attestor.ScaleAttestationError):
            attestor._bounded_child_names(
                _OverflowDirectory(), 2, "test scope"
            )

    def test_nonempty_runtime_tree_stops_after_first_entry(self):
        with self.assertRaises(attestor.ScaleAttestationError):
            attestor._ensure_empty_runtime_tree(
                _NonemptyRuntimeTree(), "runtime records"
            )

    def test_windows_reparse_file_is_rejected_before_read(self):
        path = _WindowsReparsePath(stat.S_IFREG, "reparse-file")
        with self.assertRaisesRegex(
            attestor.ScaleAttestationError, "plain regular file"
        ):
            attestor._regular_file_bytes(path, 1, "test file")

    def test_windows_reparse_directory_is_rejected_before_traversal(self):
        path = _WindowsReparsePath(stat.S_IFDIR, "reparse-directory")
        with self.assertRaisesRegex(
            attestor.ScaleAttestationError, "plain directory"
        ):
            attestor._ensure_empty_runtime_tree(path, "runtime records")


class TestSqlReadBounds(unittest.TestCase):
    def test_schema_lookup_only_materializes_known_table_names(self):
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        conn.execute("CREATE TABLE chunks (value INTEGER)")
        for index in range(100):
            conn.execute(f"CREATE TABLE attacker_{index} (value INTEGER)")
        self.assertEqual(attestor._table_names(conn), {"chunks"})

    def test_head_tree_query_rejects_at_expected_plus_one(self):
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        conn.execute(
            "CREATE TABLE tree_entries ("
            "commit_hash TEXT, path TEXT, raw_hash TEXT, "
            "tool_profile_hash TEXT, gen INTEGER)"
        )
        conn.executemany(
            "INSERT INTO tree_entries VALUES ('head', ?, 'raw', 'tool', 0)",
            [(f"document-{index}.md",) for index in range(100)],
        )
        with self.assertRaises(attestor.ScaleAttestationError):
            attestor._head_tree_rows(conn, "head", 2)

    def test_eligible_materialization_stops_at_explicit_limit(self):
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        conn.executescript(
            """
            CREATE TABLE chunks (
                chunk_id TEXT,
                raw_hash TEXT,
                tool_profile_hash TEXT,
                gen INTEGER,
                text_hash TEXT,
                first_seen_commit TEXT
            );
            CREATE TABLE chunk_config_generations (
                association_rowid INTEGER PRIMARY KEY,
                chunk_id TEXT,
                chunking_config_hash TEXT
            );
            CREATE TABLE tree_entries (
                commit_hash TEXT,
                raw_hash TEXT,
                tool_profile_hash TEXT,
                gen INTEGER
            );
            """
        )
        for index in range(100):
            chunk_id = f"chunk-{index}"
            raw_hash = f"raw-{index}"
            conn.execute(
                "INSERT INTO chunks VALUES (?, ?, 'tool', 0, ?, 'commit')",
                (chunk_id, raw_hash, f"text-{index}"),
            )
            conn.execute(
                "INSERT INTO chunk_config_generations VALUES (?, ?, 'config')",
                (index + 1, chunk_id),
            )
            conn.execute(
                "INSERT INTO tree_entries VALUES ('head', ?, 'tool', 0)",
                (raw_hash,),
            )
        attestor.materialize_current_eligible(
            conn, "head", "config", maximum_rows=3
        )
        count = conn.execute(
            "SELECT COUNT(*) FROM scale_current_eligible"
        ).fetchone()[0]
        self.assertEqual(count, 3)

    def test_registry_query_materializes_no_more_than_twenty_one_rows(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE scopes ("
            "scope_id TEXT, kio_path TEXT, root_path TEXT, "
            "participates_in_global_search INTEGER, indexed INTEGER)"
        )
        conn.executemany(
            "INSERT INTO scopes VALUES (?, '/kio', '/root', 1, 1)",
            [(f"scope-{index}",) for index in range(100)],
        )
        statements = []
        conn.set_trace_callback(statements.append)
        with (
            mock.patch.object(attestor, "_open_read_only", return_value=conn),
            mock.patch.object(attestor, "_require_plain_directory", return_value=True),
        ):
            with self.assertRaisesRegex(
                attestor.ScaleAttestationError, "row count mismatch"
            ):
                attestor.attest_registry(Path("ignored"), [{}] * len(spec.SCOPES))
        self.assertTrue(
            any("FROM scopes LIMIT 21" in statement for statement in statements)
        )


class TestAttestationLock(unittest.TestCase):
    def test_main_reports_fixture_lock_error_without_traceback(self):
        with tempfile.TemporaryDirectory(prefix="scale-attest-lock-error-") as temp:
            root = Path(temp) / "corpus"
            root.mkdir()
            with (
                mock.patch.object(
                    attestor.generator,
                    "fixture_lock",
                    side_effect=attestor.generator.ScaleGenerationError("bad lock"),
                ),
                mock.patch("builtins.print"),
            ):
                self.assertEqual(attestor.main(["--corpus", str(root)]), 1)

    def test_main_rejects_unknown_report_name_inside_owned_corpus(self):
        with tempfile.TemporaryDirectory(prefix="scale-attest-out-") as temp:
            root = Path(temp) / "corpus"
            root.mkdir()
            poisoned = root / "unexpected-report.json"
            with (
                mock.patch.object(attestor.generator, "fixture_lock") as lock,
                mock.patch.object(attestor, "attest_corpus") as attest,
                mock.patch("builtins.print"),
            ):
                self.assertEqual(
                    attestor.main(
                        ["--corpus", str(root), "--out", str(poisoned)]
                    ),
                    1,
                )
            lock.assert_not_called()
            attest.assert_not_called()
            self.assertFalse(poisoned.exists())

    def test_main_holds_fixture_lock_for_attestation_and_report_publish(self):
        events = []
        locked = False

        @contextmanager
        def fake_lock(path):
            nonlocal locked
            events.append(("enter", Path(path)))
            locked = True
            try:
                yield
            finally:
                locked = False
                events.append(("exit", Path(path)))

        def fake_attest(path):
            self.assertTrue(locked)
            events.append(("attest", Path(path)))
            return {
                "profile": "tiny",
                "totals": {
                    "scopes": 20,
                    "source_files": 20,
                    "current_eligible_chunks": 60,
                    "fts_matched_current_chunks": 60,
                },
            }

        def fake_write(path, _report):
            self.assertTrue(locked)
            events.append(("write", Path(path)))

        with tempfile.TemporaryDirectory(prefix="scale-attest-lock-") as temp:
            root = Path(temp) / "corpus"
            root.mkdir()
            out = Path(temp) / "report.json"
            with (
                mock.patch.object(
                    attestor.generator, "fixture_lock", fake_lock, create=True
                ),
                mock.patch.object(attestor, "attest_corpus", fake_attest),
                mock.patch.object(attestor, "_write_json_atomic", fake_write),
                mock.patch("builtins.print"),
            ):
                self.assertEqual(
                    attestor.main(["--corpus", str(root), "--out", str(out)]),
                    0,
                )

        self.assertEqual(
            [event[0] for event in events],
            ["enter", "attest", "write", "exit"],
        )

    def test_external_symlink_parent_into_corpus_is_rejected_before_lock(self):
        with tempfile.TemporaryDirectory(prefix="scale-attest-alias-") as temp:
            root = Path(temp) / "corpus"
            root.mkdir()
            alias = Path(temp) / "external-alias"
            alias.symlink_to(root, target_is_directory=True)
            disguised = alias / spec.ATTESTATION_NAME
            with (
                mock.patch.object(attestor.generator, "fixture_lock") as lock,
                mock.patch.object(attestor, "attest_corpus") as attest,
                mock.patch("builtins.print"),
            ):
                self.assertEqual(
                    attestor.main(
                        ["--corpus", str(root), "--out", str(disguised)]
                    ),
                    1,
                )
            lock.assert_not_called()
            attest.assert_not_called()
            self.assertFalse((root / spec.ATTESTATION_NAME).exists())

    def test_allowed_external_symlink_parent_is_canonicalized_for_publish(self):
        report = {
            "profile": "tiny",
            "totals": {
                "scopes": 20,
                "source_files": 20,
                "current_eligible_chunks": 60,
                "fts_matched_current_chunks": 60,
            },
        }
        with tempfile.TemporaryDirectory(prefix="scale-attest-external-") as temp:
            root = Path(temp) / "corpus"
            root.mkdir()
            external = Path(temp) / "external"
            external.mkdir()
            alias = Path(temp) / "external-alias"
            alias.symlink_to(external, target_is_directory=True)
            lexical_out = alias / "attestation.json"
            with (
                mock.patch.object(attestor.generator, "fixture_lock"),
                mock.patch.object(attestor, "attest_corpus", return_value=report),
                mock.patch.object(attestor, "_write_json_atomic") as write,
                mock.patch("builtins.print"),
            ):
                self.assertEqual(
                    attestor.main(
                        ["--corpus", str(root), "--out", str(lexical_out)]
                    ),
                    0,
                )
            write.assert_called_once_with(
                external.resolve(strict=True) / "attestation.json", report
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
