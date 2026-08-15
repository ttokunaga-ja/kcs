import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC_ROOT = ROOT / "tasks" / "persona-skill-corpus"


class PersonaSkillCorpusDocsTests(unittest.TestCase):
    def test_persona_briefs_are_non_authoritative_and_complete(self):
        readme = (DOC_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("accepted Rust `kio-eval persona plan` artifact", readme)
        self.assertIn("documents do not replace it", readme)
        persona_dir = DOC_ROOT / "personas"
        briefs = sorted(persona_dir.glob("p??-*.md"))
        self.assertEqual(len(briefs), 20)
        self.assertEqual(
            [path.name[:3] for path in briefs],
            [f"p{index:02d}" for index in range(1, 21)],
        )
        for path in briefs:
            text = path.read_text(encoding="utf-8")
            with self.subTest(persona=path.stem[:3]):
                self.assertTrue(
                    "## 完全配分" in text or "## 正式配分" in text
                )
                self.assertTrue(
                    "## 正規の一次パス" in text
                    or "## 正式 primary paths" in text
                )
                self.assertTrue(
                    "## 制作ルーティングと引渡し" in text
                    or "## 生成・受け渡し" in text
                )
                for skill_token in (
                    "Documents",
                    "PDF",
                    "Spreadsheets",
                    "Presentations",
                    "ImageGen",
                ):
                    self.assertIn(skill_token, text)
                self.assertIn("Kio 検索評価", text)

    def test_parent_handoff_names_all_required_runbooks_and_skills(self):
        text = (DOC_ROOT / "SESSION_HANDOFF.md").read_text(encoding="utf-8")
        for name in (
            "COMMON_RULES.md",
            "BATCH_PROTOCOL.md",
            "PERSONA_INDEX.md",
            "PRODUCTION_LAYOUT.md",
            "kio-eval persona plan",
            "python3 -m eval.scaffold_persona_skill_corpus",
            "python3 -m eval.persona_skill_corpus_lease",
            "Documents",
            "PDF",
            "Spreadsheets",
            "Presentations",
            "ImageGen",
        ):
            self.assertIn(name, text)

    def test_batch_protocol_pins_rust_plan_lease_and_artifact_join(self):
        batch = (DOC_ROOT / "BATCH_PROTOCOL.md").read_text(encoding="utf-8")
        layout = (DOC_ROOT / "PRODUCTION_LAYOUT.md").read_text(encoding="utf-8")
        self.assertIn("kio-eval persona plan", batch)
        self.assertNotIn("format_variant_counts", batch)
        self.assertIn("lease.json", batch)
        self.assertIn("inventory.jsonl", layout)
        self.assertNotIn("inventory.json entries", layout)
        self.assertIn("artifact_id", layout)
        self.assertIn('result: "pass"', layout)

        p17 = (DOC_ROOT / "personas" / "p17-construction-project-manager.md").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("JPEG", p17)

    def test_runbooks_pin_two_level_chat_and_scope_ownership_boundary(self):
        readme = (DOC_ROOT / "README.md").read_text(encoding="utf-8")
        rules = (DOC_ROOT / "COMMON_RULES.md").read_text(encoding="utf-8")
        batch = (DOC_ROOT / "BATCH_PROTOCOL.md").read_text(encoding="utf-8")
        layout = (DOC_ROOT / "PRODUCTION_LAYOUT.md").read_text(encoding="utf-8")
        handoff = (DOC_ROOT / "SESSION_HANDOFF.md").read_text(encoding="utf-8")
        self.assertIn("outside the repository", readme)
        self.assertIn("historical evidence", readme)
        self.assertIn("exactly twenty projected persona", layout)
        self.assertIn("no central", layout)
        self.assertIn("production-state directory", layout)
        self.assertIn("<root>/<persona>/_production/", layout)
        self.assertIn("One parent chat session", readme)
        self.assertIn("accepted `kio-eval persona plan` artifact", rules)
        self.assertIn("One subagent assignment owns one plan-defined leaf folder", batch)
        self.assertIn("_production/scopes/<scope-id>/", layout)
        self.assertIn("各Subagent assignmentはそのpersona内の1 leaf folder", handoff)
        self.assertIn("scope-claim", batch)
        self.assertIn("scope-release", batch)
        self.assertIn("--worker-session", batch)
        self.assertIn("Parent `release` and `recover` fail", batch)
        for text in (readme, rules, batch, layout, handoff):
            self.assertIn("scope", text.lower())


if __name__ == "__main__":
    unittest.main()
