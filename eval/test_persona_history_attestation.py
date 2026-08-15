import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from eval import persona_history_attestation as attestation

class FilesystemAttestationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "root"; self.root.mkdir(); (self.root / "a.txt").write_bytes(b"a")
        self.record = self.root / "persona-materialization.json"; self.record.write_bytes(b'{"opaque":true}\n')
        import hashlib
        self.digest = "sha256:" + hashlib.sha256(self.record.read_bytes()).hexdigest()

    def test_stable_content_and_false_claims(self):
        content = attestation.walk_directory_content_root(self.root)
        self.assertTrue(content.content_root_sha256.startswith("sha256:"))
        value = attestation.build_filesystem_attestation(directory=self.root, materialization_sha256=self.digest)
        self.assertFalse(value["claims"]["actual_kio_evidence"])
        self.assertFalse(value["claims"]["history_ready"])
        self.assertEqual(value["materialization_sha256"], self.digest)

    def test_rejects_wrong_digest_and_record_links(self):
        with self.assertRaises(attestation.PersonaHistoryAttestationError):
            attestation.build_filesystem_attestation(directory=self.root, materialization_sha256="sha256:" + "0" * 64)
        other = self.root / "other"; other.write_bytes(self.record.read_bytes())
        self.record.unlink(); os.link(other, self.record)
        with self.assertRaises(attestation.PersonaHistoryAttestationError):
            attestation.build_filesystem_attestation(directory=self.root, materialization_sha256=self.digest)

    def test_rejects_links_hardlinks_and_bounds(self):
        link = self.root / "link"; link.symlink_to("a.txt")
        with self.assertRaises(attestation.PersonaHistoryAttestationError): attestation.walk_directory_content_root(self.root)
        link.unlink(); os.link(self.root / "a.txt", self.root / "b.txt")
        with self.assertRaises(attestation.PersonaHistoryAttestationError): attestation.walk_directory_content_root(self.root)
        (self.root / "b.txt").unlink()
        (self.root / "second.txt").write_bytes(b"b")
        with self.assertRaises(attestation.PersonaHistoryAttestationError):
            attestation.walk_directory_content_root(self.root, limits=attestation.AttestationLimits(max_files=1, max_entries=1, max_direct_entries=1, max_directories=1, max_total_file_bytes=1, max_file_bytes=1, max_depth=1, max_relative_path_bytes=16, max_components=1, read_size=512))

    def test_rejects_symlink_ancestor_and_special_entry(self):
        outside = Path(self.temp.name).resolve() / "outside"; outside.mkdir()
        alias = Path(self.temp.name).resolve() / "alias"; alias.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(attestation.PersonaHistoryAttestationError): attestation.walk_directory_content_root(alias)
        pipe = self.root / "pipe"; os.mkfifo(pipe)
        with self.assertRaises(attestation.PersonaHistoryAttestationError): attestation.walk_directory_content_root(self.root)

    @unittest.skipUnless(os.path.isdir("/dev/fd"), "descriptor directory unavailable")
    def test_nondirectory_ancestor_failure_does_not_leak_descriptors(self):
        regular = Path(self.temp.name).resolve() / "regular"
        regular.write_bytes(b"not a directory")
        before = len(os.listdir("/dev/fd"))
        for _ in range(100):
            with self.assertRaises(attestation.PersonaHistoryAttestationError):
                attestation.walk_directory_content_root(regular / "child")
        self.assertLessEqual(len(os.listdir("/dev/fd")), before + 1)

    def test_rejects_raw_path_alias(self):
        alias = str(self.root.parent) + "/./" + self.root.name
        with self.assertRaises(attestation.PersonaHistoryAttestationError):
            attestation.walk_directory_content_root(alias)
        with self.assertRaises(attestation.PersonaHistoryAttestationError):
            attestation.build_filesystem_attestation(directory=alias, materialization_sha256=self.digest)

    def test_rejects_root_swap_after_authority_open(self):
        replacement = Path(self.temp.name).resolve() / "replacement"; replacement.mkdir()
        (replacement / "persona-materialization.json").write_bytes(self.record.read_bytes())
        (replacement / "different.txt").write_bytes(b"different")
        displaced = Path(self.temp.name).resolve() / "displaced"
        original_walk = attestation.walk_directory_content_root
        def swap_then_walk(path, **kwargs):
            self.root.rename(displaced); replacement.rename(self.root)
            return original_walk(path, **kwargs)
        with mock.patch.object(attestation, "walk_directory_content_root", side_effect=swap_then_walk):
            with self.assertRaises(attestation.PersonaHistoryAttestationError):
                attestation.build_filesystem_attestation(directory=self.root, materialization_sha256=self.digest)

    def test_rejects_casefold_collision_and_depth(self):
        upper, lower = self.root / "A", self.root / "a"
        upper.write_bytes(b"a"); lower.write_bytes(b"b")
        if upper.lstat().st_ino != lower.lstat().st_ino:
            with self.assertRaises(attestation.PersonaHistoryAttestationError): attestation.walk_directory_content_root(self.root)
        upper.unlink()
        if lower.exists(): lower.unlink()
        nested = self.root / "one" / "two"; nested.mkdir(parents=True)
        with self.assertRaises(attestation.PersonaHistoryAttestationError):
            attestation.walk_directory_content_root(self.root, limits=attestation.AttestationLimits(max_entries=10, max_direct_entries=10, max_files=10, max_directories=10, max_total_file_bytes=100, max_file_bytes=100, max_depth=1, max_relative_path_bytes=100, max_components=10, read_size=512))
