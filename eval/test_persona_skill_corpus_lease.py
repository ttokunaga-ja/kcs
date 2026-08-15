import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from eval.persona_skill_corpus_lease import LeaseError, claim, read_scope_lease, recover, release, scope_claim, scope_recover, scope_release
import eval.persona_skill_corpus_lease as lease

class PersonaSkillCorpusLeaseTests(unittest.TestCase):
    def make(self, base):
        root=(base/"workspace").resolve(); (root/"_control/personas/alice").mkdir(parents=True)
        for scope in ("one","two"): (root/"_control/scopes/alice"/scope).mkdir(parents=True)
        for directory in (root/"_control",root/"_control/personas",root/"_control/scopes",root/"_control/scopes/alice"): os.chmod(directory,0o500)
        for directory in (root/"_control/personas/alice",root/"_control/scopes/alice/one",root/"_control/scopes/alice/two"): os.chmod(directory,0o700)
        raw=b'{"opaque":"owner bytes"}\n'; (root/"persona-workspace-owner.json").write_bytes(raw)
        return root,"sha256:"+hashlib.sha256(raw).hexdigest()
    def test_opaque_binding_parent_child_exclusivity_and_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root,digest=self.make(Path(directory)); parent=claim(root,"alice",digest,"parent",None)
            child=scope_claim(root,"alice","one",digest,"parent","worker",None)
            self.assertEqual(parent["owner_digest"],digest); self.assertEqual(child["scope_id"],"one")
            with self.assertRaises(LeaseError): release(root,"alice",digest,parent["release_token"])
            self.assertEqual(read_scope_lease(root,"alice","one",digest)["worker_session"],"worker")
            self.assertEqual(scope_recover(root,"alice","one",digest,"parent","worker","stopped")["action"],"forced-recovery")
            self.assertEqual(recover(root,"alice",digest,"parent","stopped")["action"],"forced-recovery")
    def test_wrong_replaced_and_hardlinked_owner_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory); root,digest=self.make(base)
            with self.assertRaises(LeaseError): claim(root,"alice","sha256:"+"0"*64,"s",None)
            owner=root/"persona-workspace-owner.json"; owner.write_bytes(b"replacement\n")
            with self.assertRaises(LeaseError): claim(root,"alice",digest,"s",None)
            owner.write_bytes(b'{"opaque":"owner bytes"}\n'); os.link(owner,base/"owner-link")
            with self.assertRaises(LeaseError): claim(root,"alice",digest,"s",None)
    def test_owner_replacement_after_binding_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory); root,digest=self.make(base); original=lease._new
            def write_then_replace(*args):
                original(*args); (root/"persona-workspace-owner.json").write_bytes(b"changed\n")
            with mock.patch.object(lease,"_new",write_then_replace):
                with self.assertRaises(LeaseError): claim(root,"alice",digest,"s",None)
    def test_bound_root_is_retained_after_name_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory); root,digest=self.make(base); alternate,_=self.make(base/"other"); original=lease._bind_owner
            def bind_then_replace(fd,expected):
                bound=original(fd,expected); root.rename(base/"original"); alternate.rename(root); return bound
            with mock.patch.object(lease,"_bind_owner",bind_then_replace): claim(root,"alice",digest,"s",None)
            self.assertTrue((base/"original/_control/personas/alice/lease.json").is_file())
            self.assertFalse((root/"_control/personas/alice/lease.json").exists())
    def test_unknown_persona_scope_and_unsafe_scope_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root,digest=self.make(Path(directory))
            with self.assertRaises(LeaseError): claim(root,"missing",digest,"s",None)
            claim(root,"alice",digest,"parent",None)
            for scope in ("missing","one/two"):
                with self.assertRaises(LeaseError): scope_claim(root,"alice",scope,digest,"parent","worker",None)
    @unittest.skipUnless(os.path.isdir("/dev/fd"),"descriptor directory unavailable")
    def test_reads_do_not_leak_descriptors(self):
        with tempfile.TemporaryDirectory() as directory:
            root,digest=self.make(Path(directory)); claim(root,"alice",digest,"parent",None); child=scope_claim(root,"alice","one",digest,"parent","worker",None)
            before=len(os.listdir("/dev/fd"))
            for _ in range(100): read_scope_lease(root,"alice","one",digest)
            self.assertLessEqual(len(os.listdir("/dev/fd")),before+1)
            scope_release(root,"alice","one",digest,"parent",child["release_token"])
    def test_unsupported_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root,digest=self.make(Path(directory))
            with mock.patch.object(lease,"_platform",side_effect=LeaseError("unsupported")):
                with self.assertRaises(LeaseError): claim(root,"alice",digest,"s",None)
    def test_sealed_static_parent_rejects_mode_drift_and_direct_injection(self):
        with tempfile.TemporaryDirectory() as directory:
            root,digest=self.make(Path(directory)); static=root/"_control/scopes/alice"
            with self.assertRaises(PermissionError): (static/"forged").mkdir()
            os.chmod(static,0o700)
            claim(root,"alice",digest,"s",None)
            with self.assertRaises(LeaseError): scope_claim(root,"alice","one",digest,"s","worker",None)
    @unittest.skipUnless(os.path.isdir("/dev/fd"),"descriptor directory unavailable")
    def test_recheck_failure_still_closes_every_descriptor(self):
        with tempfile.TemporaryDirectory() as directory:
            root,digest=self.make(Path(directory)); before=len(os.listdir("/dev/fd"))
            with mock.patch.object(lease,"_recheck_owner",side_effect=LeaseError("owner changed")):
                with self.assertRaises(LeaseError): claim(root,"alice",digest,"s",None)
            self.assertLessEqual(len(os.listdir("/dev/fd")),before+1)
    def test_label_reason_and_recovery_log_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            root,digest=self.make(Path(directory))
            with self.assertRaises(LeaseError): claim(root,"alice",digest,"s","x"*(lease.MAX_OWNER_LABEL_BYTES+1))
            parent=claim(root,"alice",digest,"s",None)
            with self.assertRaises(LeaseError): recover(root,"alice",digest,"s","x"*(lease.MAX_RECOVERY_REASON_BYTES+1))
            with mock.patch.object(lease,"MAX_RECOVERY_LOG_BYTES",1):
                with self.assertRaises(LeaseError): recover(root,"alice",digest,"s","stopped")
            self.assertTrue((root/"_control/personas/alice/lease.json").exists())
    def test_cli_uses_direct_scope_id_without_legacy_scope_alias(self):
        digest="sha256:"+"0"*64
        parsed=lease._parser().parse_args(["scope-show","--root","/tmp/workspace","--persona","p01","--owner-digest",digest,"--scope-id","p01-primary-01"])
        self.assertEqual(parsed.scope_id,"p01-primary-01")
        with mock.patch("sys.stderr"):
            with self.assertRaises(SystemExit):
                lease._parser().parse_args(["scope-show","--root","/tmp/workspace","--persona","p01","--owner-digest",digest,"--scope","p01-primary-01"])
    @unittest.skipUnless(sys.platform == "darwin", "Darwin fixed filesystem aliases only")
    def test_darwin_tmp_alias_binds_same_workspace(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            root,digest=self.make(Path(directory))
            alias=Path("/tmp")/root.relative_to("/private/tmp")
            claimed=claim(alias,"alice",digest,"s",None)
            self.assertEqual(claimed["owner_digest"],digest)
if __name__=="__main__": unittest.main()
