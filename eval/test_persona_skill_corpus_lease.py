import os
import tempfile
import unittest
from pathlib import Path

from eval.persona_fixture_spec import get_persona
from eval.persona_skill_corpus_lease import (
    claim,
    read_lease,
    read_scope_lease,
    recover,
    release,
    scope_claim,
    scope_recover,
    scope_release,
)
from eval.scaffold_persona_skill_corpus import ScaffoldError, scaffold, scope_control_id


class PersonaSkillCorpusLeaseTests(unittest.TestCase):
    def test_claim_is_exclusive_and_release_requires_exact_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root = scaffold(Path(directory) / "corpus")
            first = claim(root, "p01", "session-one", "parent task")
            self.assertEqual(first["persona"], "p01-software-engineer")
            token_one = first["release_token"]
            self.assertEqual(read_lease(root, "p01")["session"], "session-one")
            self.assertNotIn("release_token", read_lease(root, "p01"))

            with self.assertRaises(ScaffoldError):
                claim(root, "p01", "session-two", None)
            with self.assertRaises(ScaffoldError):
                release(root, "p01", "wrong-token")

            released = release(root, "p01", token_one)
            self.assertEqual(released["session"], "session-one")
            second = claim(root, "p01", "session-two", None)
            self.assertEqual(second["session"], "session-two")
            with self.assertRaises(ScaffoldError):
                release(root, "p01", token_one)
            self.assertEqual(read_lease(root, "p01")["session"], "session-two")

    def test_explicit_recovery_requires_current_session_and_records_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = scaffold(Path(directory) / "corpus")
            claim(root, "p01", "abandoned-session", None)
            with self.assertRaises(ScaffoldError):
                recover(root, "p01", "different-session", "confirmed stopped")
            receipt = recover(
                root, "p01", "abandoned-session", "user confirmed writer stopped"
            )
            self.assertEqual(receipt["action"], "forced-recovery")
            self.assertEqual(
                claim(root, "p01", "replacement-session", None)["session"],
                "replacement-session",
            )
            recovery_log = (
                root
                / "p01-software-engineer"
                / "_production"
                / "lease-recovery.jsonl"
            ).read_text(encoding="utf-8")
            self.assertIn("user confirmed writer stopped", recovery_log)

    def test_rejects_unknown_persona_and_unsafe_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root = scaffold(Path(directory) / "corpus")
            with self.assertRaises(ScaffoldError):
                claim(root, "p99", "session", None)
            with self.assertRaises(ScaffoldError):
                claim(root, "p01", "contains spaces", None)

    def test_show_does_not_create_a_missing_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "mistyped-root"
            with self.assertRaises(ScaffoldError):
                read_lease(root, "p01")
            self.assertFalse(root.exists())

    def test_parent_can_assign_two_distinct_scopes_but_not_duplicate_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root = scaffold(Path(directory) / "corpus")
            parent = claim(root, "p01", "parent-one", "parent chat")
            scopes = get_persona("p01")["primary_paths"]
            first = scope_claim(root, "p01", scopes[0], "parent-one", "worker-a", "subagent a")
            second = scope_claim(root, "p01", scopes[1], "parent-one", "worker-b", "subagent b")
            self.assertEqual(first["parent_session"], "parent-one")
            self.assertEqual(second["scope_path"], scopes[1])
            self.assertNotIn("release_token", read_scope_lease(root, "p01", scopes[0]))
            with self.assertRaises(ScaffoldError):
                scope_claim(root, "p01", scopes[0], "parent-one", "worker-c", None)
            with self.assertRaises(ScaffoldError):
                release(root, "p01", parent["release_token"])
            with self.assertRaises(ScaffoldError):
                recover(root, "p01", "parent-one", "cannot abandon active workers")
            scope_dir = root / "p01-software-engineer" / "_production" / "scopes" / scope_control_id(scopes[0])
            self.assertTrue((scope_dir / "inventory.jsonl").is_file())
            self.assertTrue((root / "p01-software-engineer" / "home" / scopes[0]).is_dir())

    def test_scope_requires_its_active_parent_persona_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root = scaffold(Path(directory) / "corpus")
            scope = get_persona("p01")["primary_paths"][0]
            claim(root, "p01", "parent-one", None)
            with self.assertRaises(ScaffoldError):
                scope_claim(root, "p01", scope, "wrong-parent", "worker", None)
            with self.assertRaises(ScaffoldError):
                scope_claim(root, "p02", scope, "parent-one", "worker", None)
            lease = scope_claim(root, "p01", scope, "parent-one", "worker", None)
            with self.assertRaises(ScaffoldError):
                scope_release(root, "p01", scope, "wrong-parent", lease["release_token"])
            receipt = scope_recover(root, "p01", scope, "parent-one", "worker", "parent verified worker stopped")
            self.assertEqual(receipt["action"], "forced-recovery")

    @unittest.skipUnless(os.path.isdir("/dev/fd"), "descriptor directory unavailable")
    def test_repeated_scope_reads_do_not_leak_scope_directory_descriptors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = scaffold(Path(directory) / "corpus")
            scope = get_persona("p01")["primary_paths"][0]
            claim(root, "p01", "parent-one", None)
            scope_claim(root, "p01", scope, "parent-one", "worker", None)
            before = len(os.listdir("/dev/fd"))
            for _ in range(100):
                read_scope_lease(root, "p01", scope)
            self.assertLessEqual(len(os.listdir("/dev/fd")), before + 1)


if __name__ == "__main__":
    unittest.main()
