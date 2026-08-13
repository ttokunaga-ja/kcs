import tempfile
import unittest
from pathlib import Path

from eval.persona_skill_corpus_lease import claim, read_lease, recover, release
from eval.scaffold_persona_skill_corpus import ScaffoldError, scaffold


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


if __name__ == "__main__":
    unittest.main()
