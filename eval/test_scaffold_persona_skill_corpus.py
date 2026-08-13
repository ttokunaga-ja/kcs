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
    WORKSPACE_FILE,
    _persona_initial_files,
    _scope_initial_files,
    _scope_workspace_text_initial,
    _workspace_text_v3_initial,
    _workspace_text_v2,
    _workspace_text,
    scaffold,
    scope_control_id,
)


class PersonaSkillCorpusScaffoldTests(unittest.TestCase):
    def test_creates_all_persona_homes_scopes_and_control_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "corpus"
            created = scaffold(root)
            root = created

            marker = json.loads((root / OWNER_FILE).read_text(encoding="utf-8"))
            self.assertEqual(marker["schema_version"], 3)
            self.assertEqual(len(marker["personas"]), 20)

            for persona in spec.PERSONAS:
                slug = f"{persona['id']}-{persona['role']}"
                home = root / slug / "home"
                control = root / slug / "_production"
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
                workspace = (root / slug / WORKSPACE_FILE).read_text(encoding="utf-8")
                self.assertIn(f"# {slug} workspace", workspace)
                self.assertIn("The parent chat session exclusively owns", workspace)
                self.assertIn("The parent holds each scope lease", workspace)
                self.assertIn("A subagent creates only the fixed files", workspace)
                self.assertIn("../../tasks/persona-skill-corpus/COMMON_RULES.md", workspace)
                self.assertIn("../../tasks/persona-skill-corpus/BATCH_PROTOCOL.md", workspace)
                self.assertIn(f"../../tasks/persona-skill-corpus/personas/{slug}.md", workspace)
                manifest = json.loads(
                    (control / "manifest.json").read_text(encoding="utf-8")
                )
                self.assertEqual(manifest["artifact_join_key"], "artifact_id")
                self.assertIn("image", manifest["format_variant_counts_200"])
                for relative_path in spec.all_scope_paths(persona):
                    scope = control / "scopes" / scope_control_id(relative_path)
                    self.assertTrue((scope / "assignment.json").is_file())
                    self.assertIn(relative_path, (scope / WORKSPACE_FILE).read_text(encoding="utf-8"))
                    self.assertEqual(
                        json.loads((scope / "manifest.json").read_text(encoding="utf-8"))["scope_path"],
                        relative_path,
                    )
                    assignment = json.loads(
                        (scope / "assignment.json").read_text(encoding="utf-8")
                    )
                    self.assertEqual(assignment["state"], "unassigned")
                    self.assertEqual(assignment["files"], [])
            self.assertEqual(
                {path.name for path in root.iterdir() if path.is_dir()},
                {f"{persona['id']}-{persona['role']}" for persona in spec.PERSONAS},
            )
            self.assertFalse((root / "devices").exists())
            self.assertFalse((root / "_production").exists())

    def test_resume_requires_exact_owner_and_preserves_existing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "corpus"
            scaffold(root)
            artifact = root / "p01-software-engineer" / "home" / "note.txt"
            artifact.write_text("keep", encoding="utf-8")

            with self.assertRaises(ScaffoldError):
                scaffold(root)
            scaffold(root, resume=True)
            self.assertEqual(artifact.read_text(encoding="utf-8"), "keep")

            (root / OWNER_FILE).write_text("{}\n", encoding="utf-8")
            with self.assertRaises(ScaffoldError):
                scaffold(root, resume=True)

    def test_resume_upgrades_exact_v2_empty_scaffold_and_preserves_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = scaffold(Path(directory) / "corpus")
            artifact = root / "p01-software-engineer" / "home" / "note.txt"
            artifact.write_text("keep", encoding="utf-8")
            marker = json.loads((root / OWNER_FILE).read_text(encoding="utf-8"))
            marker["schema_version"] = 2
            (root / OWNER_FILE).write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
            for persona in spec.PERSONAS:
                slug = f"{persona['id']}-{persona['role']}"
                (root / slug / WORKSPACE_FILE).write_text(_workspace_text_v2(persona), encoding="utf-8")
                control = root / slug / "_production"
                for name, payload in _persona_initial_files(persona, version=2).items():
                    (control / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            # A prior run may have upgraded a component before stopping; v2 root
            # ownership keeps the upgrade resumable.
            first_persona = spec.PERSONAS[0]
            first_slug = f"{first_persona['id']}-{first_persona['role']}"
            (root / first_slug / WORKSPACE_FILE).write_text(_workspace_text(first_persona), encoding="utf-8")
            first_control = root / first_slug / "_production"
            manifest = json.loads((first_control / "manifest.json").read_text(encoding="utf-8"))
            manifest["user_production_note"] = {"retain": True}
            (first_control / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
            narrative = json.loads((first_control / "narrative.json").read_text(encoding="utf-8"))
            narrative["parent_authored_anchor"] = "keep me"
            (first_control / "narrative.json").write_text(json.dumps(narrative) + "\n", encoding="utf-8")

            scaffold(root, resume=True)
            self.assertEqual(json.loads((root / OWNER_FILE).read_text(encoding="utf-8"))["schema_version"], 3)
            self.assertEqual(artifact.read_text(encoding="utf-8"), "keep")
            self.assertTrue((root / "p01-software-engineer" / "_production" / "scopes").is_dir())
            manifest = json.loads((first_control / "manifest.json").read_text(encoding="utf-8"))
            narrative = json.loads((first_control / "narrative.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], 3)
            self.assertEqual(manifest["user_production_note"], {"retain": True})
            self.assertEqual(narrative["schema_version"], 3)
            self.assertEqual(narrative["parent_authored_anchor"], "keep me")

    def test_v2_upgrade_rejects_hardlinked_owner_or_workspace_without_truncating_victim(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = scaffold(base / "corpus")
            marker = json.loads((root / OWNER_FILE).read_text(encoding="utf-8"))
            marker["schema_version"] = 2
            victim = base / "owner-victim.json"
            victim.write_text(json.dumps(marker) + "\n", encoding="utf-8")
            (root / OWNER_FILE).unlink()
            os.link(victim, root / OWNER_FILE)
            with self.assertRaises(ScaffoldError):
                scaffold(root, resume=True)
            self.assertEqual(victim.read_text(encoding="utf-8"), json.dumps(marker) + "\n")

            # Restore a valid marker, then independently exercise the workspace path.
            (root / OWNER_FILE).unlink()
            (root / OWNER_FILE).write_text(json.dumps(marker) + "\n", encoding="utf-8")
            persona = spec.PERSONAS[0]
            workspace = root / f"{persona['id']}-{persona['role']}" / WORKSPACE_FILE
            workspace_victim = base / "workspace-victim.md"
            workspace_victim.write_text(_workspace_text_v2(persona), encoding="utf-8")
            workspace.unlink()
            os.link(workspace_victim, workspace)
            with self.assertRaises(ScaffoldError):
                scaffold(root, resume=True)
            self.assertEqual(workspace_victim.read_text(encoding="utf-8"), _workspace_text_v2(persona))

    def test_resume_converges_initial_v3_workspace_and_empty_scope_assignment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = scaffold(Path(directory) / "corpus")
            persona = spec.PERSONAS[0]
            slug = f"{persona['id']}-{persona['role']}"
            relative_path = persona["primary_paths"][0]
            scope = (
                root
                / slug
                / "_production"
                / "scopes"
                / scope_control_id(relative_path)
            )
            (root / slug / WORKSPACE_FILE).write_text(
                _workspace_text_v3_initial(persona), encoding="utf-8"
            )
            (scope / WORKSPACE_FILE).write_text(
                _scope_workspace_text_initial(persona, relative_path),
                encoding="utf-8",
            )
            assignment = _scope_initial_files(persona, relative_path)[
                "assignment.json"
            ]
            assignment.pop("state")
            assignment.pop("files")
            (scope / "assignment.json").write_text(
                json.dumps(assignment, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            scaffold(root, resume=True)

            self.assertIn(
                "The parent holds each scope lease",
                (root / slug / WORKSPACE_FILE).read_text(encoding="utf-8"),
            )
            self.assertIn(
                "Read `assignment.json` before work",
                (scope / WORKSPACE_FILE).read_text(encoding="utf-8"),
            )
            upgraded = json.loads(
                (scope / "assignment.json").read_text(encoding="utf-8")
            )
            self.assertEqual(upgraded["state"], "unassigned")
            self.assertEqual(upgraded["files"], [])

    def test_tracked_scaffold_files_may_be_read_only_public_but_not_public_writable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = scaffold(Path(directory) / "corpus")
            marker = root / OWNER_FILE
            workspace = root / "p01-software-engineer" / WORKSPACE_FILE
            marker.chmod(0o644)
            workspace.chmod(0o644)
            scaffold(root, resume=True)

            workspace.chmod(0o666)
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

            persona = root / "p01-software-engineer"
            persona.rename(root / "persona-real")
            persona.symlink_to(victim, target_is_directory=True)
            with self.assertRaises(ScaffoldError):
                scaffold(root, resume=True)
            self.assertEqual(list(victim.iterdir()), [])

            persona.unlink()
            (root / "persona-real").rename(persona)
            status = root / "p01-software-engineer" / "_production" / "status.json"
            external = base / "external.json"
            external.write_text("{}\n", encoding="utf-8")
            status.unlink()
            status.symlink_to(external)
            with self.assertRaises(ScaffoldError):
                scaffold(root, resume=True)
            self.assertEqual(external.read_text(encoding="utf-8"), "{}\n")


if __name__ == "__main__":
    unittest.main()
