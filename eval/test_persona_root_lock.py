import hashlib
import tempfile
import unittest
from pathlib import Path

from eval import generate_persona_corpus as generator
from eval import persona_root_lock as lock
from eval import persona_storage as storage

SHA = "sha256:" + "1" * 64

class RootLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "replay"; self.root.mkdir()
        bundle = type("Bundle", (), {"fixture_id": storage.FIXTURE_ID, "profile": "tiny", "plan_digest": SHA, "plan_sha256": SHA, "schedule_sha256": "sha256:" + "2" * 64, "render_sha256": "sha256:" + "3" * 64})()
        self.binding = generator._root_binding(bundle, "replay-01", self.root)
        raw = storage.canonical_json_bytes(self.binding); self.binding_sha = "sha256:" + hashlib.sha256(raw).hexdigest()
        (self.root / generator.ROOT_BINDING_FILE).write_bytes(raw)
        marker = storage.make_owner_marker(profile="tiny", replay_id="replay-01", state="ready", artifact_bundle_sha256=self.binding["artifact_bundle_sha256"], root_binding_sha256=self.binding_sha)
        (self.root / storage.OWNER_MARKER_NAME).write_bytes(storage.canonical_json_bytes(marker))

    def acquire(self):
        return lock.replay_root_lock(self.root, expected_profile="tiny", expected_replay_id="replay-01", expected_artifact_bundle_sha256=self.binding["artifact_bundle_sha256"], expected_root_binding_sha256=self.binding_sha)

    def test_acquires_and_revalidates(self):
        with self.acquire() as lease:
            self.assertEqual(lock.require_active_lease(lease).root, self.root)

    def test_rejects_binding_replacement(self):
        with self.assertRaises(lock.PersonaRootLockError):
            with self.acquire() as lease:
                changed = dict(self.binding); changed["history_ready"] = True
                (self.root / generator.ROOT_BINDING_FILE).unlink()
                (self.root / generator.ROOT_BINDING_FILE).write_bytes(storage.canonical_json_bytes(changed))
                lock.require_active_lease(lease)

    def test_rejects_internally_inconsistent_artifact_binding(self):
        changed = dict(self.binding)
        changed["schedule_sha256"] = "sha256:" + "9" * 64
        raw = storage.canonical_json_bytes(changed)
        self.binding = changed
        self.binding_sha = "sha256:" + hashlib.sha256(raw).hexdigest()
        (self.root / generator.ROOT_BINDING_FILE).write_bytes(raw)
        marker = storage.make_owner_marker(
            profile="tiny",
            replay_id="replay-01",
            state="ready",
            artifact_bundle_sha256=changed["artifact_bundle_sha256"],
            root_binding_sha256=self.binding_sha,
        )
        (self.root / storage.OWNER_MARKER_NAME).write_bytes(
            storage.canonical_json_bytes(marker)
        )
        with self.assertRaisesRegex(
            lock.PersonaRootLockError, "artifact bundle digest"
        ):
            with self.acquire():
                self.fail("inconsistent artifact binding acquired a root lock")
