#!/usr/bin/env python3
"""Contract and opt-in filesystem integration tests for persona W0 generation."""

import copy
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from eval import generate_persona_corpus as generator
from eval import persona_fixture_spec as spec
from eval import persona_manifest as manifest


class TestPersonaGenerationPlan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = generator.build_generation_plan("tiny")

    def test_plan_expands_twenty_people_four_hundred_scopes_and_exact_quotas(self):
        self.assertEqual(
            self.plan["totals"],
            {
                "personas": 20,
                "scope_shards": 400,
                "physical_sources": 4_000,
                "planned_contract_chunks": 4_131,
            },
        )
        self.assertEqual(len(self.plan["personas"]), 20)
        for person in self.plan["personas"]:
            self.assertEqual(len(person["scopes"]), 20)
            source_ids = []
            for scope in person["scopes"]:
                sources = scope["sources"]
                self.assertEqual(
                    dict(Counter(source["variant"] for source in sources)),
                    {
                        variant: count
                        for variant, count in scope["expected_variant_counts"].items()
                        if count
                    },
                )
                source_ids.extend(source["source_id"] for source in sources)
                self.assertEqual(len(sources), scope["expected_physical_rows"])
                self.assertEqual(
                    sum(
                        source["requested_contributor_chunks"]
                        for source in sources
                    ),
                    scope["expected_contract_chunks"],
                )
                for source in sources:
                    chunks = source["requested_contributor_chunks"]
                    if source["gate_role"] == "contract_contributor":
                        self.assertGreaterEqual(chunks, 1)
                        self.assertLessEqual(
                            chunks, spec.MAX_CONTRIBUTOR_CHUNKS_PER_FILE
                        )
                    else:
                        self.assertEqual(chunks, 0)
            self.assertEqual(
                source_ids,
                [
                    f"{person['persona_id']}-src-{index:06d}"
                    for index in range(1, person["raw_file_count"] + 1)
                ],
            )

    def test_plan_is_root_replay_and_clock_independent_canonical_json(self):
        raw = manifest.canonical_json_bytes(self.plan)
        self.assertNotIn(b"replay-01", raw)
        self.assertNotIn(str(Path.home()).encode(), raw)
        self.assertNotIn(b"mtime", raw)
        self.assertEqual(
            generator.generation_plan_sha256(self.plan),
            hashlib.sha256(raw).hexdigest(),
        )
        self.assertNotEqual(
            generator.generation_plan_sha256(self.plan),
            hashlib.sha256(raw + b"\n").hexdigest(),
        )
        self.assertEqual(json.loads(raw), self.plan)
        self.assertEqual(generator.build_generation_plan("tiny"), self.plan)

    def test_plan_rejects_scope_cell_and_source_quota_tampering(self):
        cases = []
        changed_cell = copy.deepcopy(self.plan)
        changed_cell["personas"][0]["scopes"][0]["expected_variant_counts"]["md"] += 1
        cases.append(changed_cell)
        changed_quota = copy.deepcopy(self.plan)
        source = next(
            source
            for scope in changed_quota["personas"][0]["scopes"]
            for source in scope["sources"]
            if source["gate_role"] == "contract_contributor"
        )
        source["requested_contributor_chunks"] += 1
        cases.append(changed_quota)
        changed_allocation = copy.deepcopy(self.plan)
        changed_allocation["personas"][0]["allocation"]["routing_affinity_total"] += 1
        cases.append(changed_allocation)
        changed_type = copy.deepcopy(self.plan)
        changed_type["schema_version"] = True
        cases.append(changed_type)
        changed_source_type = copy.deepcopy(self.plan)
        changed_source_type["personas"][0]["scopes"][0]["sources"][0][
            "version"
        ] = False
        cases.append(changed_source_type)
        for case in cases:
            with self.subTest(case=cases.index(case)), self.assertRaises(
                generator.PersonaGenerationError
            ):
                generator.validate_generation_plan(case)

    def test_plan_file_is_no_replace_canonical_and_duplicate_keys_fail(self):
        with tempfile.TemporaryDirectory(prefix="kcs-persona-plan-") as temporary:
            path = Path(temporary).resolve() / "plans" / "tiny.json"
            plan, written = generator.write_generation_plan(path, "tiny")
            self.assertTrue(written)
            self.assertEqual(plan, self.plan)
            self.assertEqual(generator.load_generation_plan(path), self.plan)
            before = path.stat().st_mtime_ns
            _plan, written = generator.write_generation_plan(path, "tiny")
            self.assertFalse(written)
            self.assertEqual(path.stat().st_mtime_ns, before)

            duplicate = Path(temporary).resolve() / "duplicate.json"
            duplicate.write_bytes(
                b'{"profile":"tiny","profile":"tiny"}\n'
            )
            with self.assertRaisesRegex(
                generator.PersonaGenerationError, "duplicate JSON key"
            ):
                generator.load_generation_plan(duplicate)

            inside_repo = Path(__file__).parents[1] / "persona-plan-must-not-land.json"
            with self.assertRaisesRegex(
                generator.PersonaGenerationError, "outside Git"
            ):
                generator.write_generation_plan(inside_repo, "tiny")
            self.assertFalse(inside_repo.exists())

    def test_pilot_plan_is_supported_but_physical_write_is_blocked(self):
        pilot = generator.build_generation_plan("pilot")
        self.assertEqual(pilot["totals"]["physical_sources"], 20_000)
        self.assertEqual(pilot["totals"]["planned_contract_chunks"], 240_000)
        with self.assertRaisesRegex(generator.PersonaGenerationError, "blocked"):
            generator.prepare_w0_suite(pilot)
        self.assertEqual(generator.WRITABLE_PROFILES, frozenset(("tiny",)))
        for profile in ("pilot", "full"):
            with self.subTest(profile=profile), mock.patch.object(
                generator, "validate_generation_plan"
            ):
                with self.assertRaisesRegex(generator.PersonaGenerationError, "blocked"):
                    generator.generate_replay(
                        {"profile": profile}, Path("/must-not-be-inspected"), "replay-01"
                    )

    def test_direct_script_startup(self):
        completed = subprocess.run(
            [sys.executable, "eval/generate_persona_corpus.py", "--help"],
            cwd=Path(__file__).parents[1],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("synthetic persona-PC W0 corpus", completed.stdout)

    def test_direct_plan_cli_writes_outside_git_and_reports_planned_only(self):
        with tempfile.TemporaryDirectory(prefix="kcs-persona-cli-") as temporary:
            plan_path = Path(temporary).resolve() / "tiny.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "eval/generate_persona_corpus.py",
                    "plan",
                    "--profile",
                    "tiny",
                    "--plan-out",
                    str(plan_path),
                ],
                cwd=Path(__file__).parents[1],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads(completed.stdout)
            self.assertEqual(report["physical_sources"], 4_000)
            self.assertEqual(report["planned_contract_chunks"], 4_131)
            self.assertFalse(report["actual_kcs_chunks_attested"])
            self.assertEqual(generator.load_generation_plan(plan_path), self.plan)

    def test_windows_physical_publication_is_blocked_until_durability_exists(self):
        with mock.patch.object(generator.os, "name", "nt"):
            for operation in (
                lambda: generator.generate_replay(
                    self.plan, "/not-inspected", "replay-01"
                ),
                lambda: generator.verify_replay_root(
                    self.plan, "/not-inspected", "replay-01"
                ),
            ):
                with self.assertRaisesRegex(
                    generator.PersonaGenerationError, "Windows.*durability"
                ):
                    operation()


class TestPreparedPersonaSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = generator.build_generation_plan("tiny")
        cls.prepared = generator.prepare_w0_suite(cls.plan)

    def test_prepared_suite_binds_all_rows_and_labels_chunks_as_planned(self):
        self.assertEqual(
            self.prepared["suite_manifest"]["totals"],
            {
                "personas": 20,
                "scope_shards": 400,
                "physical_sources": 4_000,
                "logical_items": 5_508,
                "planned_contract_chunks": 4_131,
            },
        )
        self.assertEqual(len(self.prepared["shards"]), 400)
        self.assertEqual(len(self.prepared["source_entries"]), 4_000)
        self.assertEqual(
            self.prepared["suite_manifest_sha256"],
            hashlib.sha256(self.prepared["suite_file"]).hexdigest(),
        )
        for shard in self.prepared["shards"]:
            self.assertEqual(
                shard["manifest"]["totals"]["sources_by_variant"],
                shard["scope"]["expected_variant_counts"],
            )

    def test_capacity_projection_covers_three_independent_replays(self):
        capacity = generator._capacity_plan(self.prepared).as_dict()
        self.assertEqual(capacity["replay_count"], 3)
        self.assertEqual(capacity["all_replays"]["physical_files"], 12_000)
        self.assertEqual(capacity["all_replays"]["current_chunks"], 12_393)
        self.assertGreater(capacity["required_peak"]["bytes"], 0)
        self.assertGreater(capacity["required_peak"]["inodes"], 4_000 * 3)

    def test_capacity_receipt_is_bound_to_destination_filesystem_and_limits(self):
        with tempfile.TemporaryDirectory(prefix="kcs-persona-capacity-") as temporary:
            base = Path(temporary).resolve()
            destination = base / "replay-01"
            receipt = generator._capacity_receipt(
                self.prepared,
                destination,
                "replay-01",
                byte_cap=generator.DEFAULT_TINY_BYTE_CAP,
                inode_cap=generator.DEFAULT_TINY_INODE_CAP,
                reserve_bytes=0,
                reserve_inodes=0,
            )
            limits = {
                "byte_cap": generator.DEFAULT_TINY_BYTE_CAP,
                "inode_cap": generator.DEFAULT_TINY_INODE_CAP,
                "reserve_bytes": 0,
                "reserve_inodes": 0,
            }
            generator._validate_capacity_receipt(
                self.prepared,
                receipt,
                "replay-01",
                expected_destination=destination,
                filesystem_path=base,
                expected_limits=limits,
            )
            wrong_destination = copy.deepcopy(receipt)
            wrong_destination["destination_root"] = str(base / "other")
            with self.assertRaises(generator.PersonaGenerationError):
                generator._validate_capacity_receipt(
                    self.prepared,
                    wrong_destination,
                    "replay-01",
                    expected_destination=destination,
                    filesystem_path=base,
                    expected_limits=limits,
                )
            wrong_limits = copy.deepcopy(receipt)
            wrong_limits["limits"]["byte_cap"] *= 2
            with self.assertRaises(generator.PersonaGenerationError):
                generator._validate_capacity_receipt(
                    self.prepared,
                    wrong_limits,
                    "replay-01",
                    expected_destination=destination,
                    filesystem_path=base,
                    expected_limits=limits,
                )


class TestHistoryPrepareEnvelope(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = generator.build_generation_plan("tiny")

    def test_intent_is_exact_root_independent_and_required_before_inspection(self):
        intent = generator.build_history_prepare_intent(
            self.plan, "replay-01"
        )
        self.assertEqual(intent["schema"], generator.HISTORY_PREPARE_INTENT_SCHEMA)
        self.assertEqual(len(intent["scope_store_directories"]), 400)
        self.assertEqual(len(intent["device_state_directories"]), 20)
        self.assertTrue(
            all(path.endswith("/.kcs") for path in intent["scope_store_directories"])
        )
        self.assertTrue(
            all(
                path.endswith("/.kcs-eval-device")
                for path in intent["device_state_directories"]
            )
        )
        raw = manifest.canonical_json_bytes(intent)
        self.assertNotIn(str(Path.home()).encode(), raw)
        validated = generator.validate_history_prepare_intent(
            self.plan, "replay-01", intent
        )
        self.assertEqual(validated, intent)
        self.assertIsNot(validated, intent)
        self.assertIsNot(
            validated["scope_store_directories"],
            intent["scope_store_directories"],
        )

        tampered = copy.deepcopy(intent)
        tampered["scope_store_directories"][0] += "/nested/.kcs"
        with self.assertRaisesRegex(
            generator.PersonaGenerationError, "canonical expansion"
        ):
            generator.validate_history_prepare_intent(
                self.plan, "replay-01", tampered
            )

        with mock.patch.object(
            generator, "verify_w0_immutable_content"
        ) as immutable:
            with self.assertRaisesRegex(
                generator.PersonaGenerationError, "intent.*missing|missing.*intent"
            ):
                generator.verify_history_prepare_envelope(
                    self.plan,
                    "/must-not-be-inspected",
                    "replay-01",
                    prepare_intent=None,
                )
            immutable.assert_not_called()

        if hasattr(os, "symlink") and os.name != "nt":
            with tempfile.TemporaryDirectory(prefix="kcs-prepare-ancestor-") as temporary:
                base = Path(temporary)
                real_parent = base / "real-parent"
                real_parent.mkdir()
                alias = base / "alias-parent"
                alias.symlink_to(real_parent, target_is_directory=True)
                with mock.patch.object(
                    generator, "_walk_history_prepare_envelope"
                ) as walk, mock.patch.object(
                    generator,
                    "prepare_w0_suite",
                    return_value={
                        "plan": self.plan,
                        "plan_sha256": generator.generation_plan_sha256(self.plan),
                    },
                ):
                    with self.assertRaises(generator.storage.PersonaStorageError):
                        generator.verify_history_prepare_envelope(
                            self.plan,
                            alias / "replay",
                            "replay-01",
                            prepare_intent=intent,
                        )
                    walk.assert_not_called()

    def test_declared_receipts_and_controls_are_hash_bound_and_cannot_enter_runtime(self):
        receipt = b'{"status":"prepared"}\n'
        control = b'{"wave":"W0"}\n'
        intent = generator.build_history_prepare_intent(
            self.plan,
            "replay-02",
            receipt_files=[{
                "relative_path": ".kcs-persona-history/receipts/w0.json",
                "raw_sha256": hashlib.sha256(receipt).hexdigest(),
                "bytes": len(receipt),
            }],
            control_files=[{
                "relative_path": ".kcs-persona-history/control/barrier.json",
                "raw_sha256": hashlib.sha256(control).hexdigest(),
                "bytes": len(control),
            }],
        )
        self.assertEqual(
            intent["receipt_files"][0]["relative_path"],
            ".kcs-persona-history/receipts/w0.json",
        )
        with tempfile.TemporaryDirectory(prefix="kcs-prepare-declared-") as temporary:
            root = Path(temporary)
            receipt_path = root / intent["receipt_files"][0]["relative_path"]
            control_path = root / intent["control_files"][0]["relative_path"]
            receipt_path.parent.mkdir(parents=True)
            control_path.parent.mkdir(parents=True)
            receipt_path.write_bytes(receipt)
            control_path.write_bytes(control)
            generator._verify_declared_prepare_files(
                root, intent["receipt_files"], "receipt"
            )
            generator._verify_declared_prepare_files(
                root, intent["control_files"], "control"
            )
            control_path.write_bytes(control + b"tamper")
            with self.assertRaisesRegex(
                generator.PersonaGenerationError, "differs from.*intent"
            ):
                generator._verify_declared_prepare_files(
                    root, intent["control_files"], "control"
                )

        scope_store = intent["scope_store_directories"][0]
        with self.assertRaisesRegex(
            generator.PersonaGenerationError,
            "opaque managed directory|canonical namespace",
        ):
            generator.build_history_prepare_intent(
                self.plan,
                "replay-02",
                receipt_files=[{
                    "relative_path": f"{scope_store}/receipt.json",
                    "raw_sha256": "0" * 64,
                    "bytes": 0,
                }],
            )
        with self.assertRaisesRegex(
            generator.PersonaGenerationError,
            "overlaps the W0|canonical namespace",
        ):
            generator.build_history_prepare_intent(
                self.plan,
                "replay-02",
                control_files=[{
                    "relative_path": generator.PLAN_FILE_NAME,
                    "raw_sha256": "0" * 64,
                    "bytes": 0,
                }],
            )
        with self.assertRaisesRegex(
            generator.PersonaGenerationError, "canonical namespace"
        ):
            generator.build_history_prepare_intent(
                self.plan,
                "replay-02",
                control_files=[{
                    "relative_path": "devices/p01-software-engineer/control.json",
                    "raw_sha256": "0" * 64,
                    "bytes": 0,
                }],
            )

    @staticmethod
    def _write_minimal_envelope(root):
        (root / "base" / "leaf" / ".kcs").mkdir(parents=True)
        (root / "devices" / "p01" / ".kcs-eval-device").mkdir(parents=True)
        (root / "base" / "leaf" / "source.txt").write_bytes(b"source")
        return (
            {"base/leaf/source.txt"},
            {
                "base", "base/leaf", "base/leaf/.kcs",
                "devices", "devices/p01", "devices/p01/.kcs-eval-device",
            },
            {"base/leaf/.kcs", "devices/p01/.kcs-eval-device"},
        )

    def test_envelope_walk_rejects_unknown_nested_managed_symlink_and_hardlink(self):
        with tempfile.TemporaryDirectory(prefix="kcs-prepare-walk-") as temporary:
            root = Path(temporary)
            files, directories, opaque = self._write_minimal_envelope(root)
            generator._walk_history_prepare_envelope(
                root, files, directories, opaque
            )
            (root / "base" / ".kcs").mkdir()
            with self.assertRaisesRegex(
                generator.PersonaGenerationError, "unexpected entry"
            ):
                generator._walk_history_prepare_envelope(
                    root, files, directories, opaque
                )

        with tempfile.TemporaryDirectory(prefix="kcs-prepare-link-") as temporary:
            root = Path(temporary)
            files, directories, opaque = self._write_minimal_envelope(root)
            target = root / "base" / "leaf" / "source.txt"
            alias = root / "base" / "leaf" / "alias.txt"
            os.link(target, alias)
            with self.assertRaisesRegex(
                generator.PersonaGenerationError, "hard-linked"
            ):
                generator._walk_history_prepare_envelope(
                    root,
                    files | {"base/leaf/alias.txt"},
                    directories,
                    opaque,
                )

        if hasattr(os, "symlink"):
            with tempfile.TemporaryDirectory(prefix="kcs-prepare-symlink-") as temporary:
                root = Path(temporary)
                files, directories, opaque = self._write_minimal_envelope(root)
                alias = root / "base" / "leaf" / "alias.txt"
                alias.symlink_to(root / "base" / "leaf" / "source.txt")
                with self.assertRaisesRegex(
                    generator.PersonaGenerationError,
                    "symlink/reparse/special",
                ):
                    generator._walk_history_prepare_envelope(
                        root,
                        files | {"base/leaf/alias.txt"},
                        directories,
                        opaque,
                    )

        if hasattr(os, "mkfifo"):
            with tempfile.TemporaryDirectory(prefix="kcs-prepare-special-") as temporary:
                root = Path(temporary)
                files, directories, opaque = self._write_minimal_envelope(root)
                fifo = root / "base" / "leaf" / "special.pipe"
                os.mkfifo(fifo)
                with self.assertRaisesRegex(
                    generator.PersonaGenerationError,
                    "symlink/reparse/special",
                ):
                    generator._walk_history_prepare_envelope(
                        root,
                        files | {"base/leaf/special.pipe"},
                        directories,
                        opaque,
                    )

    def test_opaque_runtime_is_explicitly_unattested_or_callback_attested(self):
        with tempfile.TemporaryDirectory(prefix="kcs-prepare-opaque-") as temporary:
            root = Path(temporary)
            _files, _directories, opaque = self._write_minimal_envelope(root)
            # Contents are deliberately not interpreted by the generic
            # envelope verifier, even when structurally suspicious.
            (root / "base" / "leaf" / ".kcs" / "arbitrary").write_bytes(b"x")
            descriptors = [
                {
                    "kind": "scope_store" if path.endswith("/.kcs") else "device_state",
                    "relative_path": path,
                }
                for path in sorted(opaque)
            ]
            unattested = generator._attest_opaque_runtime_directories(
                root, descriptors, None
            )
            self.assertEqual(unattested["status"], "opaque_unattested")
            self.assertIsNone(unattested["attestation_root_sha256"])
            observed = []

            def attest(path, descriptor):
                observed.append((path, descriptor))
                metadata = path.lstat()
                return {
                    "schema": generator.RUNTIME_DIRECTORY_ATTESTATION_SCHEMA,
                    "schema_version": 1,
                    "kind": descriptor["kind"],
                    "relative_path": descriptor["relative_path"],
                    "directory_device": metadata.st_dev,
                    "directory_inode": metadata.st_ino,
                    "directory_nlink": metadata.st_nlink,
                    "attestor_schema": (
                        generator.RUNTIME_SCOPE_STORE_SEMANTIC_CONTRACT
                        if descriptor["kind"] == "scope_store"
                        else generator.RUNTIME_DEVICE_STATE_SEMANTIC_CONTRACT
                    ),
                    "content_root_sha256": hashlib.sha256(
                        descriptor["relative_path"].encode()
                    ).hexdigest(),
                }

            attested = generator._attest_opaque_runtime_directories(
                root, descriptors, attest
            )
            self.assertEqual(attested["status"], "attested_by_callback")
            self.assertEqual(attested["attested_directories"], 2)
            self.assertRegex(attested["attestation_root_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(len(observed), 2)
            shared_receipt = {}

            def reused_receipt(path, descriptor):
                shared_receipt.clear()
                shared_receipt.update(attest(path, descriptor))
                return shared_receipt

            reused = generator._attest_opaque_runtime_directories(
                root, descriptors, reused_receipt
            )
            self.assertEqual(
                reused["attestation_root_sha256"],
                attested["attestation_root_sha256"],
            )
            with self.assertRaisesRegex(
                generator.PersonaGenerationError, "receipt did not bind"
            ):
                generator._attest_opaque_runtime_directories(
                    root, descriptors, lambda _path, _descriptor: True
                )

    def test_public_envelope_requires_all_canonical_runtime_roots_and_reports_limit(self):
        intent = generator.build_history_prepare_intent(
            self.plan, "replay-03"
        )
        runtime_paths = (
            intent["scope_store_directories"]
            + intent["device_state_directories"]
        )
        expected_directories = set()
        for relative in runtime_paths:
            pure = Path(relative)
            for parent in pure.parents:
                if str(parent) != ".":
                    expected_directories.add(parent.as_posix())
        with tempfile.TemporaryDirectory(prefix="kcs-public-envelope-") as temporary:
            root = Path(temporary)
            for relative in sorted(
                expected_directories,
                key=lambda value: (len(Path(value).parts), value),
            ):
                (root / relative).mkdir(exist_ok=True)
            for relative in runtime_paths:
                (root / relative).mkdir()
            immutable = {
                "root": str(root.absolute()),
                "profile": "tiny",
                "replay_id": "replay-03",
                "actual_kcs_chunks_attested": False,
                "immutable_w0_verified": True,
                "strict_full_tree_verified": False,
            }
            with mock.patch.object(
                generator,
                "verify_w0_immutable_content",
                return_value=immutable,
            ), mock.patch.object(
                generator,
                "_expected_layout",
                return_value=(set(), set(expected_directories)),
            ):
                result = generator.verify_history_prepare_envelope(
                    self.plan,
                    root,
                    "replay-03",
                    prepare_intent=intent,
                )
                def semantic_attestor(path, descriptor):
                    metadata = path.lstat()
                    return {
                        "schema": generator.RUNTIME_DIRECTORY_ATTESTATION_SCHEMA,
                        "schema_version": 1,
                        "kind": descriptor["kind"],
                        "relative_path": descriptor["relative_path"],
                        "directory_device": metadata.st_dev,
                        "directory_inode": metadata.st_ino,
                        "directory_nlink": metadata.st_nlink,
                        "attestor_schema": (
                            generator.RUNTIME_SCOPE_STORE_SEMANTIC_CONTRACT
                            if descriptor["kind"] == "scope_store"
                            else generator.RUNTIME_DEVICE_STATE_SEMANTIC_CONTRACT
                        ),
                        "content_root_sha256": hashlib.sha256(
                            descriptor["relative_path"].encode()
                        ).hexdigest(),
                    }

                callback_result = generator.verify_history_prepare_envelope(
                    self.plan,
                    root,
                    "replay-03",
                    prepare_intent=intent,
                    runtime_attestor=semantic_attestor,
                )
                mutated = [False]

                def mutating_attestor(path, descriptor):
                    receipt = semantic_attestor(path, descriptor)
                    if not mutated[0]:
                        (root / "callback-debris").write_bytes(b"not allowed")
                        mutated[0] = True
                    return receipt

                with self.assertRaisesRegex(
                    generator.PersonaGenerationError,
                    "unexpected entry|exceeds.*entry bound",
                ):
                    generator.verify_history_prepare_envelope(
                        self.plan,
                        root,
                        "replay-03",
                        prepare_intent=intent,
                        runtime_attestor=mutating_attestor,
                    )
            self.assertTrue(result["envelope_verified"])
            self.assertEqual(result["scope_store_directories"], 400)
            self.assertEqual(result["device_state_directories"], 20)
            self.assertEqual(result["runtime_contents_status"], "opaque_unattested")
            self.assertFalse(result["opaque_runtime_contents_attested"])
            self.assertFalse(result["history_ready_attested"])
            self.assertEqual(
                callback_result["runtime_contents_status"],
                "attested_by_callback",
            )
            self.assertTrue(callback_result["opaque_runtime_contents_attested"])
            self.assertEqual(callback_result["attested_runtime_directories"], 420)
            self.assertRegex(
                callback_result["runtime_attestation_root_sha256"],
                r"^[0-9a-f]{64}$",
            )


@unittest.skipUnless(
    os.environ.get("KCS_RUN_PERSONA_FS_INTEGRATION") == "1",
    "set KCS_RUN_PERSONA_FS_INTEGRATION=1 for the 8k-file publication test",
)
class TestPersonaFilesystemIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="kcs-persona-generator-")
        cls.base = Path(cls.temporary.name).resolve()
        cls.plan = generator.build_generation_plan("tiny")
        cls.first = cls.base / "replay-01"
        cls.second = cls.base / "replay-02"
        generator.generate_replay(
            cls.plan, cls.first, "replay-01", reserve_bytes=0, reserve_inodes=0
        )
        generator.generate_replay(
            cls.plan, cls.second, "replay-02", reserve_bytes=0, reserve_inodes=0
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @staticmethod
    def _snapshot(root):
        paths = [root, *root.rglob("*")]
        return {
            path.relative_to(root).as_posix(): (
                path.lstat().st_mtime_ns,
                path.lstat().st_ctime_ns,
                path.lstat().st_size,
            )
            for path in paths
        }

    @staticmethod
    def _immutable_hashes(root):
        result = {}
        for prefix in ("devices", "ledgers"):
            for path in (root / prefix).rglob("*"):
                if path.is_file():
                    result[path.relative_to(root).as_posix()] = hashlib.sha256(
                        path.read_bytes()
                    ).hexdigest()
        for name in (generator.PLAN_FILE_NAME, generator.SUITE_FILE_NAME):
            result[name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
        return result

    def test_two_roots_are_byte_identical_but_never_share_source_inodes(self):
        self.assertEqual(
            self._immutable_hashes(self.first), self._immutable_hashes(self.second)
        )
        first_files = {
            (path.stat().st_dev, path.stat().st_ino)
            for path in (self.first / "devices").rglob("*")
            if path.is_file() and path.name != generator.PERSONA_FILE_NAME
        }
        second_files = {
            (path.stat().st_dev, path.stat().st_ino)
            for path in (self.second / "devices").rglob("*")
            if path.is_file() and path.name != generator.PERSONA_FILE_NAME
        }
        self.assertEqual(len(first_files), 4_000)
        self.assertEqual(len(second_files), 4_000)
        self.assertTrue(first_files.isdisjoint(second_files))

    def test_y_history_prepare_runtime_preserves_w0_immutable_verification(self):
        for person in self.plan["personas"]:
            device = self.first / "devices" / person["device_slug"]
            (device / generator.DEVICE_STATE_DIRECTORY_NAME).mkdir()
            for scope in person["scopes"]:
                leaf = device / "home" / scope["relative_path"]
                (leaf / generator.SCOPE_STORE_DIRECTORY_NAME).mkdir()
        immutable = generator.verify_w0_immutable_content(
            self.plan, self.first, "replay-01"
        )
        self.assertTrue(immutable["immutable_w0_verified"])
        self.assertFalse(immutable["strict_full_tree_verified"])
        intent = generator.build_history_prepare_intent(
            self.plan, "replay-01"
        )
        with mock.patch.object(
            generator, "verify_w0_immutable_content", return_value=immutable
        ):
            envelope = generator.verify_history_prepare_envelope(
                self.plan,
                self.first,
                "replay-01",
                prepare_intent=intent,
            )
        self.assertTrue(envelope["envelope_verified"])
        self.assertEqual(envelope["runtime_contents_status"], "opaque_unattested")
        self.assertFalse(envelope["history_ready_attested"])
        with self.assertRaises(generator.PersonaGenerationError):
            generator.verify_replay_root(self.plan, self.first, "replay-01")

    def test_capacity_projection_covers_observed_allocated_blocks(self):
        receipt = json.loads(
            (self.first / generator.CAPACITY_FILE_NAME).read_text(encoding="utf-8")
        )
        allocated = sum(
            getattr(path.lstat(), "st_blocks", 0) * 512
            for path in (self.first, *self.first.rglob("*"))
        )
        if allocated == 0:  # Windows/rare filesystems do not expose st_blocks.
            self.skipTest("filesystem does not expose allocated block counts")
        self.assertLessEqual(
            allocated,
            receipt["capacity_plan"]["per_replay"]["retained_bytes"],
        )

    def test_ready_rerun_is_a_metadata_preserving_strict_noop(self):
        before = self._snapshot(self.first)
        result = generator.generate_replay(
            self.plan,
            self.first,
            "replay-01",
            reserve_bytes=0,
            reserve_inodes=0,
        )
        self.assertFalse(result["published"])
        self.assertTrue(result["strict_noop"])
        self.assertEqual(self._snapshot(self.first), before)

    def test_ready_rerun_rejects_different_capacity_limits(self):
        with self.assertRaisesRegex(
            generator.PersonaGenerationError, "capacity limits differ"
        ):
            generator.generate_replay(
                self.plan,
                self.first,
                "replay-01",
                byte_cap=1,
                reserve_bytes=0,
                reserve_inodes=0,
            )

    def test_z_raw_byte_tamper_is_detected(self):
        source = next(
            path
            for path in (self.second / "devices").rglob("*")
            if path.is_file() and path.name.startswith("p")
            and "-src-" in path.name
        )
        source.write_bytes(source.read_bytes() + b"tamper")
        with self.assertRaises(generator.PersonaGenerationError):
            generator.generate_replay(
                self.plan,
                self.second,
                "replay-02",
                reserve_bytes=0,
                reserve_inodes=0,
            )


if __name__ == "__main__":
    unittest.main()
