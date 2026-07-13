#!/usr/bin/env python3
"""Read-only tests for persona W0 runtime attestation primitives."""

from dataclasses import replace
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
import unicodedata
from unittest import mock

from eval import generate_persona_corpus as generator
from eval import persona_fixture_spec as fixture_spec
from eval import persona_history_attestation as attestation


def _semantic_evidence(
    kind,
    *,
    profile,
    persona_id,
    relative_path,
    content,
    scope_key=None,
    chunk_arithmetic=None,
):
    schema = (
        generator.RUNTIME_SCOPE_STORE_SEMANTIC_CONTRACT
        if kind == "scope_store"
        else generator.RUNTIME_DEVICE_STATE_SEMANTIC_CONTRACT
    )
    return attestation.KcsSemanticEvidence(
        schema=attestation.KCS_SEMANTIC_EVIDENCE_SCHEMA,
        schema_version=1,
        kind=kind,
        attestor_schema=schema,
        profile=profile,
        persona_id=persona_id,
        scope_key=scope_key,
        relative_path=relative_path,
        content_root_sha256=content.content_root_sha256,
        chunk_arithmetic=chunk_arithmetic,
        semantics_attested=True,
    )


def _valid_arithmetic(target=7, incidental=3):
    return attestation.validate_chunk_arithmetic({
        "expected_contract_contributor_chunks": target,
        "contract_contributor_chunks": target,
        "incidental_searchable_chunks": incidental,
        "raw_only_chunks": 0,
        "all_current_eligible_chunks": target + incidental,
    })


def _scope_contract(persona_id="p01", profile="tiny", ordinal=0):
    persona = fixture_spec.get_persona(persona_id)
    scope = fixture_spec.scope_specs(persona)[ordinal]
    relative = (
        f"devices/{persona_id}-{persona['role']}/home/{scope['relative_path']}/.kcs"
    )
    target = fixture_spec.scope_contributor_chunk_targets(
        persona, profile
    )[scope["scope_key"]]
    return scope["scope_key"], relative, _valid_arithmetic(target, 0)


class TestBoundedContentRoot(unittest.TestCase):
    def test_root_is_location_and_timestamp_independent_but_binds_tree_bytes(self):
        with tempfile.TemporaryDirectory(prefix="kcs-attest-a-") as first_tmp, \
                tempfile.TemporaryDirectory(prefix="kcs-attest-b-") as second_tmp:
            first = Path(first_tmp) / ".kcs"
            second = Path(second_tmp) / ".kcs"
            for root in (first, second):
                (root / "objects" / "aa").mkdir(parents=True)
                (root / "empty").mkdir()
                (root / "HEAD").write_bytes(b"sha256:" + b"1" * 64 + b"\n")
                (root / "objects" / "aa" / "object").write_bytes(b"payload")
            os.utime(second / "HEAD", ns=(1_000_000_000, 2_000_000_000))
            left = attestation.walk_directory_content_root(first)
            right = attestation.walk_directory_content_root(second)
            self.assertEqual(left.content_root_sha256, right.content_root_sha256)
            self.assertNotEqual(left.directory_inode, right.directory_inode)
            self.assertEqual(left.descendant_directories, 3)
            self.assertEqual(left.regular_files, 2)
            self.assertEqual(left.maximum_depth, 3)
            self.assertEqual(left.coverage, attestation.FILESYSTEM_COVERAGE)
            (second / "HEAD").write_bytes(b"sha256:" + b"2" * 64 + b"\n")
            changed = attestation.walk_directory_content_root(second)
            self.assertNotEqual(left.content_root_sha256, changed.content_root_sha256)

    @unittest.skipIf(os.name == "nt", "POSIX link/special semantics")
    def test_links_specials_noncanonical_names_and_collisions_fail_closed(self):
        builders = {
            "symlink": lambda root: (root / "link").symlink_to("target"),
            "hardlink": lambda root: (
                (root / "one").write_bytes(b"same"),
                os.link(root / "one", root / "two"),
            ),
            "fifo": lambda root: os.mkfifo(root / "pipe"),
            "case_collision": lambda root: (
                (root / "Name").write_bytes(b"a"),
                (root / "name").write_bytes(b"b"),
            ),
            "unicode_casefold_collision": lambda root: (
                (root / "Stra\u00dfe").write_bytes(b"a"),
                (root / "STRASSE").write_bytes(b"b"),
            ),
            "nfd": lambda root: (
                root / unicodedata.normalize("NFD", "café")
            ).write_bytes(b"x"),
            "c0": lambda root: (root / "bad\x01name").write_bytes(b"x"),
            "c1": lambda root: (root / "bad\u0085name").write_bytes(b"x"),
            "cf": lambda root: (root / "bad\u200bname").write_bytes(b"x"),
        }
        for label, build in builders.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / ".kcs"
                root.mkdir()
                if label == "symlink":
                    (root / "target").write_bytes(b"x")
                build(root)
                if label in (
                    "case_collision", "unicode_casefold_collision"
                ) and len(tuple(root.iterdir())) < 2:
                    # The default macOS filesystem collapses these names; the
                    # collision guard is exercised on case-sensitive CI.
                    continue
                with self.assertRaises(attestation.PersonaHistoryAttestationError):
                    attestation.walk_directory_content_root(root)

    def test_merkle_walk_does_not_materialize_whole_tree_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / ".kcs"
            root.mkdir()
            for index in range(100):
                (root / f"entry-{index:03d}").write_bytes(str(index).encode())
            with mock.patch.object(
                attestation.json,
                "dumps",
                side_effect=AssertionError("whole-tree JSON was materialized"),
            ):
                result = attestation.walk_directory_content_root(root)
            self.assertEqual(result.regular_files, 100)
            self.assertEqual(result.schema, attestation.CONTENT_ROOT_SCHEMA)

    def test_entry_byte_and_depth_limits_are_enforced(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / ".kcs"
            (root / "one" / "two").mkdir(parents=True)
            (root / "one" / "two" / "value").write_bytes(b"12345")
            cases = (
                replace(
                    attestation.DEFAULT_LIMITS,
                    max_entries=2,
                    max_files=1,
                    max_directories=2,
                ),
                replace(
                    attestation.DEFAULT_LIMITS,
                    max_total_file_bytes=4,
                    max_file_bytes=4,
                ),
                replace(attestation.DEFAULT_LIMITS, max_depth=2),
            )
            for limits in cases:
                with self.subTest(limits=limits), self.assertRaises(
                    attestation.PersonaHistoryAttestationError
                ):
                    attestation.walk_directory_content_root(root, limits=limits)

    def test_direct_entry_limit_accepts_exact_cap_and_rejects_next_entry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / ".kcs"
            root.mkdir()
            limits = replace(
                attestation.DEFAULT_LIMITS,
                max_entries=5,
                max_direct_entries=4,
                max_files=5,
                max_directories=1,
            )
            for index in range(4):
                (root / f"portable-{index}").write_bytes(b"value")
            exact = attestation.walk_directory_content_root(root, limits=limits)
            self.assertEqual(exact.regular_files, 4)

            (root / "portable-overflow").write_bytes(b"value")
            with self.assertRaisesRegex(
                attestation.PersonaHistoryAttestationError,
                "direct-entry bound",
            ):
                attestation.walk_directory_content_root(root, limits=limits)

    def test_invalid_limits_reject_bool_and_inconsistent_bounds(self):
        with self.assertRaises(attestation.PersonaHistoryAttestationError):
            attestation.AttestationLimits(max_entries=True)
        with self.assertRaises(attestation.PersonaHistoryAttestationError):
            attestation.AttestationLimits(max_entries=1)
        with self.assertRaisesRegex(
            attestation.PersonaHistoryAttestationError,
            "hard cap",
        ):
            attestation.AttestationLimits(
                max_entries=attestation.HARD_MAX_ENTRIES + 1,
                max_files=attestation.HARD_MAX_FILES,
                max_directories=attestation.HARD_MAX_DIRECTORIES,
            )
        with self.assertRaisesRegex(
            attestation.PersonaHistoryAttestationError,
            "hard cap",
        ):
            attestation.AttestationLimits(
                max_direct_entries=attestation.HARD_MAX_DIRECT_ENTRIES + 1,
            )

    @unittest.skipIf(os.name == "nt", "POSIX safe-open flags")
    def test_missing_safe_open_flags_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / ".kcs"
            root.mkdir()
            (root / "file").write_bytes(b"value")
            for flag in (
                "O_NOFOLLOW",
                "O_CLOEXEC",
                "O_DIRECTORY",
                "O_NONBLOCK",
            ):
                with self.subTest(flag=flag), mock.patch.object(
                    attestation.os, flag, 0
                ), self.assertRaisesRegex(
                    attestation.PersonaHistoryAttestationError,
                    "required safe-open flag",
                ):
                    attestation.walk_directory_content_root(root)

    @unittest.skipIf(os.name == "nt", "POSIX descriptor semantics")
    def test_root_descriptor_is_closed_when_post_open_fstat_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / ".kcs"
            root.mkdir()
            closed = []
            real_close = os.close

            def recording_close(descriptor):
                closed.append(descriptor)
                real_close(descriptor)

            with mock.patch.object(
                attestation.os,
                "fstat",
                side_effect=OSError("injected fstat failure"),
            ), mock.patch.object(
                attestation.os,
                "close",
                side_effect=recording_close,
            ), self.assertRaises(attestation.PersonaHistoryAttestationError):
                attestation.walk_directory_content_root(root)
            self.assertEqual(len(closed), 1)


class TestRuntimeCallbackReceipt(unittest.TestCase):
    def test_explicit_semantic_checker_produces_exact_accepted_nine_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            scope_key, relative, arithmetic = _scope_contract()
            runtime = root / relative
            runtime.mkdir(parents=True)
            (runtime / "HEAD").write_bytes(b"head")
            descriptor = {"kind": "scope_store", "relative_path": relative}

            def checker(_path, observed_descriptor, content):
                self.assertEqual(observed_descriptor, descriptor)
                self.assertEqual(content.regular_files, 1)
                return _semantic_evidence(
                    "scope_store",
                    profile="tiny",
                    persona_id="p01",
                    scope_key=scope_key,
                    relative_path=relative,
                    content=content,
                    chunk_arithmetic=arithmetic,
                )

            callback = attestation.make_runtime_attestor(
                checker, trusted_root=root
            )
            raw = callback(runtime, descriptor)
            self.assertEqual(set(raw), {
                "schema", "schema_version", "kind", "relative_path",
                "directory_device", "directory_inode", "directory_nlink",
                "attestor_schema", "content_root_sha256",
            })
            accepted = generator._attest_opaque_runtime_directories(
                root, [descriptor], callback
            )
            self.assertEqual(accepted["status"], "attested_by_callback")
            self.assertEqual(accepted["attested_directories"], 1)

    def test_content_root_cannot_be_promoted_without_typed_semantic_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            trusted = Path(temporary).resolve()
            scope_key, relative, arithmetic = _scope_contract()
            root = trusted / relative
            root.mkdir(parents=True)
            descriptor = {"kind": "scope_store", "relative_path": relative}
            for checker in (None, lambda *_args: True):
                with self.subTest(checker=checker), self.assertRaises(
                    attestation.PersonaHistoryAttestationError
                ):
                    attestation.build_runtime_directory_receipt(
                        root,
                        descriptor,
                        trusted_root=trusted,
                        semantic_checker=checker,
                    )

    def test_checker_mutation_is_detected_by_the_second_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            trusted = Path(temporary).resolve()
            scope_key, relative, arithmetic = _scope_contract()
            root = trusted / relative
            root.mkdir(parents=True)
            descriptor = {"kind": "scope_store", "relative_path": relative}

            def checker(path, _descriptor, _content):
                (path / "sqlite-wal").write_bytes(b"mutation")
                return _semantic_evidence(
                    "scope_store",
                    profile="tiny",
                    persona_id="p01",
                    scope_key=scope_key,
                    relative_path=relative,
                    content=_content,
                    chunk_arithmetic=arithmetic,
                )

            with self.assertRaisesRegex(
                attestation.PersonaHistoryAttestationError,
                "changed during KCS semantic checking",
            ):
                attestation.build_runtime_directory_receipt(
                    root,
                    descriptor,
                    trusted_root=trusted,
                    semantic_checker=checker,
                )

    @unittest.skipIf(os.name == "nt", "POSIX containment semantics")
    def test_formal_callback_rejects_symlinked_ancestor_and_outside_same_basename(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            trusted = base / "trusted"
            scope_key, relative, arithmetic = _scope_contract()
            runtime = trusted / relative
            runtime.mkdir(parents=True)
            alias = base / "alias"
            alias.symlink_to(trusted, target_is_directory=True)
            descriptor = {"kind": "scope_store", "relative_path": relative}

            def checker(_path, _descriptor, content):
                return _semantic_evidence(
                    "scope_store",
                    profile="tiny",
                    persona_id="p01",
                    scope_key=scope_key,
                    relative_path=relative,
                    content=content,
                    chunk_arithmetic=arithmetic,
                )

            with self.assertRaisesRegex(
                attestation.PersonaHistoryAttestationError,
                "ancestor|canonical|descriptor child",
            ):
                attestation.build_runtime_directory_receipt(
                    alias / relative,
                    descriptor,
                    trusted_root=alias,
                    semantic_checker=checker,
                )
            outside = base / "outside" / ".kcs"
            outside.mkdir(parents=True)
            with self.assertRaisesRegex(
                attestation.PersonaHistoryAttestationError,
                "descriptor child",
            ):
                attestation.build_runtime_directory_receipt(
                    outside,
                    descriptor,
                    trusted_root=trusted,
                    semantic_checker=checker,
                )


class TestChunkAndPartialReceipts(unittest.TestCase):
    def test_chunk_arithmetic_accepts_only_exact_role_equations(self):
        valid = _valid_arithmetic(120_000, 9)
        self.assertEqual(valid.contract_contributor_chunks, 120_000)
        cases = (
            {"contract_contributor_chunks": 119_999},
            {"raw_only_chunks": 1},
            {"all_current_eligible_chunks": 120_008},
            {"incidental_searchable_chunks": True},
        )
        baseline = {
            "expected_contract_contributor_chunks": 120_000,
            "contract_contributor_chunks": 120_000,
            "incidental_searchable_chunks": 9,
            "raw_only_chunks": 0,
            "all_current_eligible_chunks": 120_009,
        }
        for change in cases:
            value = {**baseline, **change}
            with self.subTest(change=change), self.assertRaises(
                attestation.PersonaHistoryAttestationError
            ):
                attestation.validate_chunk_arithmetic(value)
        with self.assertRaises(attestation.PersonaHistoryAttestationError):
            attestation.validate_chunk_arithmetic({**baseline, "extra": 0})

    def test_scope_and_person_receipts_are_irreducibly_partial(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            scope_path = base / "x" / ".kcs"
            device_path = base / "device" / ".kcs-eval-device"
            scope_path.mkdir(parents=True)
            device_path.mkdir(parents=True)
            scope = attestation.build_partial_scope_receipt(
                profile="tiny",
                persona_id="p01",
                scope_key="p01-primary-01",
                relative_path="devices/p01-software-engineer/home/x/.kcs",
                directory_content=attestation.walk_directory_content_root(scope_path),
                chunk_arithmetic=_valid_arithmetic(),
            )
            person = attestation.build_partial_person_receipt(
                profile="tiny",
                persona_id="p01",
                expected_contract_contributor_chunks=7,
                device_relative_path=(
                    "devices/p01-software-engineer/.kcs-eval-device"
                ),
                device_content=attestation.walk_directory_content_root(device_path),
                scopes=(scope,),
            )
            self.assertFalse(scope.history_ready_attested)
            self.assertFalse(scope.kcs_semantics_attested)
            self.assertFalse(person.history_ready_attested)
            self.assertFalse(person.scope_coverage_complete)
            with self.assertRaises(TypeError):
                attestation.PartialScopeReceipt(
                    schema=attestation.PARTIAL_SCOPE_SCHEMA,
                    schema_version=1,
                    profile="tiny",
                    persona_id="p01",
                    scope_key="x",
                    relative_path="x/.kcs",
                    directory_content=scope.directory_content,
                    chunk_arithmetic=scope.chunk_arithmetic,
                    history_ready_attested=True,
                )

    def test_scope_and_people_iterables_are_consumed_only_to_overflow_sentinel(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            scope_path = base / "x" / ".kcs"
            device_path = base / "device" / ".kcs-eval-device"
            scope_path.mkdir(parents=True)
            device_path.mkdir(parents=True)
            scope = attestation.build_partial_scope_receipt(
                profile="tiny",
                persona_id="p01",
                scope_key="p01-primary-01",
                relative_path="devices/p01-software-engineer/home/x/.kcs",
                directory_content=attestation.walk_directory_content_root(scope_path),
                chunk_arithmetic=_valid_arithmetic(),
            )
            scope_counter = [0]

            def endless_scopes():
                while True:
                    scope_counter[0] += 1
                    yield scope

            with self.assertRaisesRegex(
                attestation.PersonaHistoryAttestationError,
                "20-item bound",
            ):
                attestation.build_partial_person_receipt(
                    profile="tiny",
                    persona_id="p01",
                    expected_contract_contributor_chunks=7,
                    device_relative_path=(
                        "devices/p01-software-engineer/.kcs-eval-device"
                    ),
                    device_content=attestation.walk_directory_content_root(device_path),
                    scopes=endless_scopes(),
                )
            self.assertEqual(scope_counter[0], 21)

            person = attestation.build_partial_person_receipt(
                profile="tiny",
                persona_id="p01",
                expected_contract_contributor_chunks=7,
                device_relative_path="devices/p01-software-engineer/.kcs-eval-device",
                device_content=attestation.walk_directory_content_root(device_path),
                scopes=(scope,),
            )
            people_counter = [0]

            def endless_people():
                while True:
                    people_counter[0] += 1
                    yield person

            with self.assertRaisesRegex(
                attestation.PersonaHistoryAttestationError,
                "20-item bound",
            ):
                attestation.build_suite_receipt(
                    profile="tiny",
                    people=endless_people(),
                )
            self.assertEqual(people_counter[0], 21)


class TestSuiteCoverageGate(unittest.TestCase):
    @staticmethod
    def _content(identity, relative):
        return attestation.DirectoryContentRoot(
            schema=attestation.CONTENT_ROOT_SCHEMA,
            schema_version=2,
            coverage=attestation.FILESYSTEM_COVERAGE,
            directory_device=1,
            directory_inode=identity,
            directory_nlink=2,
            descendant_directories=0,
            regular_files=0,
            total_file_bytes=0,
            maximum_depth=0,
            content_root_sha256=hashlib.sha256(relative.encode()).hexdigest(),
        )

    @classmethod
    def _runtime(
        cls,
        kind,
        identity,
        relative,
        *,
        profile,
        persona_id,
        scope_key=None,
        chunk_arithmetic=None,
    ):
        content = cls._content(identity, relative)
        schema = (
            generator.RUNTIME_SCOPE_STORE_SEMANTIC_CONTRACT
            if kind == "scope_store"
            else generator.RUNTIME_DEVICE_STATE_SEMANTIC_CONTRACT
        )
        return content, attestation.RuntimeDirectoryReceipt(
            schema=generator.RUNTIME_DIRECTORY_ATTESTATION_SCHEMA,
            schema_version=1,
            kind=kind,
            relative_path=relative,
            directory_device=content.directory_device,
            directory_inode=content.directory_inode,
            directory_nlink=content.directory_nlink,
            attestor_schema=schema,
            content_root_sha256=content.content_root_sha256,
            semantic_evidence=_semantic_evidence(
                kind,
                profile=profile,
                persona_id=persona_id,
                scope_key=scope_key,
                relative_path=relative,
                content=content,
                chunk_arithmetic=chunk_arithmetic,
            ),
        )

    @classmethod
    def _complete_people(cls, *, profile="tiny", include_runtime=True):
        identity = 10
        people = []
        for persona in fixture_spec.PERSONAS:
            persona_id = persona["id"]
            slug = f"{persona_id}-{persona['role']}"
            scope_targets = fixture_spec.scope_contributor_chunk_targets(
                persona, profile
            )
            scopes = []
            for scope_spec in fixture_spec.scope_specs(persona):
                identity += 1
                relative = (
                    f"devices/{slug}/home/{scope_spec['relative_path']}/.kcs"
                )
                target = scope_targets[scope_spec["scope_key"]]
                arithmetic = _valid_arithmetic(target, 0)
                content, runtime = cls._runtime(
                    "scope_store",
                    identity,
                    relative,
                    profile=profile,
                    persona_id=persona_id,
                    scope_key=scope_spec["scope_key"],
                    chunk_arithmetic=arithmetic,
                )
                scopes.append(attestation.build_partial_scope_receipt(
                    profile=profile,
                    persona_id=persona_id,
                    scope_key=scope_spec["scope_key"],
                    relative_path=relative,
                    directory_content=content,
                    chunk_arithmetic=arithmetic,
                    runtime_callback_receipt=runtime if include_runtime else None,
                ))
            identity += 1
            device_relative = f"devices/{slug}/.kcs-eval-device"
            device_content, device_runtime = cls._runtime(
                "device_state",
                identity,
                device_relative,
                profile=profile,
                persona_id=persona_id,
            )
            people.append(attestation.build_partial_person_receipt(
                profile=profile,
                persona_id=persona_id,
                expected_contract_contributor_chunks=(
                    fixture_spec.contributor_plan(persona, profile)["target_chunks"]
                ),
                device_relative_path=device_relative,
                device_content=device_content,
                scopes=scopes,
                device_runtime_callback_receipt=(
                    device_runtime if include_runtime else None
                ),
            ))
        return tuple(people)

    def test_exact_400_scope_20_device_shape_stays_unready_without_callback_flag(self):
        people = self._complete_people()
        receipt = attestation.build_suite_receipt(
            profile="tiny",
            people=people,
            kcs_semantics_callback_attested=False,
        )
        self.assertEqual(receipt.personas, 20)
        self.assertEqual(receipt.scope_stores, 400)
        self.assertEqual(receipt.device_states, 20)
        self.assertTrue(receipt.filesystem_coverage_complete)
        self.assertFalse(receipt.semantic_coverage_attested)
        self.assertFalse(receipt.history_ready_attested)

        complete = attestation.build_suite_receipt(
            profile="tiny",
            people=people,
            kcs_semantics_callback_attested=True,
        )
        self.assertTrue(complete.semantic_coverage_attested)
        self.assertFalse(complete.history_ready_attested)
        self.assertEqual(complete.raw_only_chunks, 0)
        with self.assertRaises(attestation.PersonaHistoryAttestationError):
            replace(complete, history_ready_attested=True)

    def test_semantic_claim_rejects_missing_scope_device_or_typed_runtime_receipt(self):
        people = self._complete_people()
        incomplete_scope = replace(people[0], scopes=people[0].scopes[:-1])
        missing_device = replace(
            people[0], device_runtime_callback_receipt=None
        )
        no_runtime = self._complete_people(include_runtime=False)
        cases = (
            (incomplete_scope, *people[1:]),
            (missing_device, *people[1:]),
            no_runtime,
            people[:-1],
        )
        for case in cases:
            with self.subTest(scopes=sum(len(p.scopes) for p in case)), \
                    self.assertRaises(attestation.PersonaHistoryAttestationError):
                attestation.build_suite_receipt(
                    profile="tiny",
                    people=case,
                    kcs_semantics_callback_attested=True,
                )

    def test_profile_and_scope_quota_substitution_fail_closed(self):
        tiny_people = self._complete_people(include_runtime=False)
        for substituted_profile in ("pilot", "full"):
            with self.subTest(profile=substituted_profile), self.assertRaisesRegex(
                attestation.PersonaHistoryAttestationError,
                "receipt profile|canonical .* plan|canonical .* target|"
                "expected contributor total",
            ):
                attestation.build_suite_receipt(
                    profile=substituted_profile,
                    people=tiny_people,
                )

        first = tiny_people[0]
        left, right, *remaining = first.scopes
        left_target = left.chunk_arithmetic.contract_contributor_chunks
        right_target = right.chunk_arithmetic.contract_contributor_chunks
        shifted = replace(first, scopes=(
            replace(
                left,
                chunk_arithmetic=_valid_arithmetic(left_target + 1, 0),
            ),
            replace(
                right,
                chunk_arithmetic=_valid_arithmetic(right_target - 1, 0),
            ),
            *remaining,
        ))
        self.assertEqual(
            sum(
                scope.chunk_arithmetic.contract_contributor_chunks
                for scope in shifted.scopes
            ),
            first.expected_contract_contributor_chunks,
        )
        with self.assertRaisesRegex(
            attestation.PersonaHistoryAttestationError,
            "scope contributor chunks differ",
        ):
            attestation.build_suite_receipt(
                profile="tiny",
                people=(shifted, *tiny_people[1:]),
            )

    def test_valid_profile_bound_projections_are_distinct_and_still_unready(self):
        tiny = attestation.build_suite_receipt(
            profile="tiny",
            people=self._complete_people(profile="tiny", include_runtime=False),
        )
        pilot = attestation.build_suite_receipt(
            profile="pilot",
            people=self._complete_people(profile="pilot", include_runtime=False),
        )
        for receipt in (tiny, pilot):
            self.assertTrue(receipt.filesystem_coverage_complete)
            self.assertRegex(receipt.persona_plan_root_sha256, r"^[0-9a-f]{64}$")
            self.assertRegex(receipt.event_projection_root_sha256, r"^[0-9a-f]{64}$")
            self.assertFalse(receipt.history_ready_attested)
        self.assertNotEqual(
            tiny.persona_plan_root_sha256,
            pilot.persona_plan_root_sha256,
        )
        self.assertNotEqual(tiny.projection_root_sha256, pilot.projection_root_sha256)

    def test_scope_semantic_evidence_cannot_be_swapped_from_counts_or_identity(self):
        person = self._complete_people()[0]
        scope = person.scopes[0]
        runtime = scope.runtime_callback_receipt
        evidence = runtime.semantic_evidence
        target = scope.chunk_arithmetic.contract_contributor_chunks

        with self.assertRaisesRegex(
            attestation.PersonaHistoryAttestationError,
            "canonical plan",
        ):
            replace(
                evidence,
                chunk_arithmetic=_valid_arithmetic(target + 1, 0),
            )

        with self.assertRaisesRegex(
            attestation.PersonaHistoryAttestationError,
            "non-canonical scope",
        ):
            replace(evidence, scope_key="p01-primary-99")

        with self.assertRaisesRegex(
            attestation.PersonaHistoryAttestationError,
            "runtime directory callback receipt is invalid",
        ):
            replace(
                runtime,
                semantic_evidence=(
                    person.scopes[1]
                    .runtime_callback_receipt
                    .semantic_evidence
                ),
            )


if __name__ == "__main__":
    unittest.main()
