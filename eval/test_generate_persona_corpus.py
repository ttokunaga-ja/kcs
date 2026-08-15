import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from eval import generate_persona_corpus as generator
from eval import persona_artifacts
from eval import persona_storage as storage


def _raw(value):
    return (json.dumps(value, sort_keys=True) + "\n").encode()


class MaterializeTests(unittest.TestCase):
    def _artifacts(self, directory: Path, *, role: str = "test"):
        plan = _raw(
            {
                "schema": persona_artifacts.PLAN_SCHEMA,
                "fixture_id": persona_artifacts.FIXTURE_ID,
                "profile": "tiny",
                "personas": [
                    {
                        "id": "p01",
                        "role": role,
                        "scopes": [
                            {"id": "desktop", "path": "desktop/working"}
                        ],
                    }
                ],
            }
        )
        digest = "sha256:" + hashlib.sha256(plan).hexdigest()
        schedule = _raw(
            {"schema": persona_artifacts.SCHEDULE_SCHEMA, "plan_digest": digest}
        )
        render = _raw(
            {
                "schema": persona_artifacts.RENDER_SCHEMA,
                "fixture_id": persona_artifacts.FIXTURE_ID,
                "profile": "tiny",
                "plan_digest": digest,
            }
        )
        paths = []
        for name, raw in (
            ("plan.json", plan),
            ("schedule.json", schedule),
            ("render.json", render),
        ):
            path = directory / name
            path.write_bytes(raw)
            paths.append(path)
        return paths

    def test_materialize_is_exact_noop_on_matching_owned_root(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory).resolve()
            plan, schedule, render = self._artifacts(directory)
            root = directory / "output"
            first = generator.materialize(
                plan=plan,
                schedule=schedule,
                render=render,
                destination=root,
                replay_id="replay-01",
            )
            before = {
                path.name: (path.lstat().st_ino, path.read_bytes())
                for path in root.iterdir()
                if path.is_file()
            }
            second = generator.materialize(
                plan=plan,
                schedule=schedule,
                render=render,
                destination=root,
                replay_id="replay-01",
            )
            after = {
                path.name: (path.lstat().st_ino, path.read_bytes())
                for path in root.iterdir()
                if path.is_file()
            }
            self.assertTrue(first.published)
            self.assertFalse(second.published)
            self.assertEqual(after, before)

            binding = json.loads((root / generator.ROOT_BINDING_FILE).read_text())
            receipt = json.loads((root / generator.RECEIPT_FILE).read_text())
            artifact = json.loads(
                (root / generator.ARTIFACT_BUNDLE_FILE).read_text()
            )
            self.assertEqual(binding["schema"], generator.ROOT_BINDING_SCHEMA)
            self.assertEqual(
                receipt["schema"], generator.MATERIALIZATION_RECEIPT_SCHEMA
            )
            self.assertEqual(
                binding["artifact_bundle_sha256"],
                generator._digest(storage.canonical_json_bytes(artifact)),
            )
            self.assertEqual(binding["filesystem_device"], root.stat().st_dev)
            self.assertFalse(binding["sources_materialized"])
            self.assertFalse(binding["actual_kio_evidence"])
            self.assertFalse(binding["history_ready"])
            self.assertEqual(
                binding["plan_sha256"],
                "sha256:" + hashlib.sha256(plan.read_bytes()).hexdigest(),
            )

    def test_existing_extra_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory).resolve()
            plan, schedule, render = self._artifacts(directory)
            root = directory / "output"
            generator.materialize(
                plan=plan,
                schedule=schedule,
                render=render,
                destination=root,
                replay_id="replay-01",
            )
            (root / "foreign").write_text("x")
            with self.assertRaisesRegex(generator.PersonaGenerationError, "unexpected"):
                generator.materialize(
                    plan=plan,
                    schedule=schedule,
                    render=render,
                    destination=root,
                    replay_id="replay-01",
                )
            self.assertEqual((root / "foreign").read_text(), "x")

    def test_rejects_relative_destination_and_mismatched_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory).resolve()
            plan, schedule, render = self._artifacts(directory)
            with self.assertRaisesRegex(generator.PersonaGenerationError, "absolute"):
                generator.materialize(
                    plan=plan,
                    schedule=schedule,
                    render=render,
                    destination=Path("relative"),
                    replay_id="replay-01",
                )
            changed = json.loads(schedule.read_text())
            changed["plan_digest"] = "sha256:" + "0" * 64
            schedule.write_bytes(_raw(changed))
            with self.assertRaisesRegex(
                generator.PersonaGenerationError, "plan binding mismatch"
            ):
                generator.materialize(
                    plan=plan,
                    schedule=schedule,
                    render=render,
                    destination=directory / "never-created",
                    replay_id="replay-01",
                )
            self.assertFalse((directory / "never-created").exists())

    def test_rejects_unsafe_topology_before_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory).resolve()
            plan, schedule, render = self._artifacts(directory, role="../../victim")
            root = directory / "output"
            with self.assertRaisesRegex(generator.PersonaGenerationError, "topology"):
                generator.materialize(
                    plan=plan,
                    schedule=schedule,
                    render=render,
                    destination=root,
                    replay_id="replay-01",
                )
            self.assertFalse(root.exists())

    @unittest.skipUnless(hasattr(os, "link"), "hardlinks unavailable")
    def test_rejects_hardlinked_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory).resolve()
            plan, schedule, render = self._artifacts(directory)
            alias = directory / "plan-alias.json"
            os.link(plan, alias)
            with self.assertRaisesRegex(
                generator.PersonaGenerationError, "single-link"
            ):
                generator.materialize(
                    plan=plan,
                    schedule=schedule,
                    render=render,
                    destination=directory / "output",
                    replay_id="replay-01",
                )

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_rejects_symlinked_artifact_ancestor(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory).resolve()
            real = directory / "real"
            real.mkdir()
            plan, schedule, render = self._artifacts(real)
            alias = directory / "alias"
            alias.symlink_to(real, target_is_directory=True)
            with self.assertRaises(generator.PersonaGenerationError):
                generator.materialize(
                    plan=alias / plan.name,
                    schedule=schedule,
                    render=render,
                    destination=directory / "output",
                    replay_id="replay-01",
                )

    def test_artifact_read_tolerates_unrelated_sibling_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory).resolve()
            plan, _schedule, _render = self._artifacts(directory)
            original = persona_artifacts._read_fd
            created = False

            def create_sibling_then_read(descriptor, maximum):
                nonlocal created
                if not created:
                    created = True
                    (directory / "unrelated-sibling").write_bytes(b"unrelated\n")
                return original(descriptor, maximum)

            with mock.patch.object(
                persona_artifacts,
                "_read_fd",
                side_effect=create_sibling_then_read,
            ):
                raw, digest = persona_artifacts.read_exact_artifact(
                    plan, "plan artifact", persona_artifacts.MAX_PLAN_BYTES
                )
            self.assertEqual(raw, plan.read_bytes())
            self.assertEqual(digest, "sha256:" + hashlib.sha256(raw).hexdigest())


if __name__ == "__main__":
    unittest.main()
