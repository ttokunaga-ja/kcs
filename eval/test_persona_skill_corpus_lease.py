import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from eval.test_scaffold_persona_skill_corpus import plan_file
from eval.scaffold_persona_skill_corpus import ScaffoldError, scaffold, scope_control_id
from eval.persona_skill_corpus_lease import claim, read_lease, read_scope_lease, recover, release, scope_claim, scope_recover, scope_release
import eval.persona_skill_corpus_lease as lease_module

class PersonaSkillCorpusLeaseTests(unittest.TestCase):
    def make(self, base):
        plan=plan_file(base); return scaffold(base / "corpus", plan=plan)
    def test_claim_exclusive_token_release_and_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root=self.make(Path(directory)); first=claim(root,"p01","session-one",None)
            self.assertEqual(first["persona"],"p01-engineer"); self.assertNotIn("release_token",read_lease(root,"p01"))
            with self.assertRaises(ScaffoldError): claim(root,"p01","other",None)
            with self.assertRaises(ScaffoldError): release(root,"p01","wrong")
            release(root,"p01",first["release_token"]); claim(root,"p01","abandoned",None)
            receipt=recover(root,"p01","abandoned","writer stopped"); self.assertEqual(receipt["action"],"forced-recovery")
    def test_scope_membership_parent_and_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root=self.make(Path(directory)); parent=claim(root,"p01","parent",None)
            one=scope_claim(root,"p01","home","parent","worker",None)
            with self.assertRaises(ScaffoldError): scope_claim(root,"p01","nope","parent","worker2",None)
            with self.assertRaises(ScaffoldError): release(root,"p01",parent["release_token"])
            self.assertEqual(read_scope_lease(root,"p01","home")["worker_session"],"worker")
            receipt=scope_recover(root,"p01","home","parent","worker","stopped"); self.assertEqual(receipt["action"],"forced-recovery")
            scope_claim(root,"p01","docs/api","parent","worker2",None)
    @unittest.skipUnless(os.path.isdir("/dev/fd"), "descriptor directory unavailable")
    def test_reads_do_not_leak_descriptors(self):
        with tempfile.TemporaryDirectory() as directory:
            root=self.make(Path(directory)); claim(root,"p01","parent",None); lease=scope_claim(root,"p01","home","parent","worker",None)
            before=len(os.listdir("/dev/fd"))
            for _ in range(100): read_scope_lease(root,"p01","home")
            self.assertLessEqual(len(os.listdir("/dev/fd")),before+1)
            scope_release(root,"p01","home","parent",lease["release_token"])
    @unittest.skipUnless(hasattr(os,"symlink"), "symlink unavailable")
    def test_lease_rejects_control_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory); root=self.make(base); victim=base/"victim";victim.write_text("x")
            lock=root/"p01-engineer/_production/.lease.lock"; lock.unlink(); lock.symlink_to(victim)
            with self.assertRaises(ScaffoldError): claim(root,"p01","session",None)

    def test_claim_keeps_bound_root_when_path_is_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = self.make(base)
            alternate_plan = base / "alternate-plan.json"
            alternate_plan.write_text(json.dumps({
                "schema": "kio.persona.plan/v2",
                "fixture_id": "kio-persona-pc-v2",
                "profile": "tiny",
                "personas": [{"id": "p01", "role": "engineer", "scopes": [{"id": "other", "path": "other"}]}],
            }), encoding="utf-8")
            alternate = scaffold(base / "alternate", plan=alternate_plan)
            original_opener = lease_module._open_existing_root

            def open_then_replace(path):
                descriptor = original_opener(path)
                root.rename(base / "original")
                alternate.rename(root)
                return descriptor

            with mock.patch.object(lease_module, "_open_existing_root", open_then_replace):
                claim(root, "p01", "session", None)

            self.assertTrue((base / "original" / "p01-engineer" / "_production" / "lease.json").is_file())
            self.assertFalse((root / "p01-engineer" / "_production" / "lease.json").exists())

if __name__ == "__main__": unittest.main()
