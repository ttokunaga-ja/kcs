import copy
import tempfile
import unittest
from pathlib import Path

from eval import generate_persona_corpus as generator
from eval import persona_artifacts
from eval import persona_prepare_receipt as receipt
from eval import persona_storage as storage

class Bundle:
    fixture_id = "kio-persona-pc-v2"
    profile = "tiny"
    plan_digest = "sha256:" + "1" * 64
    plan_sha256 = "sha256:" + "1" * 64
    schedule_sha256 = "sha256:" + "2" * 64
    render_sha256 = "sha256:" + "3" * 64

class PrepareReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.binding = self.root / "persona-root-binding.json"
        artifact = persona_artifacts.artifact_bundle_record(
            fixture_id=Bundle.fixture_id,
            profile=Bundle.profile,
            plan_digest=Bundle.plan_digest,
            plan_sha256=Bundle.plan_sha256,
            schedule_sha256=Bundle.schedule_sha256,
            render_sha256=Bundle.render_sha256,
        )
        artifact_sha = generator._digest(storage.canonical_json_bytes(artifact))
        binding = {"schema": "kio.persona.storage-root-binding/v2", "fixture_id": Bundle.fixture_id, "profile": "tiny", "replay_id": "replay-01", "destination_root": str(self.root), "filesystem_device": self.root.stat().st_dev, "plan_digest": Bundle.plan_digest, "plan_sha256": Bundle.plan_sha256, "schedule_sha256": Bundle.schedule_sha256, "render_sha256": Bundle.render_sha256, "artifact_bundle_sha256": artifact_sha, "sources_materialized": False, "actual_kio_evidence": False, "history_ready": False}
        self.binding.write_bytes(storage.canonical_json_bytes(binding))
        self.intent = receipt.build_prepare_receipt_intent(bundle=Bundle(), replay_id="replay-01", destination_root=self.root, root_binding_path=self.binding)

    def test_canonical_false_claim_receipt(self):
        value = receipt.build_prepare_receipt(self.intent)
        self.assertEqual(receipt.validate_prepare_receipt(value), value)
        self.assertTrue(receipt.prepare_receipt_sha256(value).startswith("sha256:"))
        self.assertFalse(value["claims"]["actual_kio_evidence"])
        self.assertFalse(value["claims"]["history_ready"])

    def test_rejects_mutation_or_bad_digest(self):
        changed = copy.deepcopy(self.intent); changed["claims"]["history_ready"] = True
        with self.assertRaises(receipt.PersonaPrepareReceiptError): receipt.validate_prepare_receipt_intent(changed)
        with self.assertRaises(receipt.PersonaPrepareReceiptError):
            receipt.build_prepare_receipt_intent(bundle=Bundle(), replay_id="replay-01", destination_root="relative", root_binding_path=self.binding, root_binding_sha256="bad")
        with self.assertRaises(receipt.PersonaPrepareReceiptError):
            receipt.build_prepare_receipt_intent(bundle=Bundle(), replay_id="replay-99", destination_root=self.root, root_binding_path=self.binding)

    def test_rejects_unknown_fields(self):
        changed = dict(self.intent); changed["unknown"] = False
        with self.assertRaises(receipt.PersonaPrepareReceiptError): receipt.validate_prepare_receipt_intent(changed)
