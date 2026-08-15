import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC_ROOT = ROOT / "tasks" / "persona-skill-corpus"


class PersonaSkillCorpusDocsTests(unittest.TestCase):
    def test_persona_briefs_are_non_authoritative_and_complete(self):
        readme = (DOC_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("accepted Rust plan", readme)
        self.assertIn("not an alternate schema", readme)
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
            "kio-eval persona plan",
            "kio-eval persona scaffold",
            "python3 -m eval.persona_skill_corpus_lease",
            "Documents",
            "PDF",
            "Spreadsheets",
            "Presentations",
            "ImageGen",
        ):
            self.assertIn(name, text)

    def test_batch_protocol_pins_rust_plan_and_opaque_lease_boundary(self):
        batch = (DOC_ROOT / "BATCH_PROTOCOL.md").read_text(encoding="utf-8")
        self.assertIn("kio-eval persona plan", batch)
        self.assertIn("--owner-digest", batch)
        self.assertIn("--scope-id", batch)
        self.assertIn("home/<scope-path>", batch)
        self.assertNotIn("--scope ", batch)
        self.assertNotIn("format_variant_counts", batch)

        p17 = (DOC_ROOT / "personas" / "p17-construction-project-manager.md").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("JPEG", p17)

    def test_runbooks_pin_rust_only_materialization_and_scaffold_boundary(self):
        readme = (DOC_ROOT / "README.md").read_text(encoding="utf-8")
        batch = (DOC_ROOT / "BATCH_PROTOCOL.md").read_text(encoding="utf-8")
        handoff = (DOC_ROOT / "SESSION_HANDOFF.md").read_text(encoding="utf-8")
        rules = (DOC_ROOT / "COMMON_RULES.md").read_text(encoding="utf-8")
        layout = (DOC_ROOT / "PRODUCTION_LAYOUT.md").read_text(encoding="utf-8")
        self.assertIn("outside the repository", readme)
        self.assertIn("historical `persona-corpus/`", readme)
        self.assertIn("kio-eval persona materialize", readme)
        self.assertIn("kio-eval persona scaffold", readme)
        self.assertIn("persona-materialization.json", readme)
        self.assertIn("persona-workspace-owner.json", readme)
        self.assertIn("--owner-digest", handoff)
        self.assertIn("--scope-id", batch)
        self.assertIn("home path", handoff)
        self.assertIn("scope-claim", batch)
        self.assertIn("scope-release", batch)
        self.assertIn("--worker-session", batch)
        self.assertIn("people/<persona-id>-<role>/home/<scope-path>", layout)
        self.assertIn("_control/scopes/<persona-id>/", layout)
        self.assertIn("persona-workspace-owner.json", layout)
        self.assertIn("--scope-id", rules)
        self.assertIn("SKILL.md", rules)
        for text in (readme, batch, handoff, rules, layout):
            self.assertIn("scope", text.lower())

        for text in (readme, batch, handoff, rules, layout):
            self.assertNotIn("scaffold_persona_skill_corpus", text)
            self.assertNotIn("persona_artifacts", text)
            self.assertNotIn("generate_persona_corpus", text)
            self.assertNotIn("persona_prepare_receipt", text)
            self.assertNotIn("persona_root_lock", text)
            self.assertNotIn("persona_kio_runner", text)
            self.assertNotIn("_production/", text)
            self.assertNotIn("WORKSPACE.md", text)
            self.assertNotIn("assignment.json", text)
            self.assertNotIn("inventory.jsonl", text)
            self.assertNotIn("provenance.jsonl", text)
            self.assertNotIn("qa.jsonl", text)

        contract = (ROOT / "tasks" / "persona-pc-eval-contract.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("kio-eval persona materialize", contract)
        self.assertIn("kio-eval persona scaffold", contract)
        self.assertIn("kio.persona.materialization/v1", contract)
        self.assertIn("kio.persona.workspace-owner/v1", contract)
        for retired in ("root-lock", "command-runner", "prepare-receipt"):
            self.assertNotIn(retired, contract)


if __name__ == "__main__":
    unittest.main()
