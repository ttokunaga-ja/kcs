import copy
import unittest

try:
    from . import generate_persona_corpus as generator
    from . import persona_capacity as capacity
except ImportError:  # pragma: no cover
    import generate_persona_corpus as generator
    import persona_capacity as capacity


SHA_A = "a" * 64
SHA_B = "b" * 64


def declared(persona_id, *, component_bytes=10, component_inodes=1):
    observations = {
        name: {
            "observed_bytes": component_bytes,
            "observed_additional_inodes": component_inodes,
        }
        for name in capacity.COMPONENTS
    }
    return capacity.build_declared_pilot_amplification(
        persona_id,
        filesystem_allocation_unit_bytes=4096,
        component_observations=observations,
    )


def required_values(plan, unit=4096):
    peak_inodes = plan["all_replays"]["peak_inodes"]
    payload = plan["all_replays"][
        "payload_peak_bytes_before_filesystem_allocation"
    ]
    return peak_inodes, payload + peak_inodes * unit


class PersonaCapacityProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wrapper = generator.build_persona_generation_plan("tiny", "p01")

    def test_exact_cardinalities_are_derived_without_rendering(self):
        projection = capacity.build_persona_capacity_projection(self.wrapper)
        self.assertEqual(projection["readiness"], "blocked_missing_pilot_evidence")
        self.assertEqual(projection["unknown_components"], list(capacity.COMPONENTS))
        self.assertEqual(projection["cardinalities"]["files"], {
            "w0_physical_files": 200,
            "final_active_files": 204,
            "transient_active_files": 209,
            "history_replacement_sources": 17,
            "structural_new_sources": 3,
            "persona_and_ledger_files": 81,
        })
        self.assertEqual(projection["cardinalities"]["scopes"]["active_scopes"], 20)
        self.assertEqual(projection["cardinalities"]["chunks"], {
            "current_chunks": 375,
            "history_only_chunks": 187,
            "current_plus_history_chunks": 562,
            "transient_current_chunks": 390,
            "transient_history_only_chunks": 202,
            "transient_current_plus_history_chunks": 592,
            "transient_extra_chunk_rows": 30,
        })
        self.assertEqual(projection["cardinalities"]["events"], {
            "history_events": 77,
            "structural_events": 11,
            "events": 88,
            "index_auto_boundaries": 55,
            "purged_commit_boundaries": 5,
            "index_noop_boundaries": 5,
            "boundaries": 65,
            "schedule_items": 153,
        })
        self.assertIsNone(projection["components"]["raw"]["projected_bytes"])

    def test_declared_zero_is_distinct_from_unknown_but_cannot_be_ready(self):
        evidence = declared("p01", component_bytes=0, component_inodes=1)
        projection = capacity.build_persona_capacity_projection(
            self.wrapper,
            amplification=evidence,
            headroom={"numerator": 1, "denominator": 1},
        )
        self.assertEqual(
            projection["readiness"],
            "blocked_measurement_receipt_readback_required",
        )
        self.assertEqual(projection["unknown_components"], [])
        self.assertEqual(projection["components"]["raw"]["projected_bytes"], 0)
        self.assertEqual(
            projection["measurement_readback_state"],
            capacity.MEASUREMENT_READBACK_REQUIRED,
        )

    def test_all_zero_component_declaration_fails_closed(self):
        with self.assertRaisesRegex(capacity.PersonaCapacityError, "all-zero"):
            declared("p01", component_bytes=0, component_inodes=0)

    def test_pilot_plan_and_basis_substitution_fail_even_when_rehashed(self):
        evidence = declared("p01")

        changed = copy.deepcopy(evidence)
        receipt = changed["pilot_measurement_receipt"]
        receipt["pilot_persona_plan_sha256"] = SHA_A
        receipt["measurement_projection_sha256"] = capacity._digest(
            capacity._pilot_measurement_projection(receipt)
        )
        receipt_sha = capacity._digest(receipt)
        changed["pilot_persona_plan_sha256"] = SHA_A
        for row in changed["components"].values():
            row["pilot_receipt_sha256"] = receipt_sha
        with self.assertRaisesRegex(capacity.PersonaCapacityError, "binding"):
            capacity.build_persona_capacity_projection(
                self.wrapper, amplification=changed
            )

        changed = copy.deepcopy(evidence)
        receipt = changed["pilot_measurement_receipt"]
        receipt["components"]["raw"]["observed_units"] += 1
        receipt["measurement_projection_sha256"] = capacity._digest(
            capacity._pilot_measurement_projection(receipt)
        )
        receipt_sha = capacity._digest(receipt)
        changed["components"]["raw"]["observed_units"] += 1
        for row in changed["components"].values():
            row["pilot_receipt_sha256"] = receipt_sha
        with self.assertRaisesRegex(capacity.PersonaCapacityError, "canonical pilot"):
            capacity.build_persona_capacity_projection(
                self.wrapper, amplification=changed
            )

    def test_unread_measured_status_and_noncanonical_numbers_are_rejected(self):
        evidence = declared("p01")
        evidence["components"]["raw"]["status"] = "measured"
        with self.assertRaisesRegex(capacity.PersonaCapacityError, "readback"):
            capacity.build_persona_capacity_projection(
                self.wrapper, amplification=evidence
            )
        for value in (True, 1.5):
            evidence = declared("p01")
            evidence["components"]["raw"]["observed_bytes"] = value
            with self.assertRaises(capacity.PersonaCapacityError):
                capacity.build_persona_capacity_projection(
                    self.wrapper, amplification=evidence
                )

    def test_wrapper_and_canonical_person_object_are_equivalent_inputs(self):
        wrapped = capacity.build_persona_capacity_projection(self.wrapper)
        direct = capacity.build_persona_capacity_projection(
            self.wrapper["persona"], profile="tiny"
        )
        self.assertEqual(wrapped["cardinalities"], direct["cardinalities"])
        self.assertEqual(wrapped["input_kind"], "validated_persona_wrapper")
        self.assertEqual(direct["input_kind"], "canonical_person_object")
        changed = copy.deepcopy(self.wrapper)
        changed["persona"]["raw_file_count"] += 1
        with self.assertRaisesRegex(capacity.PersonaCapacityError, "differs"):
            capacity.build_persona_capacity_projection(changed)

    def test_checked_integer_overflow_fails_closed(self):
        evidence = declared("p01", component_bytes=capacity.MAX_INTEGER)
        with self.assertRaisesRegex(capacity.PersonaCapacityError, "checked integer"):
            capacity.build_persona_capacity_projection(
                self.wrapper,
                amplification=evidence,
                headroom={"numerator": 2, "denominator": 1},
            )


class PersonaCapacitySuiteAndReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tiny = generator.build_persona_generation_plan("tiny", "p01")
        cls.evidence = declared("p01", component_bytes=2, component_inodes=1)
        cls.amplifications = {"p01": cls.evidence}
        cls.headroom = {"numerator": 1, "denominator": 1}
        cls.plan = capacity.build_capacity_plan(
            [cls.tiny],
            amplifications=cls.amplifications,
            headroom=cls.headroom,
        )
        peak, required = required_values(cls.plan)
        cls.peak = peak
        cls.required = required
        cls.measurement = capacity.build_declared_root_capacity_measurement(
            destination_root="/private/tmp/kio-persona-capacity",
            filesystem_device=42,
            filesystem_allocation_unit_bytes=4096,
            free_bytes=required + 1000,
            free_inodes=peak + 100,
        )

    def call_check(self, **changes):
        values = {
            "root_measurement": self.measurement,
            "byte_cap": self.required,
            "inode_cap": self.peak,
            "reserve_bytes": 1000,
            "reserve_inodes": 100,
            "amplifications": self.amplifications,
            "headroom": self.headroom,
        }
        values.update(changes)
        return capacity.check_root_bound_capacity(
            self.plan, [self.tiny], **values
        )

    def build_receipt(self):
        return capacity.build_capacity_receipt(
            self.plan,
            [self.tiny],
            root_measurement=self.measurement,
            suite_manifest_sha256=SHA_B,
            byte_cap=self.required,
            inode_cap=self.peak,
            reserve_bytes=1000,
            reserve_inodes=100,
            amplifications=self.amplifications,
            headroom=self.headroom,
        )

    def validate_receipt(self, receipt, *, expected_root=None):
        return capacity.validate_capacity_receipt(
            receipt,
            self.plan,
            [self.tiny],
            expected_destination_root=(
                expected_root or "/private/tmp/kio-persona-capacity"
            ),
            expected_suite_manifest_sha256=SHA_B,
            amplifications=self.amplifications,
            headroom=self.headroom,
        )

    def test_per_replay_and_three_replay_projection_is_exact_but_blocked(self):
        plan = self.plan
        self.assertEqual(plan["readiness"], "blocked")
        self.assertEqual(
            plan["blockers"], ["pilot_measurement_receipt_readback_required"]
        )
        per_replay = plan["per_replay"]["cardinalities"]
        all_replays = plan["all_replays"]["cardinalities"]
        self.assertEqual(per_replay["files"]["w0_physical_files"], 200)
        self.assertEqual(all_replays["files"]["w0_physical_files"], 600)
        self.assertEqual(per_replay["chunks"]["current_chunks"], 375)
        self.assertEqual(all_replays["chunks"]["current_chunks"], 1125)
        self.assertEqual(per_replay["events"]["events"], 88)
        self.assertEqual(all_replays["events"]["events"], 264)
        self.assertEqual(plan["root_binding"], "forbidden_in_projection")
        self.assertEqual(plan["contracts"]["actual_kio_attestation"], "false")

    def test_fake_ready_plan_cannot_reach_capacity_check(self):
        fake = {
            "readiness": "projection_ready_root_measurement_required",
            "profile": "full",
            "input_inventory_sha256": "not-a-digest",
            "all_replays": {
                "peak_inodes": 1,
                "payload_peak_bytes_before_filesystem_allocation": 1,
            },
        }
        with self.assertRaisesRegex(
            capacity.PersonaCapacityError, "canonical expansion"
        ):
            capacity.check_root_bound_capacity(
                fake,
                [self.tiny],
                root_measurement=self.measurement,
                byte_cap=self.required,
                inode_cap=self.peak,
                reserve_bytes=0,
                reserve_inodes=0,
                amplifications=self.amplifications,
                headroom=self.headroom,
            )

    def test_full_one_person_and_wrong_replay_count_remain_blocked(self):
        full = generator.build_persona_generation_plan("full", "p01")
        one_person = capacity.build_capacity_plan([full], replay_count=2)
        self.assertEqual(one_person["readiness"], "blocked")
        self.assertIn("full_requires_three_replays", one_person["blockers"])
        self.assertIn("full_requires_all_twenty_personas", one_person["blockers"])
        self.assertIn(
            "pilot_amplification_or_allocation_unit_unknown",
            one_person["blockers"],
        )

    def test_declared_root_projection_never_claims_pass_or_write_authority(self):
        check = self.call_check()
        self.assertEqual(check["required_peak_bytes"], self.required)
        self.assertEqual(
            check["filesystem_allocation_allowance_bytes"], self.peak * 4096
        )
        self.assertEqual(
            check["capacity_state"],
            "blocked_measurement_receipt_readback_required",
        )
        self.assertIn(
            capacity.ROOT_MEASUREMENT_READBACK_REQUIRED,
            check["blocking_evidence"],
        )
        self.assertEqual(check["physical_write_authorization"], "false")
        self.assertEqual(check["actual_kio_attestation"], "false")
        receipt = self.build_receipt()
        self.assertEqual(
            receipt["approval_scope"],
            "capacity_only_not_physical_write_authorization",
        )
        self.assertEqual(receipt["actual_kio_attestation"], "false")
        self.validate_receipt(receipt)

    def test_caps_and_reserves_still_fail_before_a_blocked_receipt(self):
        failures = (
            {"byte_cap": self.required - 1},
            {"inode_cap": self.peak - 1},
            {"reserve_bytes": 1001},
            {"reserve_inodes": 101},
        )
        for changes in failures:
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(
                    capacity.PersonaCapacityError, "capacity preflight failed"
                ):
                    self.call_check(**changes)

    def test_root_measurement_and_receipt_tampering_fail_closed(self):
        changed_measurement = copy.deepcopy(self.measurement)
        changed_measurement["filesystem"]["free_bytes"] += 1
        with self.assertRaisesRegex(capacity.PersonaCapacityError, "digest"):
            self.call_check(root_measurement=changed_measurement)

        changed_measurement = copy.deepcopy(self.measurement)
        changed_measurement["destination_root"] = "relative/root"
        changed_measurement["measurement_projection_sha256"] = capacity._digest(
            capacity._root_measurement_projection(changed_measurement)
        )
        with self.assertRaisesRegex(capacity.PersonaCapacityError, "absolute"):
            self.call_check(root_measurement=changed_measurement)

        receipt = self.build_receipt()
        changed = copy.deepcopy(receipt)
        changed["check"]["required_peak_bytes"] -= 1
        with self.assertRaisesRegex(capacity.PersonaCapacityError, "arithmetic"):
            self.validate_receipt(changed)

        changed = copy.deepcopy(receipt)
        changed["limits"]["reserve_bytes"] = False
        with self.assertRaisesRegex(capacity.PersonaCapacityError, "boolean"):
            self.validate_receipt(changed)

        changed = copy.deepcopy(receipt)
        changed["destination_root"] = "relative/root"
        with self.assertRaisesRegex(capacity.PersonaCapacityError, "absolute"):
            self.validate_receipt(changed, expected_root="relative/root")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
