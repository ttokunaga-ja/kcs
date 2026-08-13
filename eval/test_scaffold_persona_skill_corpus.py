import json
import os
import tempfile
import unittest
from pathlib import Path

from eval import persona_fixture_spec as spec
from eval.scaffold_persona_skill_corpus import (
    OWNER_FILE,
    PRODUCTION_DIRS,
    ScaffoldError,
    scaffold,
)


class PersonaSkillCorpusScaffoldTests(unittest.TestCase):
    def test_creates_all_persona_homes_scopes_and_control_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "corpus"
            created = scaffold(root)
            root = created

            marker = json.loads((root / OWNER_FILE).read_text(encoding="utf-8"))
            self.assertEqual(marker["schema_version"], 1)
            self.assertEqual(len(marker["personas"]), 20)

            for persona in spec.PERSONAS:
                slug = f"{persona['id']}-{persona['role']}"
                home = root / "devices" / slug / "home"
                control = root / "_production" / slug
                for relative_path in spec.all_scope_paths(persona):
                    self.assertTrue((home / relative_path).is_dir())
                for relative_path in PRODUCTION_DIRS:
                    self.assertTrue((control / relative_path).is_dir())
                self.assertTrue((control / "status.json").is_file())
                self.assertTrue((control / "manifest.json").is_file())
                self.assertTrue((control / "narrative.json").is_file())
                self.assertTrue((control / "inventory.jsonl").is_file())
                self.assertTrue((control / "provenance.jsonl").is_file())
                self.assertTrue((control / "qa.jsonl").is_file())
                manifest = json.loads(
                    (control / "manifest.json").read_text(encoding="utf-8")
                )
                self.assertEqual(manifest["artifact_join_key"], "artifact_id")
                self.assertIn("image", manifest["format_variant_counts_200"])

    def test_resume_requires_exact_owner_and_preserves_existing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "corpus"
            scaffold(root)
            artifact = root / "devices" / "p01-software-engineer" / "home" / "note.txt"
            artifact.write_text("keep", encoding="utf-8")

            with self.assertRaises(ScaffoldError):
                scaffold(root)
            scaffold(root, resume=True)
            self.assertEqual(artifact.read_text(encoding="utf-8"), "keep")

            (root / OWNER_FILE).write_text("{}\n", encoding="utf-8")
            with self.assertRaises(ScaffoldError):
                scaffold(root, resume=True)

    def test_requires_existing_parent_and_rejects_non_directory_component(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            with self.assertRaises(ScaffoldError):
                scaffold(base / "missing" / "corpus")
            blocker = base / "blocker"
            blocker.write_text("not a directory", encoding="utf-8")
            with self.assertRaises(ScaffoldError):
                scaffold(blocker / "corpus")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_rejects_symlink_target_component(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            victim = base / "victim"
            victim.mkdir()
            link = base / "linked"
            link.symlink_to(victim, target_is_directory=True)
            with self.assertRaises(ScaffoldError):
                scaffold(link / "corpus")
            self.assertFalse((victim / "corpus").exists())

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_resume_rejects_internal_directory_and_control_file_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = scaffold(base / "corpus")
            victim = base / "victim"
            victim.mkdir()

            devices = root / "devices"
            devices.rename(root / "devices-real")
            devices.symlink_to(victim, target_is_directory=True)
            with self.assertRaises(ScaffoldError):
                scaffold(root, resume=True)
            self.assertEqual(list(victim.iterdir()), [])

            devices.unlink()
            (root / "devices-real").rename(devices)
            status = root / "_production" / "p01-software-engineer" / "status.json"
            external = base / "external.json"
            external.write_text("{}\n", encoding="utf-8")
            status.unlink()
            status.symlink_to(external)
            with self.assertRaises(ScaffoldError):
                scaffold(root, resume=True)
            self.assertEqual(external.read_text(encoding="utf-8"), "{}\n")


if __name__ == "__main__":
    unittest.main()
