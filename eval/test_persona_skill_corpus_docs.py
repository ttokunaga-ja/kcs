import re
import unittest
from pathlib import Path

from eval import persona_fixture_spec as spec


ROOT = Path(__file__).resolve().parents[1]
DOC_ROOT = ROOT / "tasks" / "persona-skill-corpus"


class PersonaSkillCorpusDocsTests(unittest.TestCase):
    def test_every_persona_brief_matches_authoritative_counts_ratios_and_paths(self):
        persona_dir = DOC_ROOT / "personas"
        expected_files = {
            f"{persona['id']}-{persona['role']}.md" for persona in spec.PERSONAS
        }
        self.assertEqual(
            {path.name for path in persona_dir.glob("*.md")}, expected_files
        )

        for persona in spec.PERSONAS:
            path = persona_dir / f"{persona['id']}-{persona['role']}.md"
            text = path.read_text(encoding="utf-8")
            with self.subTest(persona=persona["id"]):
                self.assertIn(f"{persona['full_raw_files']:,}", text)
                for family, percentage in persona["format_percentages"].items():
                    self.assertRegex(
                        text,
                        rf"(?<![A-Za-z0-9_]){re.escape(family)}\s+{percentage}%",
                    )
                for primary_path in persona["primary_paths"]:
                    self.assertIn(f"`{primary_path}`", text)
                self.assertIn("SECONDARY_PATHS", text)
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
            "eval/persona_fixture_spec.py",
            "eval/scaffold_persona_skill_corpus.py",
            "eval/persona_skill_corpus_lease.py",
            "Documents",
            "PDF",
            "Spreadsheets",
            "Presentations",
            "ImageGen",
        ):
            self.assertIn(name, text)

    def test_batch_protocol_pins_variant_oracle_lease_and_artifact_join(self):
        batch = (DOC_ROOT / "BATCH_PROTOCOL.md").read_text(encoding="utf-8")
        layout = (DOC_ROOT / "PRODUCTION_LAYOUT.md").read_text(encoding="utf-8")
        self.assertIn('format_variant_counts(persona, "tiny")', batch)
        self.assertIn("lease.json", batch)
        self.assertIn("inventory.jsonl", layout)
        self.assertNotIn("inventory.json entries", layout)
        self.assertIn("artifact_id", layout)
        self.assertIn('result: "pass"', layout)

        p17 = (DOC_ROOT / "personas" / "p17-construction-project-manager.md").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("JPEG", p17)

    def test_runbooks_pin_direct_persona_layout_and_ownership_boundary(self):
        readme = (DOC_ROOT / "README.md").read_text(encoding="utf-8")
        rules = (DOC_ROOT / "COMMON_RULES.md").read_text(encoding="utf-8")
        batch = (DOC_ROOT / "BATCH_PROTOCOL.md").read_text(encoding="utf-8")
        layout = (DOC_ROOT / "PRODUCTION_LAYOUT.md").read_text(encoding="utf-8")
        handoff = (DOC_ROOT / "SESSION_HANDOFF.md").read_text(encoding="utf-8")
        self.assertIn("repository root's `persona-corpus/`", readme)
        self.assertIn("exactly twenty direct persona", layout)
        self.assertIn("no central `devices/` or `_production/`", layout)
        self.assertIn("<root>/<persona>/_production/", layout)
        for text in (readme, rules, batch, layout, handoff):
            self.assertIn("complete persona folder", text)


if __name__ == "__main__":
    unittest.main()
