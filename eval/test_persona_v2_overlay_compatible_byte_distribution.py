import copy
import hashlib
import inspect
import unittest
from unittest import mock

from eval import persona_v2_aggregate_byte_distribution_catalog as aggregate
from eval import persona_v2_artifact_common as artifact_common
from eval import persona_v2_format_implementation_registry as registry
from eval import persona_v2_overlay_compatible_byte_distribution as subject
from eval import persona_v2_overlay_compatible_byte_distribution_validator as independent
from eval import persona_v2_overlay_reservation_layout as reservation


EXPECTED_CANONICAL_BYTES = 91_039
EXPECTED_SHA256 = "e4acd26dd7b268d86e21320a4a893416e7de169501b479a0bd8a215927265a89"


class PersonaV2OverlayCompatibleByteDistributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = subject.build_overlay_compatible_byte_distribution()
        cls.aggregate_value = aggregate.build_aggregate_byte_distribution_catalog()
        cls.registry_value = registry.build_format_implementation_registry()
        cls.reservation_value = reservation.build_overlay_reservation_suite()
        cls.eml_implementation_row = next(
            row
            for row in cls.registry_value["implementation_rows"]
            if row["variant_id"] == "eml"
        )
        renderer_provider, validator_provider = registry._probe_providers()
        cls.origin_provider = staticmethod(reservation.build_overlay_reservation_origin)
        cls.renderer_provider = staticmethod(renderer_provider)
        cls.validator_provider = staticmethod(validator_provider)

    def _x_filled_renderer(self, variant_id, parameters):
        rendered = self.renderer_provider(variant_id, parameters)
        rendered["data"] = b"X" * rendered["target_bytes"]
        return rendered

    def _forged_x_validator(self, variant_id, parameters, rendered):
        complexity = parameters["target_complexity"]
        target_bytes = rendered["target_bytes"]
        implementation = self.eml_implementation_row["implementation"]
        return {
            "input_payload_sha256": hashlib.sha256(rendered["data"]).hexdigest(),
            "native_receipt": {
                "actual_chunks_attested": False,
                "attachment_count": complexity,
                "byte_length": target_bytes,
                "identity_tokens_absent": True,
                "kcs_execution_attested": False,
                "observed_complexity_measure": "attachments",
                "observed_local_complexity": complexity,
                "structure_validated": True,
                "target_bytes": target_bytes,
                "utf8_validated": True,
            },
            "validator_binding_id": implementation["validator_binding_id"],
            "validator_id": implementation["validator_id"],
            "validator_profile_id": implementation["validator_profile_id"],
            "validator_schema_version": implementation["validator_schema_version"],
            "variant_id": variant_id,
        }

    def _independent_validate(
        self,
        value,
        *,
        aggregate_value=None,
        registry_value=None,
        reservation_value=None,
        origin_provider=None,
        renderer_provider=None,
        validator_provider=None,
    ):
        return independent.validate_overlay_compatible_byte_distribution(
            value,
            aggregate_value=(
                self.aggregate_value if aggregate_value is None else aggregate_value
            ),
            registry_value=(
                self.registry_value if registry_value is None else registry_value
            ),
            reservation_suite_value=(
                self.reservation_value
                if reservation_value is None
                else reservation_value
            ),
            reservation_origin_provider=(
                self.origin_provider if origin_provider is None else origin_provider
            ),
            renderer_probe_provider=(
                self.renderer_provider
                if renderer_provider is None
                else renderer_provider
            ),
            validator_probe_provider=(
                self.validator_provider
                if validator_provider is None
                else validator_provider
            ),
        )

    def _assert_independent_rejects_rehashed(self, value, **kwargs):
        raw = artifact_common.canonical_json_bytes(
            value,
            label="rehashed overlay-compatible byte distribution",
            max_bytes=subject.MAX_CATALOG_BYTES,
        )
        with (
            mock.patch.object(
                independent, "EXPECTED_CATALOG_CANONICAL_BYTES", len(raw)
            ),
            mock.patch.object(
                independent,
                "EXPECTED_CATALOG_SHA256",
                hashlib.sha256(raw).hexdigest(),
            ),
            mock.patch.object(
                independent.aggregate,
                "validate_aggregate_byte_distribution_catalog",
                return_value=True,
            ),
            mock.patch.object(
                independent.registry,
                "validate_format_implementation_registry",
                return_value=True,
            ),
            mock.patch.object(
                independent.reservation,
                "validate_overlay_reservation_suite",
                return_value=True,
            ),
            self.assertRaises(
                independent.PersonaV2OverlayCompatibleByteDistributionValidationError
            ),
        ):
            self._independent_validate(value, **kwargs)

    def test_exact_pin_and_independent_acceptance(self):
        self.assertEqual(
            len(subject.canonical_json_bytes(self.value)), EXPECTED_CANONICAL_BYTES
        )
        self.assertEqual(
            subject.overlay_compatible_byte_distribution_sha256(self.value),
            EXPECTED_SHA256,
        )
        self.assertTrue(self._independent_validate(self.value))

    def test_base_infeasibility_is_explicit_and_exact(self):
        self.assertEqual(
            self.value["base_infeasibility_receipt"],
            {
                "base_assignment_feasible": False,
                "base_selectable_complexities": [0, 1, 5],
                "incompatible_persona_origin_count": 40,
                "missing_required_complexities": [2, 3, 4],
                "required_full_host_fanout_counts": [
                    {"host_member_count": 1, "host_source_count": 1_370},
                    {"host_member_count": 2, "host_source_count": 590},
                    {"host_member_count": 3, "host_source_count": 400},
                    {"host_member_count": 4, "host_source_count": 260},
                    {"host_member_count": 5, "host_source_count": 180},
                ],
            },
        )

    def test_all_twenty_eml_rows_close_pilot_residual_and_full(self):
        rows = self.value["eml_override_rows"]
        self.assertEqual(len(rows), 20)
        self.assertEqual(
            [row["persona_id"] for row in rows],
            [f"p{index:02d}" for index in range(1, 21)],
        )
        for row in rows:
            self.assertEqual(row["variant_id"], "eml")
            self.assertEqual(
                [item["target_complexity"] for item in row["parameter_bins"]],
                list(range(6)),
            )
            for item in row["parameter_bins"]:
                counts = item["counts"]
                self.assertEqual(
                    counts["full"], counts["pilot"] + counts["full-residual"]
                )
            for profile in ("pilot", "full-residual", "full"):
                self.assertEqual(
                    sum(item["counts"][profile] for item in row["parameter_bins"]),
                    row["source_counts"][profile],
                )
                self.assertEqual(
                    sum(
                        item["target_complexity"] * item["counts"][profile]
                        for item in row["parameter_bins"]
                    ),
                    row["attachment_membership_counts"][profile],
                )
                self.assertEqual(
                    sum(
                        item["counts"][profile]
                        for item in row["parameter_bins"]
                        if item["target_complexity"] > 0
                    ),
                    row["host_source_counts"][profile],
                )

    def test_effective_suite_and_capacity_are_exact(self):
        summary = self.value["effective_suite_summary"]
        self.assertEqual(
            summary["source_counts"],
            {"pilot": 20_300, "full-residual": 182_700, "full": 203_000},
        )
        self.assertEqual(
            summary["summaries"]["full"],
            {
                "block_rounded_payload_bytes": 5_189_435_392,
                "formal_tail_count": 160,
                "maximum_bytes": 2_621_440,
                "nearest_rank_p50_bytes": 8_192,
                "nearest_rank_p95_bytes": 129_024,
                "raw_byte_sum": 5_029_207_294,
                "source_count": 203_000,
                "statistics_defined": True,
            },
        )
        self.assertTrue(summary["capacity_check"]["passes_hard_cap"])
        p12 = next(
            row
            for row in self.value["effective_persona_summaries"]
            if row["persona_id"] == "p12"
        )
        self.assertEqual(
            p12["summaries"]["full"]["block_rounded_payload_bytes"], 411_774_976
        )
        self.assertTrue(p12["capacity_check"]["passes_hard_cap"])

    def test_effective_html_eml_projection_and_runtime_receipts_are_complete(self):
        family_rows = self.value["effective_html_eml_family_projection_rows"]
        self.assertEqual(len(family_rows), 20)
        self.assertEqual(
            [row["persona_id"] for row in family_rows],
            [f"p{index:02d}" for index in range(1, 21)],
        )
        self.assertTrue(all(row["family"] == "html_eml" for row in family_rows))
        self.assertTrue(all(row["variant_row_count"] == 2 for row in family_rows))

        probes = self.value["eml_runtime_probe_receipts"]
        self.assertEqual(len(probes), 6)
        self.assertEqual(
            [row["target_complexity"] for row in probes], list(range(6))
        )
        self.assertEqual(
            [row["target_bytes"] for row in probes],
            [8_192 + 16_384 * complexity for complexity in range(6)],
        )
        self.assertTrue(all(row["validator_accepted"] is True for row in probes))
        self.assertTrue(
            all(len(row["validator_receipt_sha256"]) == 64 for row in probes)
        )

    def test_direct_payload_validation_rejects_x_filled_forged_receipts(self):
        inputs = {"registry": self.registry_value}
        formula = subject._eml_formula(inputs)
        with self.assertRaises(
            subject.PersonaV2OverlayCompatibleByteDistributionError
        ):
            subject._probe_receipts(
                inputs,
                formula,
                self._x_filled_renderer,
                self._forged_x_validator,
            )

        mutation = copy.deepcopy(self.value)
        for probe in mutation["eml_runtime_probe_receipts"]:
            parameters = copy.deepcopy(probe["renderer_parameters"])
            rendered = self._x_filled_renderer("eml", parameters)
            forged_receipt = self._forged_x_validator(
                "eml", parameters, rendered
            )
            receipt_raw = artifact_common.canonical_json_bytes(
                forged_receipt,
                label="forged X-filled EML validator receipt",
                max_bytes=128 * 1024,
            )
            probe["payload_sha256"] = hashlib.sha256(rendered["data"]).hexdigest()
            probe["validator_receipt_sha256"] = hashlib.sha256(
                receipt_raw
            ).hexdigest()
        self._assert_independent_rejects_rehashed(
            mutation,
            renderer_provider=self._x_filled_renderer,
            validator_provider=self._forged_x_validator,
        )

    def test_completion_and_authority_remain_narrow_and_false(self):
        self.assertFalse(self.value["g0_contract_frozen"])
        self.assertTrue(self.value["authority"])
        self.assertFalse(any(self.value["authority"].values()))
        claims = self.value["completion_claims"]
        self.assertTrue(claims["effective_203000_source_aggregate_summary_complete"])
        self.assertFalse(claims["all_203000_source_instance_parameters_bound"])
        self.assertFalse(claims["host_to_source_parameter_assignment_complete"])
        self.assertFalse(claims["source_instance_assignment_complete"])
        self.assertFalse(claims["decoded_attachment_payload_equivalence_bound"])
        with self.assertRaises(
            subject.PersonaV2OverlayCompatibleByteDistributionError
        ):
            subject.require_source_instance_parameter_assignment()

    def test_builder_is_detached_and_public_validator_wraps_rejection(self):
        changed = subject.build_overlay_compatible_byte_distribution()
        changed["eml_override_rows"][0]["parameter_bins"][0]["counts"][
            "pilot"
        ] = True
        fresh = subject.build_overlay_compatible_byte_distribution()
        self.assertIsNot(
            fresh["eml_override_rows"][0]["parameter_bins"][0]["counts"][
                "pilot"
            ],
            True,
        )
        with self.assertRaises(
            subject.PersonaV2OverlayCompatibleByteDistributionError
        ):
            subject.validate_overlay_compatible_byte_distribution(changed)

    def test_producer_authenticates_origin_suite_binding(self):
        origin_bindings = subject._origin_binding_map(
            {"reservation": self.reservation_value}
        )
        changed = copy.deepcopy(origin_bindings)
        changed[("p01", "pilot")]["sha256"] = "0" * 64
        with self.assertRaises(
            subject.PersonaV2OverlayCompatibleByteDistributionError
        ):
            subject._host_fanout(
                "p01", "pilot", self.origin_provider, changed
            )

    def test_producer_callback_cannot_mutate_cached_dependencies(self):
        cached_inputs = subject._cached_shared_inputs()
        calls = []

        def mutating_origin(_persona_id, _origin):
            cached_inputs["bindings"][0]["sha256"] = "0" * 64
            calls.append(True)
            raise RuntimeError("stop after mutating cached dependencies")

        subject._canonical_catalog.cache_clear()
        with (
            mock.patch.object(
                subject.reservation,
                "build_overlay_reservation_origin",
                side_effect=mutating_origin,
            ),
            self.assertRaisesRegex(
                subject.PersonaV2OverlayCompatibleByteDistributionError,
                "cached dependency bodies changed",
            ),
        ):
            subject.build_overlay_compatible_byte_distribution()
        self.assertEqual(calls, [True])
        self.assertEqual(subject._cached_shared_inputs.cache_info().currsize, 0)

    def test_producer_rejects_validator_repair_of_bad_renderer_alias(self):
        inputs = {"registry": self.registry_value}
        formula = subject._eml_formula(inputs)

        def bad_renderer(variant_id, parameters):
            rendered = self.renderer_provider(variant_id, parameters)
            rendered["target_bytes"] = True
            return rendered

        def repairing_validator(variant_id, parameters, rendered):
            rendered["target_bytes"] = len(rendered["data"])
            return self.validator_provider(variant_id, parameters, rendered)

        with self.assertRaises(
            subject.PersonaV2OverlayCompatibleByteDistributionError
        ):
            subject._probe_receipts(
                inputs, formula, bad_renderer, repairing_validator
            )

        def malicious_validator(variant_id, parameters, rendered):
            receipt = self.validator_provider(variant_id, parameters, rendered)
            receipt["native_receipt"]["structure_validated"] = False
            return receipt

        with self.assertRaises(
            subject.PersonaV2OverlayCompatibleByteDistributionError
        ):
            subject._probe_receipts(
                inputs, formula, self.renderer_provider, malicious_validator
            )

    def test_producer_rejects_prepoisoned_bindings_and_snapshot_drift(self):
        inputs = copy.deepcopy(subject._cached_shared_inputs())
        inputs["bindings"][0]["sha256"] = "0" * 64
        with self.assertRaises(
            subject.PersonaV2OverlayCompatibleByteDistributionError
        ):
            subject._validate_shared_inputs(inputs)

        inputs = copy.deepcopy(subject._cached_shared_inputs())
        opening = subject._input_fingerprint(inputs)
        inputs["registry"]["completion_scope"] = "mutated-during-callback"
        with self.assertRaises(
            subject.PersonaV2OverlayCompatibleByteDistributionError
        ):
            subject._reauth_inputs(inputs, opening, label="test snapshot")

    def test_rehashed_histogram_full_composition_and_capacity_drift_are_rejected(self):
        mutation = copy.deepcopy(self.value)
        mutation["eml_override_rows"][0]["parameter_bins"][1]["counts"][
            "pilot"
        ] += 1
        self._assert_independent_rejects_rehashed(mutation)

        mutation = copy.deepcopy(self.value)
        mutation["eml_override_rows"][0]["source_counts"]["full"] += 1
        self._assert_independent_rejects_rehashed(mutation)

        mutation = copy.deepcopy(self.value)
        mutation["effective_persona_summaries"][0]["capacity_check"][
            "passes_hard_cap"
        ] = False
        self._assert_independent_rejects_rehashed(mutation)

    def test_rehashed_bool_masquerades_for_count_version_and_bytes_are_rejected(self):
        mutations = []
        count = copy.deepcopy(self.value)
        count["eml_override_rows"][0]["parameter_bins"][0]["counts"][
            "pilot"
        ] = True
        mutations.append(("count", count))

        version = copy.deepcopy(self.value)
        version["artifact_schema_version"] = True
        mutations.append(("version", version))

        byte_count = copy.deepcopy(self.value)
        byte_count["eml_override_rows"][0]["parameter_bins"][0][
            "exact_raw_bytes"
        ] = True
        mutations.append(("bytes", byte_count))

        for label, mutation in mutations:
            with self.subTest(label=label):
                self._assert_independent_rejects_rehashed(mutation)

    def test_rehashed_authority_and_completion_drift_are_metadata_first(self):
        for field, key, replacement in (
            ("authority", "authorizes_g0_freeze", True),
            ("completion_claims", "source_instance_assignment_complete", True),
        ):
            with self.subTest(field=field):
                mutation = copy.deepcopy(self.value)
                mutation[field][key] = replacement
                calls = []

                def recording_origin(persona_id, origin):
                    calls.append((persona_id, origin))
                    return self.origin_provider(persona_id, origin)

                self._assert_independent_rejects_rehashed(
                    mutation, origin_provider=recording_origin
                )
                self.assertEqual(calls, [])

    def test_malicious_runtime_receipt_and_non_object_renderer_are_rejected(self):
        def malicious_validator(variant_id, parameters, rendered):
            receipt = self.validator_provider(variant_id, parameters, rendered)
            receipt["native_receipt"]["structure_validated"] = False
            return receipt

        self._assert_independent_rejects_rehashed(
            self.value, validator_provider=malicious_validator
        )

        self._assert_independent_rejects_rehashed(
            self.value,
            renderer_provider=lambda _variant_id, _parameters: b"not-an-object",
        )

    def test_provider_callbacks_cannot_mutate_target_or_registry(self):
        for target in ("catalog", "registry"):
            with self.subTest(target=target):
                value = copy.deepcopy(self.value)
                registry_value = copy.deepcopy(self.registry_value)
                calls = []

                def mutating_origin(persona_id, origin):
                    if not calls:
                        if target == "catalog":
                            value["authority"]["authorizes_g0_freeze"] = True
                        else:
                            registry_value["completion_scope"] = (
                                "mutated-during-provider-callback"
                            )
                    calls.append((persona_id, origin))
                    return self.origin_provider(persona_id, origin)

                self._assert_independent_rejects_rehashed(
                    value,
                    registry_value=registry_value,
                    origin_provider=mutating_origin,
                )
                self.assertTrue(calls)

    def test_registry_drift_is_rejected_before_origin_callbacks(self):
        changed = copy.deepcopy(self.registry_value)
        changed["completion_scope"] = "drifted"
        calls = []

        def recording_origin(persona_id, origin):
            calls.append((persona_id, origin))
            return self.origin_provider(persona_id, origin)

        with self.assertRaises(
            independent.PersonaV2OverlayCompatibleByteDistributionValidationError
        ):
            self._independent_validate(
                self.value,
                registry_value=changed,
                origin_provider=recording_origin,
            )
        self.assertEqual(calls, [])

    def test_input_binding_tamper_uses_specific_validation_error(self):
        mutation = copy.deepcopy(self.value)
        mutation["input_bindings"][0]["sha256"] = "0" * 64
        self._assert_independent_rejects_rehashed(mutation)

    def test_independent_validator_does_not_import_subject(self):
        source = inspect.getsource(independent)
        self.assertNotIn("import persona_v2_overlay_compatible_byte_distribution", source)
        self.assertNotIn("from . import persona_v2_overlay_compatible_byte_distribution", source)


if __name__ == "__main__":
    unittest.main()
