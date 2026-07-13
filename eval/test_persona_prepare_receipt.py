#!/usr/bin/env python3
"""Focused tests for non-executing persona W0 prepare receipts."""

from __future__ import annotations

import builtins
import copy
import hashlib
import subprocess
import unittest
from unittest import mock

from eval import generate_persona_corpus as generator
from eval import persona_fixture_spec as fixture_spec
from eval import persona_manifest as manifest
from eval import persona_prepare_receipt as receipt


def _hash(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _root_binding(*, profile, replay_id, destination_root, plan_sha256):
    return {
        "schema": generator.ROOT_BINDING_SCHEMA,
        "schema_version": 1,
        "fixture_id": fixture_spec.FIXTURE_ID,
        "profile": profile,
        "replay_id": replay_id,
        "destination_root": destination_root,
        "filesystem_device": 73,
        "plan_sha256": plan_sha256,
        "suite_manifest_sha256": _hash("suite-manifest"),
        "capacity_receipt_sha256": _hash("capacity-receipt"),
        "persona_manifest_root_sha256": _hash("persona-manifest-root"),
    }


def _compact_scope_hashes(persona_id):
    persona = fixture_spec.get_persona(persona_id)
    return [
        {
            "scope_key": scope["scope_key"],
            "init_receipt_sha256": _hash(
                f"init/{persona_id}/{scope['scope_key']}"
            ),
            "index_receipt_sha256": _hash(
                f"index/{persona_id}/{scope['scope_key']}"
            ),
        }
        for scope in fixture_spec.scope_specs(persona)
    ]


class TestPersonaPrepareReceipt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = "tiny"
        cls.replay_id = "replay-01"
        cls.destination_root = "/synthetic/persona-replay-01"
        cls.plan = generator.build_generation_plan(cls.profile)
        cls.plan_sha = generator.generation_plan_sha256(cls.plan)
        cls.binary_sha = _hash("trusted-kcs-binary-identity")
        cls.root_binding = _root_binding(
            profile=cls.profile,
            replay_id=cls.replay_id,
            destination_root=cls.destination_root,
            plan_sha256=cls.plan_sha,
        )
        cls.root_binding_sha = receipt.root_binding_sha256(cls.root_binding)
        cls.history_intent = receipt.build_canonical_history_prepare_intent(
            profile=cls.profile,
            replay_id=cls.replay_id,
            generation_plan_sha256=cls.plan_sha,
        )
        cls.person_bindings = [
            receipt.build_person_command_binding(
                profile=cls.profile,
                replay_id=cls.replay_id,
                destination_root=cls.destination_root,
                root_binding_sha256=cls.root_binding_sha,
                binary_identity_sha256=cls.binary_sha,
                persona_id=persona["id"],
                environment_receipt_sha256=_hash(
                    f"environment/{persona['id']}"
                ),
                scope_receipt_hashes=_compact_scope_hashes(persona["id"]),
            )
            for persona in fixture_spec.PERSONAS
        ]
        cls.prepare_intent = receipt.build_prepare_receipt_intent(
            profile=cls.profile,
            replay_id=cls.replay_id,
            destination_root=cls.destination_root,
            generation_plan_sha256=cls.plan_sha,
            root_binding=cls.root_binding,
            binary_identity_sha256=cls.binary_sha,
            history_prepare_intent=cls.history_intent,
            person_command_bindings=cls.person_bindings,
        )
        cls.root_receipt = receipt.build_prepare_receipt(cls.prepare_intent)

    def test_history_intent_is_compatible_with_existing_generator_contract(self):
        expected = generator.build_history_prepare_intent(
            self.plan, self.replay_id
        )
        self.assertEqual(
            receipt.canonical_generation_plan_sha256(self.profile),
            self.plan_sha,
        )
        self.assertEqual(self.history_intent, expected)
        self.assertEqual(
            receipt.validate_canonical_history_prepare_intent(
                self.history_intent
            ),
            expected,
        )
        self.assertEqual(
            self.root_binding_sha,
            generator._root_binding_sha256(self.root_binding),
        )

    def test_streamed_pilot_plan_sha_matches_materialized_plan(self):
        pilot = generator.build_generation_plan("pilot")
        self.assertEqual(
            receipt.canonical_generation_plan_sha256("pilot"),
            generator.generation_plan_sha256(pilot),
        )

    def test_streamed_full_plan_sha_matches_frozen_capacity_projection(self):
        self.assertEqual(
            receipt.canonical_generation_plan_sha256("full"),
            "1ebae5dc4bf39aeb3c0f417e3e57aca3ffe1904f5f4b3f11646fd32e9ffe5e82",
        )

    def test_exact_20_by_20_receipt_binds_every_upstream_hash(self):
        validated_intent = receipt.validate_prepare_receipt_intent(
            self.prepare_intent
        )
        validated = receipt.validate_prepare_receipt(self.root_receipt)
        self.assertEqual(validated_intent, self.prepare_intent)
        self.assertEqual(validated, self.root_receipt)
        self.assertEqual(
            validated["totals"],
            {
                "personas": 20,
                "scope_stores": 400,
                "device_states": 20,
                "physical_sources": 4_000,
                "planned_contract_contributor_chunks": (
                    self.plan["totals"]["planned_contract_chunks"]
                ),
            },
        )
        self.assertEqual(
            [person["persona_id"] for person in validated["persons"]],
            [persona["id"] for persona in fixture_spec.PERSONAS],
        )
        for person, binding in zip(
            validated["persons"], self.person_bindings, strict=True
        ):
            self.assertEqual(len(person["scopes"]), 20)
            self.assertEqual(person["device"]["expected_registry_rows"], 20)
            self.assertEqual(
                person["environment_receipt_sha256"],
                binding["environment_receipt_sha256"],
            )
            for scope, command in zip(
                person["scopes"], binding["scopes"], strict=True
            ):
                self.assertEqual(scope["scope_key"], command["scope_key"])
                self.assertEqual(
                    scope["generation_plan_sha256"], self.plan_sha
                )
                self.assertEqual(
                    scope["root_binding_sha256"], self.root_binding_sha
                )
                self.assertEqual(
                    scope["binary_identity_sha256"], self.binary_sha
                )
                self.assertEqual(
                    scope["environment_receipt_sha256"],
                    binding["environment_receipt_sha256"],
                )
                self.assertEqual(
                    scope["init_receipt_sha256"],
                    command["init_receipt_sha256"],
                )
                self.assertEqual(
                    scope["index_receipt_sha256"],
                    command["index_receipt_sha256"],
                )
        self.assertRegex(
            receipt.prepare_receipt_sha256(validated), r"[0-9a-f]{64}\Z"
        )
        self.assertLessEqual(
            len(manifest.canonical_json_bytes(validated)),
            receipt.MAX_ROOT_RECEIPT_BYTES,
        )

    def test_all_semantic_execution_and_mutation_claims_are_fixed_false(self):
        evidence_rows = [self.root_receipt["semantic_evidence"]]
        top_rows = [self.root_receipt]
        for person in self.root_receipt["persons"]:
            evidence_rows.extend((
                person["semantic_evidence"],
                person["device"]["semantic_evidence"],
            ))
            top_rows.extend((person, person["device"], *person["scopes"]))
            evidence_rows.extend(
                scope["semantic_evidence"] for scope in person["scopes"]
            )
        self.assertEqual(len(evidence_rows), 1 + 20 + 20 + 400)
        expected_checks = {
            "root": receipt.ROOT_SEMANTIC_CHECKS,
            "person": receipt.PERSON_SEMANTIC_CHECKS,
            "device": receipt.DEVICE_SEMANTIC_CHECKS,
            "scope": receipt.SCOPE_SEMANTIC_CHECKS,
        }
        for evidence in evidence_rows:
            self.assertEqual(
                evidence["schema"], receipt.SEMANTIC_EVIDENCE_SCHEMA
            )
            self.assertTrue(evidence["checks"])
            self.assertEqual(
                tuple(evidence["checks"]), expected_checks[evidence["kind"]]
            )
            self.assertTrue(all(value is False for value in evidence["checks"].values()))
            for field in (
                "semantic_checks_complete",
                "actual_kcs_chunks_attested",
                "opaque_runtime_contents_attested",
                "external_api_absence_attested",
                "history_ready_attested",
                "history_assignment_executable",
            ):
                self.assertIs(evidence[field], False)
        for row in top_rows:
            self.assertIs(row["canonical_fixture_projection_complete"], True)
            for field in (
                "filesystem_mutation_performed",
                "kcs_commands_executed_by_this_module",
                "external_api_execution_performed",
                "history_ready_attested",
                "history_assignment_executable",
            ):
                self.assertIs(row[field], False)

    def test_person_device_and_scope_schemas_validate_independently(self):
        person = receipt.build_person_prepare_receipt(
            self.prepare_intent, "p01"
        )
        device = receipt.build_device_prepare_receipt(
            self.prepare_intent, "p01"
        )
        scope_key = person["scopes"][0]["scope_key"]
        scope = receipt.build_scope_prepare_receipt(
            self.prepare_intent, "p01", scope_key
        )
        self.assertEqual(person, self.root_receipt["persons"][0])
        self.assertEqual(device, person["device"])
        self.assertEqual(scope, person["scopes"][0])
        self.assertEqual(
            receipt.validate_person_prepare_receipt(
                person, self.prepare_intent
            ),
            person,
        )
        self.assertEqual(
            receipt.validate_device_prepare_receipt(
                device, self.prepare_intent
            ),
            device,
        )
        self.assertEqual(
            receipt.validate_scope_prepare_receipt(
                scope, self.prepare_intent
            ),
            scope,
        )
        unknown = copy.deepcopy(scope)
        unknown["unknown"] = False
        with self.assertRaises(receipt.PersonaPrepareReceiptError):
            receipt.validate_scope_prepare_receipt(
                unknown, self.prepare_intent
            )

    def test_person_and_scope_cardinality_order_and_duplicates_fail_closed(self):
        with self.assertRaises(receipt.PersonaPrepareReceiptError):
            receipt.build_prepare_receipt_intent(
                profile=self.profile,
                replay_id=self.replay_id,
                destination_root=self.destination_root,
                generation_plan_sha256=self.plan_sha,
                root_binding=self.root_binding,
                binary_identity_sha256=self.binary_sha,
                history_prepare_intent=self.history_intent,
                person_command_bindings=self.person_bindings[:-1],
            )
        with self.assertRaises(receipt.PersonaPrepareReceiptError):
            receipt.build_prepare_receipt_intent(
                profile=self.profile,
                replay_id=self.replay_id,
                destination_root=self.destination_root,
                generation_plan_sha256=self.plan_sha,
                root_binding=self.root_binding,
                binary_identity_sha256=self.binary_sha,
                history_prepare_intent=self.history_intent,
                person_command_bindings=[*self.person_bindings, self.person_bindings[0]],
            )
        with self.assertRaises(receipt.PersonaPrepareReceiptError):
            receipt.build_prepare_receipt_intent(
                profile=self.profile,
                replay_id=self.replay_id,
                destination_root=self.destination_root,
                generation_plan_sha256=self.plan_sha,
                root_binding=self.root_binding,
                binary_identity_sha256=self.binary_sha,
                history_prepare_intent=self.history_intent,
                person_command_bindings=list(reversed(self.person_bindings)),
            )
        rows = _compact_scope_hashes("p01")
        for invalid in (rows[:-1], [*rows, rows[0]], list(reversed(rows))):
            with self.subTest(scope_rows=len(invalid)), self.assertRaises(
                receipt.PersonaPrepareReceiptError
            ):
                receipt.build_person_command_binding(
                    profile=self.profile,
                    replay_id=self.replay_id,
                    destination_root=self.destination_root,
                    root_binding_sha256=self.root_binding_sha,
                    binary_identity_sha256=self.binary_sha,
                    persona_id="p01",
                    environment_receipt_sha256=_hash("environment/p01"),
                    scope_receipt_hashes=invalid,
                )
        duplicate = copy.deepcopy(rows)
        duplicate[1]["init_receipt_sha256"] = duplicate[0][
            "init_receipt_sha256"
        ]
        with self.assertRaises(receipt.PersonaPrepareReceiptError):
            receipt.build_person_command_binding(
                profile=self.profile,
                replay_id=self.replay_id,
                destination_root=self.destination_root,
                root_binding_sha256=self.root_binding_sha,
                binary_identity_sha256=self.binary_sha,
                persona_id="p01",
                environment_receipt_sha256=_hash("environment/p01"),
                scope_receipt_hashes=duplicate,
            )

    def test_unknown_fields_strict_types_and_declared_file_order_fail(self):
        unknown = copy.deepcopy(self.prepare_intent)
        unknown["unknown"] = False
        with self.assertRaises(receipt.PersonaPrepareReceiptError):
            receipt.validate_prepare_receipt_intent(unknown)

        nested_unknown = copy.deepcopy(self.prepare_intent)
        nested_unknown["person_command_bindings"][0]["scopes"][0][
            "unknown"
        ] = False
        with self.assertRaises(receipt.PersonaPrepareReceiptError):
            receipt.validate_prepare_receipt_intent(nested_unknown)

        invalid_root = copy.deepcopy(self.root_binding)
        invalid_root["filesystem_device"] = True
        with self.assertRaises(receipt.PersonaPrepareReceiptError):
            receipt.build_prepare_receipt_intent(
                profile=self.profile,
                replay_id=self.replay_id,
                destination_root=self.destination_root,
                generation_plan_sha256=self.plan_sha,
                root_binding=invalid_root,
                binary_identity_sha256=self.binary_sha,
                history_prepare_intent=self.history_intent,
                person_command_bindings=self.person_bindings,
            )

        descriptors = [
            {
                "relative_path": ".kcs-persona-history/receipts/b.json",
                "raw_sha256": _hash("b"),
                "bytes": 1,
            },
            {
                "relative_path": ".kcs-persona-history/receipts/a.json",
                "raw_sha256": _hash("a"),
                "bytes": 1,
            },
        ]
        canonical = receipt.build_canonical_history_prepare_intent(
            profile=self.profile,
            replay_id=self.replay_id,
            generation_plan_sha256=self.plan_sha,
            receipt_files=descriptors,
        )
        self.assertEqual(
            [row["relative_path"] for row in canonical["receipt_files"]],
            sorted(row["relative_path"] for row in descriptors),
        )
        noncanonical = copy.deepcopy(canonical)
        noncanonical["receipt_files"].reverse()
        with self.assertRaises(receipt.PersonaPrepareReceiptError):
            receipt.validate_canonical_history_prepare_intent(noncanonical)

    def test_profile_replay_root_and_hash_substitutions_fail_closed(self):
        mutations = []
        profile = copy.deepcopy(self.prepare_intent)
        profile["profile"] = "full"
        mutations.append(profile)
        replay = copy.deepcopy(self.prepare_intent)
        replay["replay_id"] = "replay-02"
        mutations.append(replay)
        root = copy.deepcopy(self.prepare_intent)
        root["root_binding"]["destination_root"] = "/synthetic/other-root"
        mutations.append(root)
        command = copy.deepcopy(self.prepare_intent)
        command["person_command_bindings"][0]["scopes"][0][
            "index_receipt_sha256"
        ] = _hash("substituted-index-receipt")
        mutations.append(command)
        environment = copy.deepcopy(self.prepare_intent)
        environment["person_command_bindings"][0][
            "environment_receipt_sha256"
        ] = environment["person_command_bindings"][1][
            "environment_receipt_sha256"
        ]
        mutations.append(environment)
        for mutated in mutations:
            with self.subTest(mutation=len(mutations)), self.assertRaises(
                receipt.PersonaPrepareReceiptError
            ):
                receipt.validate_prepare_receipt_intent(mutated)

        final_substitution = copy.deepcopy(self.root_receipt)
        final_substitution["persons"][0]["scopes"][0][
            "index_receipt_sha256"
        ] = _hash("final-receipt-substitution")
        with self.assertRaises(receipt.PersonaPrepareReceiptError):
            receipt.validate_prepare_receipt(final_substitution)

        swapped_people = copy.deepcopy(self.root_receipt)
        swapped_people["persons"][0], swapped_people["persons"][1] = (
            swapped_people["persons"][1],
            swapped_people["persons"][0],
        )
        with self.assertRaises(receipt.PersonaPrepareReceiptError):
            receipt.validate_prepare_receipt(swapped_people)

    def test_coherently_rehashed_noncanonical_plan_and_unsafe_roots_fail_closed(self):
        fake_plan_sha = "f" * 64
        with self.assertRaisesRegex(
            receipt.PersonaPrepareReceiptError, "canonical suite plan"
        ):
            receipt.build_canonical_history_prepare_intent(
                profile=self.profile,
                replay_id=self.replay_id,
                generation_plan_sha256=fake_plan_sha,
            )

        for destination_root in (
            "/",
            "/synthetic/" + "a" * (receipt.MAX_PORTABLE_COMPONENT_BYTES + 1),
        ):
            with self.subTest(destination_root=destination_root), self.assertRaises(
                receipt.PersonaPrepareReceiptError
            ):
                receipt.build_person_command_binding(
                    profile=self.profile,
                    replay_id=self.replay_id,
                    destination_root=destination_root,
                    root_binding_sha256=self.root_binding_sha,
                    binary_identity_sha256=self.binary_sha,
                    persona_id="p01",
                    environment_receipt_sha256=_hash("environment/p01"),
                    scope_receipt_hashes=_compact_scope_hashes("p01"),
                )

    def test_validator_rejects_scope_overflow_before_row_iteration(self):
        overflow = copy.deepcopy(self.prepare_intent)
        overflow["person_command_bindings"][0]["scopes"] = [object()] * 21
        with mock.patch.object(
            receipt,
            "_exact_dict",
            wraps=receipt._exact_dict,
        ) as exact_dict, self.assertRaisesRegex(
            receipt.PersonaPrepareReceiptError, "exactly twenty"
        ):
            receipt.validate_prepare_receipt_intent(overflow)
        self.assertFalse(
            any(
                call.args[2] == "scope command binding"
                for call in exact_dict.call_args_list
            )
        )

    def test_root_receipt_and_declared_file_overflow_fail_before_rebuild(self):
        person_overflow = copy.deepcopy(self.root_receipt)
        person_overflow["persons"].append(person_overflow["persons"][0])
        with mock.patch.object(
            receipt,
            "build_prepare_receipt",
            side_effect=AssertionError("root receipt was rebuilt"),
        ) as rebuild, self.assertRaisesRegex(
            receipt.PersonaPrepareReceiptError, "cardinality"
        ):
            receipt.validate_prepare_receipt(person_overflow)
        rebuild.assert_not_called()

        placeholder = {
            "relative_path": ".kcs-persona-history/receipts/x.json",
            "raw_sha256": _hash("x"),
            "bytes": 1,
        }
        with mock.patch.object(
            receipt,
            "canonical_generation_plan_sha256",
            side_effect=AssertionError("plan digest was rebuilt"),
        ) as plan_digest, self.assertRaisesRegex(
            receipt.PersonaPrepareReceiptError, "counts overflow"
        ):
            receipt.build_canonical_history_prepare_intent(
                profile=self.profile,
                replay_id=self.replay_id,
                generation_plan_sha256=self.plan_sha,
                receipt_files=[placeholder] * 5_001,
                control_files=[placeholder] * 5_000,
            )
        plan_digest.assert_not_called()

    def test_true_semantic_or_execution_claims_can_never_validate(self):
        cases = []
        history_ready = copy.deepcopy(self.root_receipt)
        history_ready["history_ready_attested"] = True
        cases.append(history_ready)
        semantic = copy.deepcopy(self.root_receipt)
        semantic["persons"][0]["scopes"][0]["semantic_evidence"][
            "checks"
        ]["sqlite_integrity_attested"] = True
        cases.append(semantic)
        missing_check = copy.deepcopy(self.root_receipt)
        del missing_check["persons"][0]["device"]["semantic_evidence"][
            "checks"
        ]["registry_integrity_attested"]
        cases.append(missing_check)
        for invalid in cases:
            with self.assertRaises(receipt.PersonaPrepareReceiptError):
                receipt.validate_prepare_receipt(invalid)

        executable_intent = copy.deepcopy(self.prepare_intent)
        executable_intent["contracts"]["subprocess_execution"] = True
        with self.assertRaises(receipt.PersonaPrepareReceiptError):
            receipt.validate_prepare_receipt_intent(executable_intent)

    def test_composer_never_uses_all_person_plan_or_io_execution(self):
        with mock.patch.object(
            generator,
            "build_generation_plan",
            side_effect=AssertionError("all-person plan must not be built"),
        ), mock.patch.object(
            builtins,
            "open",
            side_effect=AssertionError("filesystem I/O is forbidden"),
        ), mock.patch.object(
            subprocess,
            "Popen",
            side_effect=AssertionError("subprocess execution is forbidden"),
        ):
            built = receipt.build_prepare_receipt(self.prepare_intent)
        self.assertEqual(built["totals"]["personas"], 20)
        self.assertEqual(built["totals"]["scope_stores"], 400)


if __name__ == "__main__":
    unittest.main()
