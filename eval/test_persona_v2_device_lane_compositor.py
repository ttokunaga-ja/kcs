"""Focused regressions for the non-authorizing device-lane compositor."""

from __future__ import annotations

import copy
import hashlib
import inspect
import unittest
from unittest import mock

try:  # Support package and direct discovery modes.
    from . import persona_v2_contract as envelope
    from . import persona_v2_device_lane_compositor as producer
    from . import persona_v2_device_lane_compositor_validator as independent
except ImportError:  # pragma: no cover - direct discovery compatibility
    import persona_v2_contract as envelope
    import persona_v2_device_lane_compositor as producer
    import persona_v2_device_lane_compositor_validator as independent


class PersonaV2DeviceLaneCompositorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = producer.build_device_lane_compositor()
        cls.raw = producer.canonical_json_bytes(cls.value)

    def fresh(self):
        return copy.deepcopy(self.value)

    def assert_rejected(self, value):
        with self.assertRaises(
            independent.PersonaV2DeviceLaneCompositorValidationError
        ):
            independent.validate_device_lane_compositor(value)

    def test_identity_dependency_and_frozen_golden_are_exact(self):
        value = self.value
        self.assertEqual(value["artifact_schema"], producer.ARTIFACT_SCHEMA)
        self.assertEqual(value["artifact_schema_version"], 1)
        self.assertEqual(value["fixture_id"], "kio-persona-pc-v2")
        self.assertEqual(value["fixture_schema_version"], 2)
        self.assertLess(len(self.raw), producer.TARGET_COMPOSITOR_BYTES)
        expected = (
            41_099,
            "eb1a82d631b810ca96d90c84f9324263b4bb1018f0cde2a8339037a183d35bdf",
        )
        self.assertEqual(
            (producer.EXPECTED_CANONICAL_BYTES, producer.EXPECTED_SHA256),
            expected,
        )
        self.assertEqual(
            (independent.EXPECTED_CANONICAL_BYTES, independent.EXPECTED_SHA256),
            expected,
        )
        self.assertEqual(len(self.raw), expected[0])
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), expected[1])

        pin = value["dependency_pin"]
        self.assertEqual(pin["dependency_id"], "persona-envelope-v2")
        self.assertEqual(pin["canonical_bytes"], 71_979)
        self.assertEqual(
            pin["sha256"],
            "12a5f175cbcd9b1ea9886c8a8e3b673b857f6b314ba48c9b71e6b279150244a7",
        )

    def test_exact_twenty_roles_sixty_roots_and_designated_candidate_paths(self):
        personas = self.value["personas"]
        self.assertEqual(len(personas), 20)
        self.assertEqual(
            [(row["persona_id"], row["role"], row["full_w0_source_files_per_replay"])
             for row in personas],
            list(independent.PERSONA_ROWS),
        )

        device_roots = []
        registry_roots = []
        for row in personas:
            persona_id = row["persona_id"]
            role_slug = row["role_slug"]
            self.assertEqual(role_slug, row["role"])
            mappings = row["formal_replay_mappings"]
            self.assertEqual(len(mappings), 3)
            for mapping, replay_id in zip(mappings, producer.REPLAY_IDS):
                device = f"{replay_id}/devices/{persona_id}-{role_slug}"
                self.assertEqual(mapping["device_root"], device)
                self.assertEqual(mapping["home_root"], f"{device}/home")
                self.assertEqual(
                    mapping["registry_root"], f"{device}/.kio-eval-device"
                )
                self.assertEqual(mapping["formal_scope_count"], 20)
                self.assertTrue(mapping["fresh_w0_build_required"])
                self.assertFalse(mapping["physical_materialization_claimed"])
                device_roots.append(device)
                registry_roots.append(mapping["registry_root"])

            designated = row["designated_lane_candidate_mapping"]
            self.assertEqual(designated["replay_id"], "formal-replay-01")
            self.assertEqual(designated["device_root"], mappings[0]["device_root"])
            self.assertEqual(
                designated["ambient_home_root"],
                f"{mappings[0]['device_root']}/ambient-home",
            )
            self.assertEqual(
                designated["byte_stress_root"],
                f"{mappings[0]['device_root']}/byte-stress",
            )
            self.assertFalse(designated["candidate_selection_authoritative"])
            self.assertFalse(designated["historical_template_path_imported"])

        self.assertEqual(len(device_roots), 60)
        self.assertEqual(len(set(device_roots)), 60)
        self.assertEqual(len(registry_roots), 60)
        self.assertEqual(len(set(registry_roots)), 60)

    def test_exact_scale_totals_are_plans_not_actual_attestations(self):
        summary = self.value["summary"]
        self.assertEqual(summary["logical_persona_count"], 20)
        self.assertEqual(summary["physical_device_root_count_three_replays"], 60)
        self.assertEqual(summary["isolated_registry_count_three_replays"], 60)
        self.assertEqual(summary["formal_scope_count_three_replays"], 1_200)
        self.assertEqual(summary["full_w0_source_files_per_replay"], 203_000)
        self.assertEqual(summary["full_w0_source_files_three_replays"], 609_000)
        self.assertEqual(
            summary["planned_current_contract_chunks_per_device_root"], 120_000
        )
        self.assertEqual(
            summary[
                "planned_w5_final_current_plus_history_contract_chunks_per_device_root"
            ],
            180_000,
        )
        self.assertEqual(
            summary[
                "planned_w5_final_current_plus_history_contract_chunks_three_replays"
            ],
            10_800_000,
        )
        self.assertFalse(self.value["authority"]["actual_chunks_attested"])

    def test_all_authority_g0_and_write_claims_remain_false(self):
        self.assertTrue(all(flag is False for flag in self.value["authority"].values()))
        self.assertFalse(self.value["g0_contract_frozen"])
        completion = self.value["completion_claims"]
        for key in (
            "designated_lane_replay_selected_by_g0",
            "filesystem_materialized",
            "g0_eligible",
            "physical_isolation_readback_complete",
            "production_device_lane_composition_complete",
        ):
            self.assertFalse(completion[key])
        candidate = self.value["designated_lane_replay_candidate"]
        self.assertEqual(candidate["candidate_status"], "unratified")
        self.assertFalse(candidate["selected_by_g0"])
        self.assertIn(
            "designated-ambient-and-byte-stress-replay-not-selected-by-g0",
            self.value["remaining_blockers"],
        )

    def test_historical_templates_are_logical_only_and_safety_is_fail_closed(self):
        historical = self.value["historical_lane_templates"]
        self.assertEqual(historical["coordinate_semantics"], "logical-lane-plan-only")
        self.assertFalse(historical["physical_path_authority"])
        self.assertFalse(historical["direct_writer_input_allowed"])
        self.assertFalse(historical["historical_roots_may_be_created"])
        self.assertEqual(
            [row["historical_template"] for row in historical["templates"]],
            [
                "formal-root/devices/{persona_id}/home",
                "robustness-root/devices/{persona_id}/ambient-home",
            ],
        )

        safety = self.value["safety_contract"]
        self.assertTrue(safety["fresh_w0_build_required_for_every_formal_replay"])
        for key in (
            "completed_root_copy_allowed",
            "cross_boundary_file_copy_allowed",
            "cross_lane_payload_materialization_sharing_allowed",
            "cross_persona_payload_materialization_sharing_allowed",
            "cross_replay_payload_materialization_sharing_allowed",
            "filesystem_clone_allowed",
            "hard_link_allowed",
            "lane_pooling_allowed",
            "persona_pooling_allowed",
            "payload_materialization_reuse_allowed",
            "replay_pooling_allowed",
            "shared_inode_allowed",
            "symlink_allowed",
        ):
            self.assertFalse(safety[key])

    def test_independent_validator_accepts_object_bytes_and_hash(self):
        source = inspect.getsource(independent)
        self.assertNotIn("persona_v2_device_lane_compositor as", source)
        self.assertTrue(independent.validate_device_lane_compositor(self.value))
        loaded = independent.load_and_validate_device_lane_compositor(self.raw)
        self.assertEqual(loaded, self.value)
        self.assertEqual(
            producer.device_lane_compositor_sha256(self.value),
            hashlib.sha256(self.raw).hexdigest(),
        )

    def test_builder_is_detached_and_role_slug_derivation_is_strict(self):
        first = producer.build_device_lane_compositor()
        first["personas"][0]["role_slug"] = "poisoned"
        second = producer.build_device_lane_compositor()
        self.assertEqual(second["personas"][0]["role_slug"], "software-engineer")
        self.assertEqual(producer.portable_role_slug("software-engineer"), "software-engineer")
        for role in ("Software-Engineer", "software_engineer", "éngineer", "a--b"):
            with self.subTest(role=role):
                with self.assertRaises(producer.PersonaV2DeviceLaneCompositorError):
                    producer.portable_role_slug(role)

    def test_golden_drift_and_producer_validator_misalignment_fail_closed(self):
        with mock.patch.object(independent, "EXPECTED_SHA256", "0" * 64):
            with self.assertRaisesRegex(
                producer.PersonaV2DeviceLaneCompositorError,
                "golden constants differ",
            ):
                producer.canonical_json_bytes(self.value)

        with mock.patch.object(independent, "EXPECTED_SHA256", "0" * 64):
            with self.assertRaisesRegex(
                independent.PersonaV2DeviceLaneCompositorValidationError,
                "SHA-256 drifted",
            ):
                independent.validate_device_lane_compositor(self.value)

        with mock.patch.object(producer, "EXPECTED_SHA256", "0" * 64):
            for operation in (
                producer.build_device_lane_compositor,
                lambda: producer.validate_device_lane_compositor(self.value),
            ):
                with self.subTest(operation=operation):
                    with self.assertRaisesRegex(
                        producer.PersonaV2DeviceLaneCompositorError,
                        "golden constants differ",
                    ):
                        operation()

    def test_authority_candidate_role_path_dependency_summary_and_safety_tamper_fail(self):
        mutations = []

        authority = self.fresh()
        authority["authority"]["authorizes_physical_write"] = True
        mutations.append(authority)

        selected = self.fresh()
        selected["designated_lane_replay_candidate"]["selected_by_g0"] = True
        mutations.append(selected)

        role = self.fresh()
        role["personas"][0]["role_slug"] = "site-reliability-engineer"
        mutations.append(role)

        path = self.fresh()
        path["personas"][0]["formal_replay_mappings"][0]["device_root"] = (
            "formal-replay-01/devices/p02-site-reliability-engineer"
        )
        mutations.append(path)

        dependency = self.fresh()
        dependency["dependency_pin"]["sha256"] = "0" * 64
        mutations.append(dependency)

        summary = self.fresh()
        summary["full_w0_source_files_three_replays"] = 203_000
        mutations.append(summary)

        sharing = self.fresh()
        sharing["safety_contract"]["shared_inode_allowed"] = True
        mutations.append(sharing)

        historical = self.fresh()
        historical["historical_lane_templates"]["physical_path_authority"] = True
        mutations.append(historical)

        for mutation in mutations:
            with self.subTest(index=mutations.index(mutation)):
                self.assert_rejected(mutation)

    def test_omission_extra_wrong_type_and_noncanonical_bytes_fail(self):
        omitted = self.fresh()
        omitted.pop("summary")
        extra = self.fresh()
        extra["writer_receipt"] = {}
        wrong_type = self.fresh()
        wrong_type["personas"][0]["logical_persona_ordinal"] = True
        for mutation in (omitted, extra, wrong_type):
            self.assert_rejected(mutation)

        duplicated = b'{"artifact_kind":"forged",' + self.raw[1:]
        with self.assertRaisesRegex(
            independent.PersonaV2DeviceLaneCompositorValidationError,
            "duplicate object key",
        ):
            independent.strict_load_canonical_json_bytes(duplicated)

        noncanonical = self.raw.replace(b'":', b'": ', 1)
        with self.assertRaisesRegex(
            independent.PersonaV2DeviceLaneCompositorValidationError,
            "not exact canonical JSON",
        ):
            independent.strict_load_canonical_json_bytes(noncanonical)

        with self.assertRaises(
            independent.PersonaV2DeviceLaneCompositorValidationError
        ):
            independent.strict_load_canonical_json_bytes(
                b"{" + b" " * independent.MAX_COMPOSITOR_BYTES + b"}"
            )

    def test_envelope_tamper_and_expanded_alias_bomb_fail_before_acceptance(self):
        tampered_envelope = envelope.build_envelope_contract()
        tampered_envelope["personas"][0]["role"] = "software-engineer-forged"
        with self.assertRaises(
            independent.PersonaV2DeviceLaneCompositorValidationError
        ):
            independent.validate_device_lane_compositor(
                self.value,
                envelope_value=tampered_envelope,
            )

        alias = [False] * 2_000
        bomb = {f"branch-{ordinal}": alias for ordinal in range(60)}
        with self.assertRaisesRegex(
            independent.PersonaV2DeviceLaneCompositorValidationError,
            "expanded node budget",
        ):
            independent.validate_device_lane_compositor(bomb)

    def test_authorized_entrypoints_fail_closed(self):
        with self.assertRaises(producer.PersonaV2DeviceLaneCompositorError):
            producer.require_authorized_device_lane_compositor()
        with self.assertRaises(
            independent.PersonaV2DeviceLaneCompositorValidationError
        ):
            independent.require_authorized_device_lane_compositor(self.value)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
