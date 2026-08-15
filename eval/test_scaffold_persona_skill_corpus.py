import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import eval.scaffold_persona_skill_corpus as scaffold_module
from eval.scaffold_persona_skill_corpus import OWNER_FILE, PLAN_FILE, ScaffoldError, scaffold, scope_control_id


def plan_file(base: Path) -> Path:
    plan = base / "plan.json"
    plan.write_text(json.dumps({"schema":"kio.persona.plan/v2","fixture_id":"kio-persona-pc-v2","profile":"tiny","personas":[{"id":"p01","role":"engineer","scopes":[{"id":"home","path":"home"},{"id":"docs","path":"docs/api"}]},{"id":"p02","role":"analyst","scopes":[]}]}), encoding="utf-8")
    return plan


class PersonaSkillCorpusScaffoldTests(unittest.TestCase):
    def test_missing_descriptor_capability_fails_before_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            plan = plan_file(base)
            root = base / "corpus"
            with mock.patch.object(scaffold_module, "_O_NOFOLLOW", None):
                with self.assertRaisesRegex(ScaffoldError, "O_NOFOLLOW"):
                    scaffold(root, plan=plan)
            self.assertFalse(root.exists())

            with mock.patch.object(scaffold_module, "_O_DIRECTORY", None):
                with self.assertRaisesRegex(ScaffoldError, "O_DIRECTORY"):
                    scaffold(root, plan=plan)
            self.assertFalse(root.exists())

    def test_creates_only_rust_plan_topology_and_exact_owner_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); plan = plan_file(base)
            root = scaffold(base / "corpus", plan=plan)
            owner = json.loads((root / OWNER_FILE).read_text())
            self.assertEqual(owner["schema"], "kio.persona.skill-corpus/v4")
            self.assertEqual(owner["plan_sha256"], "sha256:" + hashlib.sha256(plan.read_bytes()).hexdigest())
            self.assertEqual((root / PLAN_FILE).read_bytes(), plan.read_bytes())
            self.assertTrue((root / "p01-engineer" / "home" / "docs/api").is_dir())
            self.assertTrue((root / "p01-engineer" / "_production/scopes" / scope_control_id("docs/api")).is_dir())
            self.assertFalse((root / "p99").exists())

    def test_resume_requires_same_exact_artifact_and_preserves_uncontrolled_work(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); plan = plan_file(base); root = scaffold(base / "corpus", plan=plan)
            note = root / "p01-engineer/home/note.txt"; note.write_text("keep")
            with self.assertRaises(ScaffoldError): scaffold(root, plan=plan)
            scaffold(root, plan=plan, resume=True)
            self.assertEqual(note.read_text(), "keep")
            changed = json.loads(plan.read_text()); changed["profile"] = "pilot"; plan.write_text(json.dumps(changed))
            with self.assertRaises(ScaffoldError): scaffold(root, plan=plan, resume=True)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_rejects_symlink_ancestry_and_control_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); victim = base / "victim"; victim.mkdir(); link = base / "link"; link.symlink_to(victim, target_is_directory=True)
            with self.assertRaises(ScaffoldError): scaffold(link / "corpus", plan=plan_file(base))
            root = scaffold(base / "corpus", plan=plan_file(base)); (root / OWNER_FILE).unlink(); (root / OWNER_FILE).symlink_to(base / "plan.json")
            with self.assertRaises(ScaffoldError): scaffold(root, plan=base / "plan.json", resume=True)

    def test_rejects_hardlinked_owner_without_touching_victim(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); plan = plan_file(base); root = scaffold(base / "corpus", plan=plan)
            victim = base / "victim.json"; victim.write_bytes((root / OWNER_FILE).read_bytes())
            (root / OWNER_FILE).unlink(); os.link(victim, root / OWNER_FILE)
            with self.assertRaises(ScaffoldError): scaffold(root, plan=plan, resume=True)
            self.assertTrue(victim.read_bytes())


if __name__ == "__main__": unittest.main()
