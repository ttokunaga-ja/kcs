import os
import tempfile
import unittest
from pathlib import Path

from eval import persona_history_attestation as attestation

class Bundle:
    fixture_id = "kio-persona-pc-v2"; profile = "tiny"
    plan_digest = "sha256:" + "1" * 64
    plan_sha256 = "sha256:" + "1" * 64
    schedule_sha256 = "sha256:" + "2" * 64
    render_sha256 = "sha256:" + "3" * 64

class FilesystemAttestationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "root"; self.root.mkdir(); (self.root / "a.txt").write_bytes(b"a")

    def test_stable_content_and_false_claims(self):
        content = attestation.walk_directory_content_root(self.root)
        self.assertTrue(content.content_root_sha256.startswith("sha256:"))
        value = attestation.build_filesystem_attestation(bundle=Bundle(), root_binding_sha256="sha256:" + "4" * 64, directory=self.root)
        self.assertFalse(value["claims"]["actual_kio_evidence"])
        self.assertFalse(value["claims"]["history_ready"])

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
