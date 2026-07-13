#!/usr/bin/env python3
"""Standard-library tests for the independent 120k scale fixture tooling."""

import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import attest_scale_corpus as attestor  # noqa: E402
import generate_scale_corpus as generator  # noqa: E402
import scale_fixture_spec as spec  # noqa: E402


class TestScaleSpec(unittest.TestCase):
    def test_full_shape_is_exactly_20_scopes_and_120k_chunks(self):
        full = spec.profile("full")
        self.assertEqual(full["scope_count"], 20)
        self.assertEqual(full["files_per_scope"], 200)
        self.assertEqual(full["sections_per_file"], 30)
        self.assertEqual(full["expected_files"], 4_000)
        self.assertEqual(full["expected_current_chunks"], 120_000)
        self.assertGreater(full["expected_current_chunks"], 100_000)
        rendered = spec.render_document(19, 199, "full")
        sections = [part for part in rendered.split("## ") if part]
        self.assertEqual(len(sections), 30)
        self.assertTrue(all(len(part) < spec.CHUNKING_MAX_CHARS for part in sections))

    def test_tiny_uses_same_20_scope_registry_shape(self):
        tiny = spec.profile("tiny")
        self.assertEqual(tiny["scope_count"], 20)
        self.assertEqual(tiny["expected_files"], 20)
        self.assertEqual(tiny["expected_current_chunks"], 60)
        rendered = spec.render_document(0, 0, "tiny")
        sections = [line for line in rendered.splitlines() if line.startswith("## ")]
        self.assertEqual(len(sections), 3)
        self.assertEqual(rendered.count("scale needle"), 3)

    def test_manifest_queries_are_unique_tokens_in_the_expected_sections(self):
        queries = [spec.section_query(index, 0, 0) for index in range(20)]
        self.assertEqual(len(set(queries)), 20)
        for index, query in enumerate(queries):
            self.assertRegex(query, r"^[0-9a-f]{12}$")
            rendered = spec.render_document(index, 0, "full")
            first_section = rendered.split("## ", 2)[1]
            self.assertEqual(first_section.count(query), 1)
            self.assertEqual(rendered.count(query), 1)


class TestScaleGeneration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="kcs-scale-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "corpus"

    def test_generation_is_deterministic_and_ready_rerun_is_noop(self):
        first, generated = generator.write_corpus(self.root, "tiny")
        self.assertTrue(generated)
        manifest_path = self.root / spec.MANIFEST_NAME
        marker_path = self.root / spec.OWNER_MARKER_NAME
        before_manifest = manifest_path.read_bytes()
        before_times = (manifest_path.stat().st_mtime_ns, marker_path.stat().st_mtime_ns)

        second, generated = generator.write_corpus(self.root, "tiny")
        self.assertFalse(generated)
        self.assertEqual(first, second)
        self.assertEqual(manifest_path.read_bytes(), before_manifest)
        self.assertEqual(
            (manifest_path.stat().st_mtime_ns, marker_path.stat().st_mtime_ns),
            before_times,
        )
        _, owner, loaded = generator.load_owned_manifest(self.root)
        self.assertEqual(owner["state"], "ready")
        self.assertEqual(loaded["query_workload_id"], spec.QUERY_WORKLOAD_ID)
        self.assertEqual(loaded["shape"]["expected_current_chunks"], 60)
        self.assertEqual(
            attestor.verify_source_files(self.root, loaded, allow_kcs=True), 20
        )

    def test_query_workload_identity_is_required(self):
        manifest, _ = generator.write_corpus(self.root, "tiny")
        tampered = json.loads(json.dumps(manifest))
        tampered["query_workload_id"] = "broad-common-legacy"
        with self.assertRaisesRegex(
            generator.ScaleGenerationError, "query_workload_id"
        ):
            generator.validate_manifest(tampered)

    def test_nonempty_unowned_output_is_never_modified(self):
        self.root.mkdir()
        sentinel = self.root / "keep.txt"
        sentinel.write_text("owned by user", encoding="utf-8")
        with self.assertRaises(generator.ScaleGenerationError):
            generator.write_corpus(self.root, "tiny")
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "owned by user")
        self.assertFalse((self.root / spec.OWNER_MARKER_NAME).exists())
        self.assertFalse((self.root / spec.LOCK_NAME).exists())

    def test_invalid_owner_marker_is_rejected_before_lock_creation(self):
        self.root.mkdir()
        marker = self.root / spec.OWNER_MARKER_NAME
        marker.write_bytes(b"not valid owner JSON\n")
        before = marker.read_bytes()
        with self.assertRaises(generator.ScaleGenerationError):
            generator.write_corpus(self.root, "tiny")
        self.assertEqual(marker.read_bytes(), before)
        self.assertEqual(
            sorted(path.name for path in self.root.iterdir()),
            [spec.OWNER_MARKER_NAME],
        )
        self.assertFalse((self.root / spec.LOCK_NAME).exists())

    def test_symlink_owner_marker_is_rejected_before_lock_creation(self):
        self.root.mkdir()
        outside = Path(self.temp.name) / "outside-owner"
        outside.write_bytes(
            generator._json_bytes(generator._owner_value("tiny", "building"))
        )
        marker = self.root / spec.OWNER_MARKER_NAME
        marker.symlink_to(outside)
        with self.assertRaises(generator.ScaleGenerationError):
            generator.write_corpus(self.root, "tiny")
        self.assertTrue(marker.is_symlink())
        self.assertEqual(
            outside.read_bytes(),
            generator._json_bytes(generator._owner_value("tiny", "building")),
        )
        self.assertFalse((self.root / spec.LOCK_NAME).exists())

    def test_windows_reparse_metadata_is_not_a_plain_regular_file(self):
        metadata = SimpleNamespace(
            st_mode=stat.S_IFREG,
            st_file_attributes=generator.WINDOWS_REPARSE_POINT_ATTRIBUTE,
            st_reparse_tag=0xA000000C,
        )
        self.assertFalse(generator._is_plain_regular_file(metadata))
        directory_metadata = SimpleNamespace(
            st_mode=stat.S_IFDIR,
            st_file_attributes=generator.WINDOWS_REPARSE_POINT_ATTRIBUTE,
            st_reparse_tag=0xA0000003,
        )
        self.assertFalse(generator._is_plain_directory(directory_metadata))

    def test_owned_tree_rejects_reparse_scope_source_runtime_and_device(self):
        manifest, _ = generator.write_corpus(self.root, "tiny")
        scope_dir = self.root / manifest["scopes"][0]["name"]
        source = scope_dir / manifest["scopes"][0]["files"][0]["path"]
        kcs_dir = scope_dir / ".kcs"
        kcs_dir.mkdir()
        device_dir = self.root / spec.DEVICE_DIR_NAME
        device_dir.mkdir()
        runtime = self.root / spec.ATTESTATION_NAME
        runtime.write_bytes(b"{}\n")
        original_lstat = Path.lstat

        for target in (scope_dir, source, kcs_dir, device_dir, runtime):
            with self.subTest(target=target):
                def fake_lstat(path, *args, **kwargs):
                    metadata = original_lstat(path, *args, **kwargs)
                    if path == target:
                        return SimpleNamespace(
                            st_mode=metadata.st_mode,
                            st_size=metadata.st_size,
                            st_dev=metadata.st_dev,
                            st_ino=metadata.st_ino,
                            st_file_attributes=(
                                generator.WINDOWS_REPARSE_POINT_ATTRIBUTE
                            ),
                            st_reparse_tag=0xA0000003,
                        )
                    return metadata

                with mock.patch.object(Path, "lstat", new=fake_lstat):
                    with self.assertRaises(generator.ScaleGenerationError):
                        generator._check_owned_tree(self.root, "tiny")

    def test_unowned_enumeration_is_bounded_and_never_modified(self):
        self.root.mkdir()
        for index in range(10):
            (self.root / f"user-{index}.txt").write_text(
                str(index), encoding="utf-8"
            )
        before = sorted(path.name for path in self.root.iterdir())
        with self.assertRaises(generator.ScaleGenerationError):
            generator.write_corpus(self.root, "tiny")
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), before)
        self.assertFalse((self.root / spec.LOCK_NAME).exists())

    def test_lock_is_regular_persistent_and_survives_owned_reset(self):
        generator.write_corpus(self.root, "tiny")
        lock_path = self.root / spec.LOCK_NAME
        self.assertTrue(lock_path.is_file())
        self.assertFalse(lock_path.is_symlink())
        self.assertEqual(lock_path.read_bytes(), generator.LOCK_BYTES)

        generator.reset_owned_output(self.root)
        self.assertEqual(
            sorted(path.name for path in self.root.iterdir()),
            [spec.LOCK_NAME],
        )
        self.assertEqual(lock_path.read_bytes(), generator.LOCK_BYTES)
        generator.write_corpus(self.root, "tiny")
        self.assertEqual(lock_path.read_bytes(), generator.LOCK_BYTES)

    def test_lock_symlink_is_rejected_without_touching_owned_sources(self):
        manifest, _ = generator.write_corpus(self.root, "tiny")
        source = (
            self.root
            / manifest["scopes"][0]["name"]
            / manifest["scopes"][0]["files"][0]["path"]
        )
        source_before = source.read_bytes()
        lock_path = self.root / spec.LOCK_NAME
        lock_path.unlink()
        outside = Path(self.temp.name) / "outside-lock"
        outside.write_bytes(generator.LOCK_BYTES)
        lock_path.symlink_to(outside)

        with self.assertRaises(generator.ScaleGenerationError):
            generator.write_corpus(self.root, "tiny")
        self.assertEqual(source.read_bytes(), source_before)
        self.assertEqual(outside.read_bytes(), generator.LOCK_BYTES)

    def test_fixture_lock_excludes_an_independent_process(self):
        generator.write_corpus(self.root, "tiny")
        ready = Path(self.temp.name) / "child-ready"
        acquired = Path(self.temp.name) / "child-acquired"
        script = (
            "import sys\n"
            "from pathlib import Path\n"
            "import generate_scale_corpus as generator\n"
            "Path(sys.argv[2]).write_text('ready', encoding='utf-8')\n"
            "with generator.fixture_lock(sys.argv[1]):\n"
            "    Path(sys.argv[3]).write_text('acquired', encoding='utf-8')\n"
        )
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parent)
        with generator.fixture_lock(self.root):
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    script,
                    str(self.root),
                    str(ready),
                    str(acquired),
                ],
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            deadline = time.monotonic() + 5
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(ready.exists(), "child did not reach the lock attempt")
            time.sleep(0.1)
            self.assertFalse(acquired.exists())
        stdout, stderr = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 0, stdout + stderr)
        self.assertTrue(acquired.exists())

    def test_every_source_is_published_through_atomic_writer(self):
        published = []
        original = generator._atomic_write

        def recording_atomic_write(path, data):
            published.append(Path(path))
            return original(path, data)

        with mock.patch.object(
            generator, "_atomic_write", side_effect=recording_atomic_write
        ):
            manifest, _ = generator.write_corpus(self.root, "tiny")

        expected_sources = {
            self.root / scope["name"] / file_entry["path"]
            for scope in manifest["scopes"]
            for file_entry in scope["files"]
        }
        self.assertTrue(expected_sources.issubset(set(published)))
        self.assertFalse(
            any(path.name.endswith(".tmp") for path in self.root.rglob("*"))
        )

    def test_atomic_writer_does_not_leave_partial_final_on_replace_error(self):
        self.root.mkdir()
        target = self.root / "document.md"
        with mock.patch.object(
            generator.os, "replace", side_effect=OSError("injected replace failure")
        ):
            with self.assertRaises(OSError):
                generator._atomic_write(target, b"complete bytes")
        self.assertFalse(target.exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_exact_initial_owner_temp_is_recovered_under_existing_lock(self):
        self.root.mkdir()
        (self.root / spec.LOCK_NAME).write_bytes(generator.LOCK_BYTES)
        temp_owner = self.root / f".{spec.OWNER_MARKER_NAME}.abcdefgh.tmp"
        temp_owner.write_bytes(
            generator._json_bytes(generator._owner_value("tiny", "building"))
        )

        manifest, generated = generator.write_corpus(self.root, "tiny")
        self.assertTrue(generated)
        self.assertFalse(temp_owner.exists())
        self.assertEqual(manifest["shape"]["expected_current_chunks"], 60)

    def test_one_exact_owned_source_temp_is_recovered_but_lookalikes_are_not(self):
        manifest, _ = generator.write_corpus(self.root, "tiny")
        scope_dir = self.root / manifest["scopes"][0]["name"]
        source_name = manifest["scopes"][0]["files"][0]["path"]
        marker = self.root / spec.OWNER_MARKER_NAME
        marker.write_bytes(
            generator._json_bytes(generator._owner_value("tiny", "building"))
        )
        exact = scope_dir / f".{source_name}.abcdefgh.tmp"
        exact.write_bytes(b"interrupted temporary bytes")
        generator.write_corpus(self.root, "tiny")
        self.assertFalse(exact.exists())

        marker.write_bytes(
            generator._json_bytes(generator._owner_value("tiny", "building"))
        )
        lookalike = scope_dir / f".{source_name}.abcdefg.tmp"
        lookalike.write_bytes(b"not an owned temporary name")
        with self.assertRaises(generator.ScaleGenerationError):
            generator.write_corpus(self.root, "tiny")
        self.assertTrue(lookalike.is_file())

    def test_unknown_owned_entry_blocks_reset_before_deletion(self):
        manifest, _ = generator.write_corpus(self.root, "tiny")
        first_source = (
            self.root
            / manifest["scopes"][0]["name"]
            / manifest["scopes"][0]["files"][0]["path"]
        )
        unknown = self.root / "user-note.txt"
        unknown.write_text("do not delete", encoding="utf-8")
        with self.assertRaises(generator.ScaleGenerationError):
            generator.write_corpus(self.root, "tiny", reset_owned=True)
        self.assertTrue(first_source.exists())
        self.assertEqual(unknown.read_text(encoding="utf-8"), "do not delete")

    def test_unsafe_late_reset_target_blocks_before_scope_deletion(self):
        manifest, _ = generator.write_corpus(self.root, "tiny")
        first_source = (
            self.root
            / manifest["scopes"][0]["name"]
            / manifest["scopes"][0]["files"][0]["path"]
        )
        # Runtime reports must be regular files. Before the full preflight this
        # late error was discovered only after every scope directory was deleted.
        (self.root / spec.ATTESTATION_NAME).mkdir()
        with self.assertRaises(generator.ScaleGenerationError):
            generator.write_corpus(self.root, "tiny", reset_owned=True)
        self.assertTrue(first_source.is_file())
        self.assertTrue((self.root / spec.ATTESTATION_NAME).is_dir())

    def test_interrupted_reset_keeps_owner_until_final_unlink_and_resumes(self):
        generator.write_corpus(self.root, "tiny")
        owner_path = self.root / spec.OWNER_MARKER_NAME
        manifest_path = self.root / spec.MANIFEST_NAME
        original_unlink = Path.unlink

        def interrupt_before_owner(path, *args, **kwargs):
            if path == owner_path:
                raise OSError("injected interruption before owner unlink")
            return original_unlink(path, *args, **kwargs)

        with mock.patch.object(Path, "unlink", new=interrupt_before_owner):
            with self.assertRaisesRegex(OSError, "injected interruption"):
                generator.write_corpus(self.root, "tiny", reset_owned=True)

        self.assertTrue(owner_path.is_file())
        self.assertFalse(manifest_path.exists())
        self.assertTrue((self.root / spec.LOCK_NAME).is_file())
        resumed, generated = generator.write_corpus(
            self.root, "tiny", reset_owned=True
        )
        self.assertTrue(generated)
        self.assertEqual(resumed["shape"]["expected_current_chunks"], 60)

    def test_building_owner_resumes_only_missing_deterministic_files(self):
        manifest, _ = generator.write_corpus(self.root, "tiny")
        source = (
            self.root
            / manifest["scopes"][0]["name"]
            / manifest["scopes"][0]["files"][0]["path"]
        )
        source.unlink()
        marker = self.root / spec.OWNER_MARKER_NAME
        marker.write_bytes(
            generator._json_bytes(generator._owner_value("tiny", "building"))
        )
        resumed, generated = generator.write_corpus(self.root, "tiny")
        self.assertTrue(generated)
        self.assertTrue(source.is_file())
        self.assertEqual(resumed, manifest)
        _, owner, _ = generator.load_owned_manifest(self.root)
        self.assertEqual(owner["state"], "ready")

    def test_source_tamper_and_manifest_binding_tamper_are_detected(self):
        manifest, _ = generator.write_corpus(self.root, "tiny")
        source = (
            self.root
            / manifest["scopes"][0]["name"]
            / manifest["scopes"][0]["files"][0]["path"]
        )
        data = bytearray(source.read_bytes())
        data[-1] = ord("x")
        source.write_bytes(data)
        with self.assertRaises(attestor.ScaleAttestationError):
            attestor.verify_source_files(self.root, manifest)

        # Restore source, then prove the ready marker binds exact manifest bytes.
        source.write_bytes(spec.render_document(0, 0, "tiny").encode("utf-8"))
        manifest_path = self.root / spec.MANIFEST_NAME
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
        value["needles"][0]["query"] = "tampered"
        manifest_path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaises(generator.ScaleGenerationError):
            generator.load_owned_manifest(self.root)

    def test_manifest_file_read_bound_is_bound_to_deterministic_bytes(self):
        manifest, _ = generator.write_corpus(self.root, "tiny")
        tampered = json.loads(json.dumps(manifest))
        tampered["scopes"][0]["files"][0]["bytes"] = 1_000_000_000
        manifest_raw = generator._json_bytes(tampered)
        (self.root / spec.MANIFEST_NAME).write_bytes(manifest_raw)
        (self.root / spec.OWNER_MARKER_NAME).write_bytes(
            generator._json_bytes(
                generator._owner_value(
                    "tiny", "ready", generator._sha256(manifest_raw)
                )
            )
        )
        with self.assertRaisesRegex(
            generator.ScaleGenerationError, "byte count mismatch"
        ):
            generator.load_owned_manifest(self.root)


class TestCurrentEligibleSql(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.addCleanup(self.conn.close)
        self.conn.executescript(
            """
            CREATE TABLE chunks (
                chunk_id TEXT PRIMARY KEY,
                raw_hash TEXT NOT NULL,
                tool_profile_hash TEXT NOT NULL,
                gen INTEGER NOT NULL,
                text_hash TEXT NOT NULL,
                text TEXT NOT NULL,
                heading_path TEXT NOT NULL,
                first_seen_commit TEXT
            );
            CREATE TABLE chunk_config_generations (
                association_rowid INTEGER PRIMARY KEY,
                chunk_id TEXT NOT NULL,
                chunking_config_hash TEXT NOT NULL
            );
            CREATE TABLE tree_entries (
                commit_hash TEXT NOT NULL,
                path TEXT NOT NULL,
                raw_hash TEXT NOT NULL,
                tool_profile_hash TEXT,
                gen INTEGER NOT NULL
            );
            CREATE VIRTUAL TABLE chunk_fts USING fts5(
                text, heading_path,
                content='chunks', content_rowid='rowid', tokenize='trigram'
            );
            """
        )

    def _chunk(self, rowid, chunk_id, raw_hash, profile, gen, first_seen="commit"):
        self.conn.execute(
            "INSERT INTO chunks(rowid, chunk_id, raw_hash, tool_profile_hash, gen, "
            "text_hash, text, heading_path, first_seen_commit) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, '[]', ?)",
            (
                rowid,
                chunk_id,
                raw_hash,
                profile,
                gen,
                f"text-{chunk_id}",
                f"scale text for {chunk_id}",
                first_seen,
            ),
        )

    def test_predicate_excludes_history_placeholders_wrong_config_and_frozen_rows(self):
        head = "sha256:" + "a" * 64
        config = "sha256:" + "b" * 64
        other = "sha256:" + "c" * 64
        profile = "sha256:" + "d" * 64
        self._chunk(1, "eligible", "sha256:r1", profile, 0)
        self._chunk(2, "historical", "sha256:r2", profile, 0)
        self._chunk(3, "placeholder", "sha256:r3", profile, 0, None)
        self._chunk(4, "wrong-config", "sha256:r4", profile, 0)
        self._chunk(5, "wrong-generation", "sha256:r5", profile, 1)
        self._chunk(6, "late-association", "sha256:r6", profile, 0)
        self._chunk(7, "late-chunk", "sha256:r7", profile, 0)

        for rowid, chunk_id, cfg in (
            (1, "eligible", config),
            (2, "historical", config),
            (3, "placeholder", config),
            (4, "wrong-config", other),
            (5, "wrong-generation", config),
            (6, "late-association", config),
            (7, "late-chunk", config),
        ):
            self.conn.execute(
                "INSERT INTO chunk_config_generations VALUES (?, ?, ?)",
                (rowid, chunk_id, cfg),
            )
        for index, (raw_hash, generation) in enumerate(
            (
                ("sha256:r1", 0),
                ("sha256:r3", 0),
                ("sha256:r4", 0),
                ("sha256:r5", 0),
                ("sha256:r6", 0),
                ("sha256:r7", 0),
            )
        ):
            self.conn.execute(
                "INSERT INTO tree_entries VALUES (?, ?, ?, ?, ?)",
                (head, f"document-{index}.md", raw_hash, profile, generation),
            )
        self.conn.execute("INSERT INTO chunk_fts(chunk_fts) VALUES('rebuild')")

        attestor.materialize_current_eligible(
            self.conn,
            head,
            config,
            max_chunk_rowid=6,
            max_association_rowid=5,
        )
        ids = [
            row[0]
            for row in self.conn.execute(
                "SELECT chunk_id FROM scale_current_eligible ORDER BY chunk_id"
            )
        ]
        self.assertEqual(ids, ["eligible"])
        self.assertEqual(attestor._fts_coverage(self.conn), (1, 1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
