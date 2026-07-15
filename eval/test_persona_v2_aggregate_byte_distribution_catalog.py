"""Focused and adversarial gates for aggregate byte distributions."""

from __future__ import annotations

import copy
import hashlib
import unittest
from unittest import mock

from eval import persona_v2_aggregate_byte_distribution_catalog as catalog
from eval import persona_v2_aggregate_byte_distribution_catalog_validator as independent
from eval import persona_v2_artifact_common as artifact_common
from eval import persona_v2_formal_source_recipe_catalog as formal
from eval import persona_v2_format_implementation_registry as registry
from eval import persona_v2_realism_profile as realism
from eval import persona_v2_source_inventory_profile as inventory
from eval import persona_v2_source_profile_catalog as historical
from eval import persona_v2_variant_catalog as variants


EXPECTED_CANONICAL_BYTES = 1_576_125
EXPECTED_SHA256 = (
    "7f2fdcc823885401cb7ed1b8fc42c9010b38af63d2c58879babb28aadeb6b343"
)


class AggregateByteDistributionCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.variant_value = variants.build_variant_catalog()
        cls.registry_value = registry.build_format_implementation_registry()
        cls.formal_value = formal.build_formal_source_recipe_catalog()
        cls.realism_value = realism.build_realism_profile()
        cls.inventory_value = inventory.build_source_inventory_profile_catalog()
        cls.historical_value = historical.build_source_profile_catalog()
        cls.semantic_value = formal._source_semantic_catalog_dependency()
        renderer_contract_provider, validator_contract_provider = (
            registry._contract_providers()
        )
        renderer_probe_provider, validator_probe_provider = registry._probe_providers()
        cls.renderer_contract_provider = staticmethod(renderer_contract_provider)
        cls.validator_contract_provider = staticmethod(validator_contract_provider)
        cls.renderer_probe_provider = staticmethod(renderer_probe_provider)
        cls.validator_probe_provider = staticmethod(validator_probe_provider)
        cls.value = catalog.build_aggregate_byte_distribution_catalog()

    def _independent_validate(
        self,
        value,
        *,
        registry_value=None,
        selected_renderer_probe_provider=None,
        selected_validator_probe_provider=None,
    ):
        return independent.validate_aggregate_byte_distribution_catalog(
            value,
            variant_catalog_value=self.variant_value,
            format_implementation_registry_value=(
                self.registry_value if registry_value is None else registry_value
            ),
            formal_source_recipe_catalog_value=self.formal_value,
            realism_profile_value=self.realism_value,
            historical_source_profile_value=self.historical_value,
            source_inventory_profile_value=self.inventory_value,
            source_semantic_membership_catalog_value=self.semantic_value,
            renderer_contract_provider=self.renderer_contract_provider,
            validator_contract_provider=self.validator_contract_provider,
            renderer_probe_provider=self.renderer_probe_provider,
            selected_renderer_probe_provider=(
                self.renderer_probe_provider
                if selected_renderer_probe_provider is None
                else selected_renderer_probe_provider
            ),
            selected_validator_probe_provider=(
                self.validator_probe_provider
                if selected_validator_probe_provider is None
                else selected_validator_probe_provider
            ),
        )

    def _assert_independent_rejects_rehashed(self, value):
        raw = artifact_common.canonical_json_bytes(
            value,
            label="rehashed aggregate byte distribution catalog",
            max_bytes=catalog.MAX_CATALOG_BYTES,
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
                independent.formal_validator,
                "validate_formal_source_recipe_catalog",
                return_value=True,
            ),
            self.assertRaises(
                independent.PersonaV2AggregateByteDistributionCatalogValidationError
            ),
        ):
            self._independent_validate(value)

    def _replace_variant_bin_with_valid_renderer_request(
        self, value, *, variant_id, bin_id, parameters
    ):
        """Keep every aggregate/probe projection internally self-consistent."""

        rendered = self.renderer_probe_provider(variant_id, parameters)
        validator_receipt = self.validator_probe_provider(
            variant_id, parameters, rendered
        )
        validator_raw = artifact_common.canonical_json_bytes(
            validator_receipt,
            label="adversarial selected-bin validator receipt",
            max_bytes=128 * 1024,
        )
        for row in value["persona_variant_rows"]:
            if row["variant_id"] != variant_id:
                continue
            selected = next(
                item for item in row["parameter_bins"] if item["bin_id"] == bin_id
            )
            selected["renderer_parameters"] = copy.deepcopy(parameters)
            selected["target_complexity"] = rendered["target_complexity"]
            selected["exact_raw_bytes"] = rendered["target_bytes"]
            row["summaries"] = {
                profile: catalog._summary(
                    catalog._row_entries(row["parameter_bins"], profile)
                )
                for profile in catalog.PROFILE_ORDER
            }
        family_rows, persona_rows, suite = catalog._projections(
            value["persona_variant_rows"]
        )
        value["persona_family_projection_rows"] = family_rows
        value["persona_summaries"] = persona_rows
        value["suite_summary"] = suite
        probe = next(
            row
            for row in value["parameter_bin_probe_receipts"]
            if row["variant_id"] == variant_id and row["bin_id"] == bin_id
        )
        probe.update(
            {
                "payload_sha256": hashlib.sha256(rendered["data"]).hexdigest(),
                "renderer_parameters": copy.deepcopy(parameters),
                "target_bytes": rendered["target_bytes"],
                "target_complexity": rendered["target_complexity"],
                "validator_accepted": True,
                "validator_receipt_sha256": hashlib.sha256(
                    validator_raw
                ).hexdigest(),
            }
        )

    def test_canonical_pin_and_exact_cardinalities(self):
        raw = catalog.canonical_json_bytes(self.value)
        self.assertEqual(len(raw), EXPECTED_CANONICAL_BYTES)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), EXPECTED_SHA256)
        self.assertEqual(len(self.value["persona_variant_rows"]), 566)
        self.assertEqual(len(self.value["persona_family_projection_rows"]), 300)
        self.assertEqual(len(self.value["persona_summaries"]), 20)
        self.assertEqual(len(self.value["parameter_bin_probe_receipts"]), 362)

    def test_source_histogram_and_summary_closure_is_exact(self):
        for row in self.value["persona_variant_rows"]:
            counts = row["source_counts"]
            self.assertEqual(counts["full"], counts["pilot"] + counts["full-residual"])
            self.assertEqual(
                [item["bin_id"] for item in row["parameter_bins"][:5]],
                list(catalog.BIN_ORDER),
            )
            for profile in catalog.PROFILE_ORDER:
                self.assertEqual(
                    sum(item["counts"][profile] for item in row["parameter_bins"]),
                    counts[profile],
                )
            for field in (
                "block_rounded_payload_bytes",
                "formal_tail_count",
                "raw_byte_sum",
                "source_count",
            ):
                self.assertEqual(
                    row["summaries"]["full"][field],
                    row["summaries"]["pilot"][field]
                    + row["summaries"]["full-residual"][field],
                )

    def test_tail_and_runtime_probe_coverage_is_exact(self):
        for summary in self.value["persona_summaries"]:
            self.assertEqual(summary["summaries"]["pilot"]["formal_tail_count"], 1)
            self.assertEqual(
                summary["summaries"]["full-residual"]["formal_tail_count"], 7
            )
            self.assertEqual(summary["summaries"]["full"]["formal_tail_count"], 8)
        suite = self.value["suite_summary"]["summaries"]
        self.assertEqual(suite["pilot"]["formal_tail_count"], 20)
        self.assertEqual(suite["full-residual"]["formal_tail_count"], 140)
        self.assertEqual(suite["full"]["formal_tail_count"], 160)
        ordinary = {
            row["variant_id"]
            for row in self.value["parameter_bin_probe_receipts"]
            if row["bin_id"] in catalog.BIN_ORDER
        }
        tails = {
            row["variant_id"]
            for row in self.value["parameter_bin_probe_receipts"]
            if row["bin_id"] == "formal-tail"
        }
        self.assertEqual(len(ordinary), 71)
        self.assertEqual(tails, set(catalog.TAIL_CAPABLE_VARIANTS))
        self.assertEqual(
            sum(
                row["bin_id"] in catalog.BIN_ORDER
                for row in self.value["parameter_bin_probe_receipts"]
            ),
            355,
        )

    def test_capacity_envelope_preserves_required_margin(self):
        maximum = max(
            self.value["persona_summaries"],
            key=lambda row: row["summaries"]["full"][
                "block_rounded_payload_bytes"
            ],
        )
        self.assertEqual(maximum["persona_id"], "p12")
        self.assertEqual(
            maximum["summaries"]["full"]["block_rounded_payload_bytes"],
            417_591_296,
        )
        for row in self.value["persona_summaries"]:
            self.assertTrue(row["capacity_check"]["passes_hard_cap"])
            self.assertLessEqual(
                row["summaries"]["full"]["block_rounded_payload_bytes"],
                480 * 2**20,
            )
            self.assertGreaterEqual(
                row["capacity_check"]["remaining_candidate_margin_bytes"],
                32 * 2**20,
            )
        suite = self.value["suite_summary"]
        self.assertEqual(
            suite["summaries"]["full"]["block_rounded_payload_bytes"],
            5_194_530_816,
        )
        self.assertLessEqual(
            suite["summaries"]["full"]["block_rounded_payload_bytes"],
            10 * 2**30,
        )

    def test_pilot_and_full_suite_metrics_are_pinned(self):
        summaries = self.value["suite_summary"]["summaries"]
        self.assertEqual(summaries["pilot"]["source_count"], 20_300)
        self.assertEqual(summaries["pilot"]["raw_byte_sum"], 499_678_429)
        self.assertEqual(
            summaries["pilot"]["block_rounded_payload_bytes"], 515_657_728
        )
        self.assertEqual(summaries["full"]["source_count"], 203_000)
        self.assertEqual(summaries["full"]["raw_byte_sum"], 5_034_302_718)
        self.assertEqual(summaries["full"]["nearest_rank_p50_bytes"], 8_192)
        self.assertEqual(summaries["full"]["nearest_rank_p95_bytes"], 129_024)
        self.assertEqual(summaries["full"]["maximum_bytes"], 2_621_440)

    def test_authority_is_negative_and_instance_identifiers_are_absent(self):
        self.assertEqual(set(self.value["authority"]), catalog.AUTHORITY_FIELDS)
        self.assertTrue(all(flag is False for flag in self.value["authority"].values()))
        self.assertIs(self.value["g0_contract_frozen"], False)
        claims = self.value["completion_claims"]
        self.assertIs(claims["source_instances_bound"], False)
        self.assertIs(claims["all_source_instance_parameters_bound"], False)
        self.assertIs(claims["all_parameter_bins_runtime_validated"], True)
        self.assertIs(claims["all_parameter_bin_runtime_probes_complete"], True)
        raw = catalog.canonical_json_bytes(self.value)
        for forbidden in (
            b'"source_id"',
            b'"materialization_id"',
            b'"scope_key"',
            b'"payload_seed"',
            b'"source_instances"',
        ):
            self.assertNotIn(forbidden, raw)

    def test_builder_is_detached_and_public_validator_is_strict(self):
        changed = catalog.build_aggregate_byte_distribution_catalog()
        changed["persona_variant_rows"][0]["parameter_bins"][0]["counts"][
            "pilot"
        ] = True
        fresh = catalog.build_aggregate_byte_distribution_catalog()
        self.assertIsNot(
            fresh["persona_variant_rows"][0]["parameter_bins"][0]["counts"][
                "pilot"
            ],
            True,
        )
        with self.assertRaises(catalog.PersonaV2AggregateByteDistributionCatalogError):
            catalog.validate_aggregate_byte_distribution_catalog(changed)

    def test_public_and_independent_validation_accepts_exact_body(self):
        self.assertTrue(catalog.validate_aggregate_byte_distribution_catalog(self.value))

    def test_independent_validator_rejects_rehashed_histogram_and_capacity_drift(self):
        mutation = copy.deepcopy(self.value)
        mutation["persona_variant_rows"][0]["summaries"]["full"][
            "nearest_rank_p50_bytes"
        ] += 1
        self._assert_independent_rejects_rehashed(mutation)

        mutation = copy.deepcopy(self.value)
        mutation["persona_summaries"][0]["capacity_check"][
            "passes_hard_cap"
        ] = False
        self._assert_independent_rejects_rehashed(mutation)

    def test_independent_validator_reconstructs_affine_anchor_maximality(self):
        mutation = copy.deepcopy(self.value)
        markdown = next(
            row for row in mutation["persona_variant_rows"]
            if row["variant_id"] == "markdown"
        )
        medium = next(
            row for row in markdown["parameter_bins"]
            if row["bin_id"] == "medium"
        )
        self._replace_variant_bin_with_valid_renderer_request(
            mutation,
            variant_id="markdown",
            bin_id="large",
            parameters=medium["renderer_parameters"],
        )
        self._assert_independent_rejects_rehashed(mutation)

    def test_independent_validator_rejects_off_lattice_and_aspect_raster_anchors(self):
        cases = (
            ("off-lattice", {"width": 100, "height": 400, "frame_or_event_count": 0}),
            ("aspect", {"width": 4_096, "height": 64, "frame_or_event_count": 0}),
        )
        for label, parameters in cases:
            with self.subTest(label=label):
                mutation = copy.deepcopy(self.value)
                self._replace_variant_bin_with_valid_renderer_request(
                    mutation,
                    variant_id="bmp",
                    bin_id="large" if label == "aspect" else "small",
                    parameters=parameters,
                )
                self._assert_independent_rejects_rehashed(mutation)

    def test_independent_validator_rejects_raster_over_max_pixels(self):
        mutation = copy.deepcopy(self.value)
        bmp = next(
            row for row in mutation["persona_variant_rows"]
            if row["variant_id"] == "bmp"
        )
        selected = next(
            row for row in bmp["parameter_bins"] if row["bin_id"] == "large"
        )
        selected["renderer_parameters"] = {
            "width": 4_096,
            "height": 4_097,
            "frame_or_event_count": 0,
        }
        selected["target_complexity"] = 4_096 * 4_097
        selected["exact_raw_bytes"] = 62 + 4 * ((4_096 + 31) // 32) * 4_097
        self._assert_independent_rejects_rehashed(mutation)

    def test_independent_validator_rejects_malicious_selected_renderer(self):
        def malicious_renderer(variant_id, parameters):
            rendered = self.renderer_probe_provider(variant_id, parameters)
            data = rendered["data"]
            rendered["data"] = bytes((data[0] ^ 1,)) + data[1:]
            return rendered

        with (
            mock.patch.object(
                independent.formal_validator,
                "validate_formal_source_recipe_catalog",
                return_value=True,
            ),
            self.assertRaises(
                independent.PersonaV2AggregateByteDistributionCatalogValidationError
            ),
        ):
            self._independent_validate(
                self.value,
                selected_renderer_probe_provider=malicious_renderer,
            )

    def test_provider_callback_cannot_mutate_catalog_or_registry(self):
        for target in ("catalog", "registry"):
            with self.subTest(target=target):
                value = copy.deepcopy(self.value)
                registry_value = copy.deepcopy(self.registry_value)
                calls = []

                def mutating_renderer(variant_id, parameters):
                    if not calls:
                        if target == "catalog":
                            value["completion_scope"] = "mutated-during-callback"
                        else:
                            registry_value["completion_scope"] = (
                                "mutated-during-callback"
                            )
                    calls.append(variant_id)
                    return self.renderer_probe_provider(variant_id, parameters)

                with (
                    mock.patch.object(
                        independent.formal_validator,
                        "validate_formal_source_recipe_catalog",
                        return_value=True,
                    ),
                    self.assertRaises(
                        independent.PersonaV2AggregateByteDistributionCatalogValidationError
                    ),
                ):
                    self._independent_validate(
                        value,
                        registry_value=registry_value,
                        selected_renderer_probe_provider=mutating_renderer,
                    )
                self.assertTrue(calls)

    def test_dependency_body_drift_is_rejected_before_selected_probes(self):
        changed = copy.deepcopy(self.registry_value)
        changed["completion_scope"] = "drifted"
        calls = []

        def recording_renderer(variant_id, parameters):
            calls.append(variant_id)
            return self.renderer_probe_provider(variant_id, parameters)

        with self.assertRaises(
            independent.PersonaV2AggregateByteDistributionCatalogValidationError
        ):
            self._independent_validate(
                self.value,
                registry_value=changed,
                selected_renderer_probe_provider=recording_renderer,
            )
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
