"""Regression and adversarial gates for formal recipe profile bindings."""

from __future__ import annotations

import copy
import hashlib
import unittest
from unittest import mock

from eval import persona_v2_artifact_common as artifact_common
from eval import persona_v2_formal_source_recipe_catalog as catalog
from eval import persona_v2_formal_source_recipe_catalog_validator as independent
from eval import persona_v2_format_implementation_registry as registry
from eval import persona_v2_source_inventory_profile as inventory
from eval import persona_v2_source_profile_catalog as historical
from eval import persona_v2_variant_catalog as variants


EXPECTED_CANONICAL_BYTES = 386_152
EXPECTED_SHA256 = (
    "0ac0906397c8d81b7504637fe119d45ae2ffa7acb7cb47b719c985121ce1b2df"
)


class FormalSourceRecipeCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.variant_value = variants.build_variant_catalog()
        cls.inventory_value = inventory.build_source_inventory_profile_catalog()
        cls.historical_value = historical.build_source_profile_catalog()
        cls.registry_value = registry.build_format_implementation_registry()
        cls.semantic_value = catalog._source_semantic_catalog_dependency()
        renderer_contract_provider, validator_contract_provider = (
            registry._contract_providers()
        )
        renderer_probe_provider, _ = registry._probe_providers()
        cls.renderer_contract_provider = staticmethod(renderer_contract_provider)
        cls.validator_contract_provider = staticmethod(validator_contract_provider)
        cls.renderer_probe_provider = staticmethod(renderer_probe_provider)
        cls.value = catalog.build_formal_source_recipe_catalog()

    def _independent_validate(
        self,
        value,
        *,
        registry_value=None,
        semantic_value=None,
        renderer_probe_provider=None,
    ):
        return independent.validate_formal_source_recipe_catalog(
            value,
            variant_catalog_value=self.variant_value,
            source_inventory_profile_value=self.inventory_value,
            format_implementation_registry_value=(
                self.registry_value if registry_value is None else registry_value
            ),
            source_semantic_membership_catalog_value=(
                self.semantic_value if semantic_value is None else semantic_value
            ),
            historical_source_profile_value=self.historical_value,
            renderer_contract_provider=self.renderer_contract_provider,
            validator_contract_provider=self.validator_contract_provider,
            renderer_probe_provider=(
                self.renderer_probe_provider
                if renderer_probe_provider is None
                else renderer_probe_provider
            ),
        )

    def _assert_independent_rejects_rehashed(self, value):
        raw = artifact_common.canonical_json_bytes(
            value,
            label="rehashed adversarial formal recipe catalog",
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
            self.assertRaises(
                independent.PersonaV2FormalSourceRecipeCatalogValidationError
            ),
        ):
            with mock.patch.object(
                independent.registry_validator,
                "validate_format_implementation_registry",
                return_value=True,
            ):
                self._independent_validate(value)

    def test_canonical_body_pin_and_both_validators(self):
        raw = catalog.canonical_json_bytes(self.value)
        self.assertEqual(len(raw), EXPECTED_CANONICAL_BYTES)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), EXPECTED_SHA256)
        self.assertEqual(
            independent.EXPECTED_CATALOG_CANONICAL_BYTES,
            EXPECTED_CANONICAL_BYTES,
        )
        self.assertEqual(independent.EXPECTED_CATALOG_SHA256, EXPECTED_SHA256)
        self.assertTrue(catalog.validate_formal_source_recipe_catalog(self.value))
        self.assertTrue(self._independent_validate(self.value))
        self.assertEqual(
            catalog.formal_source_recipe_catalog_sha256(self.value),
            EXPECTED_SHA256,
        )

    def test_exact_71_profile_slot_bijections_and_order(self):
        rows = self.value["recipe_profile_rows"]
        variant_order = [row["variant_id"] for row in self.variant_value["variant_rows"]]
        self.assertEqual([row["variant_id"] for row in rows], variant_order)
        self.assertEqual(len(rows), 71)
        for field in (
            "variant_id",
            "source_inventory_profile_id",
            "semantic_profile_id",
            "source_recipe_slot_id",
            "recipe_profile_id",
        ):
            self.assertEqual(len({row[field] for row in rows}), 71)
        self.assertEqual(
            len(
                {
                    row["content_policy"]["content_template_profile_id"]
                    for row in rows
                }
            ),
            71,
        )
        self.assertEqual(
            len(
                {
                    row["content_policy"]["content_template_slot_id"]
                    for row in rows
                }
            ),
            71,
        )
        self.assertEqual(
            len(
                {
                    row["filename_policy"]["filename_template_profile_id"]
                    for row in rows
                }
            ),
            71,
        )
        self.assertEqual(
            len(
                {
                    row["filename_policy"]["filename_template_slot_id"]
                    for row in rows
                }
            ),
            71,
        )
        for row in rows:
            variant_id = row["variant_id"]
            self.assertEqual(
                row["source_recipe_slot_id"],
                f"persona-v2-source-recipe-slot-{variant_id}-v2",
            )
            self.assertEqual(
                row["recipe_profile_id"],
                f"persona-v2-formal-source-recipe-profile-{variant_id}-v2",
            )
            self.assertEqual(row["binding_status"], "profile-bound-instance-unbound")

    def test_input_bindings_pin_all_four_upstreams_without_rewriting_them(self):
        bindings = {row["name"]: row for row in self.value["input_bindings"]}
        self.assertEqual(
            self.value["input_binding_order"],
            [
                "persona-v2-variant-catalog",
                "persona-v2-source-inventory-profile-catalog",
                "persona-v2-format-implementation-registry",
                "persona-v2-source-semantic-membership-catalog",
            ],
        )
        for name, (expected_bytes, expected_sha) in (
            catalog.EXPECTED_DEPENDENCY_PINS.items()
        ):
            self.assertEqual(bindings[name]["canonical_bytes"], expected_bytes)
            self.assertEqual(bindings[name]["sha256"], expected_sha)
        for row in self.inventory_value["source_profile_rows"]:
            self.assertEqual(row["source_recipe"]["binding_status"], "reserved-unbound")
            self.assertEqual(row["source_recipe"]["profile_id"], "not-bound")
            self.assertIs(row["source_recipe"]["parameters_complete"], False)

    def test_content_and_filename_profile_policies_bind_semantic_slots(self):
        rows = {row["variant_id"]: row for row in self.value["recipe_profile_rows"]}
        expected_roles = {
            "md": "narrative-document",
            "csv": "tabular-record",
            "docx": "word-processing-document",
            "warehouse-zip": "domain-binary-record",
        }
        for variant_id, role in expected_roles.items():
            row = rows[variant_id]
            content = row["content_policy"]
            filename = row["filename_policy"]
            self.assertEqual(content["document_role"], role)
            self.assertEqual(
                content["content_template_slot_id"],
                f"persona-v2-content-template-slot-{variant_id}-v2",
            )
            self.assertEqual(
                filename["filename_template_slot_id"],
                f"persona-v2-filename-template-slot-{variant_id}-v2",
            )
            self.assertIs(content["content_instance_values_bound"], False)
            self.assertIs(
                content["semantic_content_adapter_conformance_attested"], False
            )
            self.assertIs(filename["basename_instance_bound"], False)
            self.assertIs(filename["scope_casefold_uniqueness_attested"], False)
        self.assertIn(
            "empty-present-fact-profile-only-no-search-participation",
            {row["content_policy"]["fact_profile_rule"] for row in rows.values()},
        )
        self.assertIn(
            "source-owned-nonempty-present-fact-profile-required",
            {row["content_policy"]["fact_profile_rule"] for row in rows.values()},
        )
        filename_core = self.value["policy_catalogs"]["filename_core_policy"]
        self.assertEqual(filename_core["max_basename_bytes"], 120)
        self.assertTrue(filename_core["collision_suffix_from_internal_identity_forbidden"])
        self.assertEqual(
            filename_core["casefold_uniqueness_check_phase"],
            "downstream-final-source-plan",
        )

    def test_each_row_binds_exact_contract_and_runtime_receipt_ownership(self):
        registry_rows = {
            row["variant_id"]: row
            for row in self.registry_value["implementation_rows"]
        }
        contracts = {
            row["binding_id"]: row for row in self.registry_value["contract_bindings"]
        }
        for row in self.value["recipe_profile_rows"]:
            source = registry_rows[row["variant_id"]]
            implementation = source["implementation"]
            binding = row["implementation_binding"]
            runtime = row["runtime_conformance_binding"]
            self.assertEqual(binding["implementation_pair_id"], implementation["pair_id"])
            self.assertEqual(runtime["implementation_pair_id"], implementation["pair_id"])
            self.assertEqual(runtime["variant_id"], row["variant_id"])
            self.assertEqual(
                binding["renderer"]["contract_sha256"],
                contracts[implementation["renderer_binding_id"]]["sha256"],
            )
            self.assertEqual(
                binding["validator"]["contract_sha256"],
                contracts[implementation["validator_binding_id"]]["sha256"],
            )
            receipt_raw = artifact_common.canonical_json_bytes(
                source["conformance_receipt"],
                label="test runtime conformance receipt",
                max_bytes=128 * 1024,
            )
            self.assertEqual(
                runtime["conformance_receipt_sha256"],
                hashlib.sha256(receipt_raw).hexdigest(),
            )
            self.assertTrue(runtime["runtime_validator_accepted_all"])

    def test_complexity_formula_quantization_and_lane_policies_are_profile_only(self):
        by_id = {row["variant_id"]: row for row in self.value["recipe_profile_rows"]}
        self.assertEqual(
            by_id["md"]["complexity_byte_policy"]["complexity"]["inclusive_maximum"],
            70,
        )
        self.assertEqual(
            by_id["pdf-text"]["complexity_byte_policy"]["complexity"]["measure"],
            "text-pages",
        )
        self.assertEqual(
            by_id["png"]["complexity_byte_policy"]["parameter_shape"][
                "complexity_parameters"
            ],
            ["width", "height", "frame_or_event_count"],
        )
        self.assertEqual(
            by_id["png"]["complexity_byte_policy"]["formula"]["formula_kind"],
            "exact-expression",
        )
        for row in by_id.values():
            policy = row["complexity_byte_policy"]
            self.assertIs(policy["selected_parameter_values_present"], False)
            self.assertIs(policy["selected_target_complexity_present"], False)
            self.assertIs(policy["selected_target_bytes_present"], False)
            self.assertEqual(
                policy["target_bytes_binding_mode"],
                "derived-exactly-by-renderer-formula",
            )
        lanes = self.value["policy_catalogs"]["lane_contracts"]
        self.assertTrue(
            lanes["lane_separation"][
                "byte_stress_reuses_only_format_encoding_and_validator_identity"
            ]
        )
        self.assertEqual(lanes["byte_stress"]["lane_local_gate_role"], "raw_only")
        self.assertEqual(lanes["byte_stress"]["lane_local_requested_chunks"], 0)

    def test_gate_role_chunk_policies_keep_quota_complexity_and_observation_separate(self):
        policies = {
            row["gate_role"]: row
            for row in self.value["policy_catalogs"]["gate_role_chunk_policies"]
        }
        contributor = policies["contract_contributor"]
        incidental = policies["incidental_searchable"]
        raw = policies["raw_only"]
        self.assertEqual(contributor["requested_chunks"]["inclusive_minimum"], 1)
        self.assertEqual(contributor["requested_chunks"]["inclusive_maximum"], 70)
        self.assertIs(contributor["requested_chunks_equal_format_complexity"], False)
        self.assertEqual(incidental["requested_chunks"]["exact_value"], 0)
        self.assertTrue(
            incidental["expected_incidental_chunks_upper"][
                "assignment_required_at_source_instance"
            ]
        )
        self.assertEqual(raw["observed_chunk_gate"], "actual-equals-zero")
        wave = self.value["policy_catalogs"]["dynamic_incidental_wave_cap_policy"]
        self.assertTrue(wave["exact_integer_profile_and_checkpoint_table"])
        self.assertIs(wave["source_instance_assignments_present"], False)
        profile_rows = {row["profile"]: row for row in wave["profile_rows"]}
        self.assertEqual(set(profile_rows), {"full", "pilot"})
        expected_inputs = {
            "full": (135_000, 210_000, 15_000, 30_000),
            "pilot": (13_500, 21_000, 1_500, 3_000),
        }
        expected_checkpoints = {
            "full": (
                ("W0", 120_000, 0, 15_000, 30_000),
                ("W1", 120_000, 24_000, 15_000, 30_000),
                ("W2", 120_000, 24_000, 15_000, 30_000),
                ("W3", 120_000, 48_000, 15_000, 30_000),
                ("W4", 120_000, 60_000, 15_000, 30_000),
                ("W5-pre-purge", 124_800, 64_800, 10_200, 20_400),
                ("W5-final", 120_000, 60_000, 15_000, 30_000),
            ),
            "pilot": (
                ("W0", 12_000, 0, 1_500, 3_000),
                ("W1", 12_000, 2_400, 1_500, 3_000),
                ("W2", 12_000, 2_400, 1_500, 3_000),
                ("W3", 12_000, 4_800, 1_500, 3_000),
                ("W4", 12_000, 6_000, 1_500, 3_000),
                ("W5-pre-purge", 12_480, 6_480, 1_020, 2_040),
                ("W5-final", 12_000, 6_000, 1_500, 3_000),
            ),
        }
        for profile, row in profile_rows.items():
            self.assertEqual(
                (
                    row["current_eligible_ceiling"],
                    row["current_plus_history_eligible_ceiling"],
                    row["base_incidental_current"],
                    row["base_incidental_current_plus_history"],
                ),
                expected_inputs[profile],
            )
            self.assertEqual(
                tuple(
                    (
                        checkpoint["checkpoint"],
                        checkpoint["contributor_current_chunks"],
                        checkpoint["contributor_history_only_chunks"],
                        checkpoint["incidental_current_cap"],
                        checkpoint["incidental_current_plus_history_cap"],
                    )
                    for checkpoint in row["checkpoint_rows"]
                ),
                expected_checkpoints[profile],
            )

    def test_counts_close_rowwise_and_at_gate_role_totals(self):
        for row in self.value["recipe_profile_rows"]:
            counts = row["source_count_projection"]
            self.assertEqual(counts["full"], counts["pilot"] + counts["full-residual"])
            self.assertTrue(counts["projection_only_no_source_instances"])
        self.assertEqual(self.value["coverage"], catalog.EXPECTED_COVERAGE)

    def test_all_authority_and_instance_completion_claims_remain_false(self):
        self.assertEqual(set(self.value["authority"]), catalog.AUTHORITY_FIELDS)
        self.assertTrue(all(flag is False for flag in self.value["authority"].values()))
        self.assertIs(self.value["g0_contract_frozen"], False)
        claims = self.value["completion_claims"]
        for key in (
            "physical_source_materialization_complete",
            "selected_complexity_and_bytes_present",
            "semantic_payload_materialization_complete",
            "source_instance_parameter_values_bound",
            "source_instances_bound",
            "source_level_allocation_solution_present",
        ):
            self.assertIs(claims[key], False)
        raw = catalog.canonical_json_bytes(self.value)
        for forbidden_key in (
            b'"source_id"',
            b'"materialization_id"',
            b'"scope_key"',
            b'"payload_seed"',
            b'"solution_sha256"',
        ):
            self.assertNotIn(forbidden_key, raw)

    def test_builder_returns_a_detached_value(self):
        changed = catalog.build_formal_source_recipe_catalog()
        changed["recipe_profile_rows"][0]["recipe_profile_id"] = "tampered"
        fresh = catalog.build_formal_source_recipe_catalog()
        self.assertNotEqual(
            changed["recipe_profile_rows"][0]["recipe_profile_id"],
            fresh["recipe_profile_rows"][0]["recipe_profile_id"],
        )

    def test_public_validator_rejects_policy_and_authority_mutations(self):
        cases = []
        mutation = copy.deepcopy(self.value)
        mutation["authority"]["authorizes_g0_freeze"] = True
        cases.append(("authority", mutation))
        mutation = copy.deepcopy(self.value)
        mutation["recipe_profile_rows"][0]["source_recipe_slot_id"] = (
            mutation["recipe_profile_rows"][1]["source_recipe_slot_id"]
        )
        cases.append(("slot", mutation))
        mutation = copy.deepcopy(self.value)
        mutation["recipe_profile_rows"][0]["content_policy"]["query_oracle_inputs_allowed"] = True
        cases.append(("query-input", mutation))
        mutation = copy.deepcopy(self.value)
        mutation["policy_catalogs"]["filename_core_policy"]["max_basename_bytes"] = 121
        cases.append(("filename", mutation))
        mutation = copy.deepcopy(self.value)
        mutation["recipe_profile_rows"][0]["complexity_byte_policy"][
            "selected_target_bytes_present"
        ] = True
        cases.append(("selected-bytes", mutation))
        mutation = copy.deepcopy(self.value)
        mutation["coverage"]["total"]["full"] += 1
        cases.append(("count", mutation))
        for label, candidate in cases:
            with self.subTest(label=label), self.assertRaises(
                catalog.PersonaV2FormalSourceRecipeCatalogError
            ):
                catalog.validate_formal_source_recipe_catalog(candidate)

    def test_independent_validator_rejects_rehashed_receipt_and_contract_rethreading(self):
        first, second = self.value["recipe_profile_rows"][:2]
        mutation = copy.deepcopy(self.value)
        mutation["recipe_profile_rows"][0]["runtime_conformance_binding"] = copy.deepcopy(
            second["runtime_conformance_binding"]
        )
        mutation["recipe_profile_rows"][0]["runtime_conformance_binding"]["variant_id"] = first[
            "variant_id"
        ]
        self._assert_independent_rejects_rehashed(mutation)

        mutation = copy.deepcopy(self.value)
        mutation["recipe_profile_rows"][0]["implementation_binding"]["validator"] = copy.deepcopy(
            second["implementation_binding"]["validator"]
        )
        self._assert_independent_rejects_rehashed(mutation)

    def test_independent_validator_rejects_rethreaded_registry_dependency(self):
        malicious_registry = copy.deepcopy(self.registry_value)
        malicious_registry["implementation_rows"][0]["conformance_receipt"] = copy.deepcopy(
            malicious_registry["implementation_rows"][1]["conformance_receipt"]
        )
        with self.assertRaises(
            independent.PersonaV2FormalSourceRecipeCatalogValidationError
        ):
            self._independent_validate(self.value, registry_value=malicious_registry)

    def test_independent_registry_join_rejects_contract_identity_rethreading(self):
        malicious_registry = copy.deepcopy(self.registry_value)
        implementation = malicious_registry["implementation_rows"][0][
            "implementation"
        ]
        binding = next(
            row
            for row in malicious_registry["contract_bindings"]
            if row["binding_id"] == implementation["renderer_binding_id"]
        )
        binding["implementation_id"] = "rethreaded-renderer"
        with self.assertRaises(
            independent.PersonaV2FormalSourceRecipeCatalogValidationError
        ):
            independent._validate_registry_ownership(malicious_registry)

    def test_independent_semantic_join_rejects_rethreaded_profile_and_slots(self):
        cases = []
        mutation = copy.deepcopy(self.semantic_value)
        mutation["semantic_profiles"][0]["source_profile_id"] = mutation[
            "semantic_profiles"
        ][1]["source_profile_id"]
        cases.append(("source-profile", mutation))
        mutation = copy.deepcopy(self.semantic_value)
        mutation["semantic_profiles"][0]["content_template_slot_id"] = mutation[
            "semantic_profiles"
        ][1]["content_template_slot_id"]
        cases.append(("content-slot", mutation))
        mutation = copy.deepcopy(self.semantic_value)
        mutation["semantic_profiles"][0]["filename_template_slot_id"] = mutation[
            "semantic_profiles"
        ][1]["filename_template_slot_id"]
        cases.append(("filename-slot", mutation))
        mutation = copy.deepcopy(self.semantic_value)
        mutation["semantic_profiles"][0]["semantic_profile_id"] = mutation[
            "semantic_profiles"
        ][1]["semantic_profile_id"]
        cases.append(("semantic-profile", mutation))
        mutation = copy.deepcopy(self.semantic_value)
        mutation["semantic_profiles"][0][
            "formal_recipe_binding_status"
        ] = "profile-bound-instance-unbound"
        cases.append(("reservation-status", mutation))
        for label, semantic_value in cases:
            with self.subTest(label=label), self.assertRaises(
                independent.PersonaV2FormalSourceRecipeCatalogValidationError
            ):
                independent._expected_value(
                    self.variant_value,
                    self.inventory_value,
                    self.registry_value,
                    semantic_value,
                    self.value["input_bindings"],
                )

    def test_independent_validator_rejects_malicious_renderer_provider(self):
        def malicious_renderer_provider(variant_id, parameters):
            rendered = self.renderer_probe_provider(variant_id, parameters)
            data = rendered["data"]
            rendered["data"] = bytes([data[0] ^ 1]) + data[1:]
            return rendered

        with self.assertRaises(
            independent.PersonaV2FormalSourceRecipeCatalogValidationError
        ):
            self._independent_validate(
                self.value, renderer_probe_provider=malicious_renderer_provider
            )

    def test_provider_callback_cannot_mutate_formal_or_semantic_body(self):
        for target in ("formal", "semantic"):
            with self.subTest(target=target):
                formal_value = copy.deepcopy(self.value)
                semantic_value = copy.deepcopy(self.semantic_value)
                calls = []

                def mutating_renderer_provider(variant_id, parameters):
                    if not calls:
                        if target == "formal":
                            formal_value["completion_scope"] = (
                                "mutated-during-provider-callback"
                            )
                        else:
                            semantic_value["semantic_profiles"][0][
                                "content_template_slot_id"
                            ] = "mutated-during-provider-callback"
                    calls.append(variant_id)
                    return self.renderer_probe_provider(variant_id, parameters)

                with self.assertRaises(
                    independent.PersonaV2FormalSourceRecipeCatalogValidationError
                ):
                    self._independent_validate(
                        formal_value,
                        semantic_value=semantic_value,
                        renderer_probe_provider=mutating_renderer_provider,
                    )
                self.assertTrue(calls)

    def test_independent_validator_rejects_dependency_body_drift(self):
        changed_variant = copy.deepcopy(self.variant_value)
        changed_variant["variant_rows"][0]["family"] = "wrong"
        with self.assertRaises(
            independent.PersonaV2FormalSourceRecipeCatalogValidationError
        ):
            independent.validate_formal_source_recipe_catalog(
                self.value,
                variant_catalog_value=changed_variant,
                source_inventory_profile_value=self.inventory_value,
                format_implementation_registry_value=self.registry_value,
                source_semantic_membership_catalog_value=self.semantic_value,
                historical_source_profile_value=self.historical_value,
                renderer_contract_provider=self.renderer_contract_provider,
                validator_contract_provider=self.validator_contract_provider,
                renderer_probe_provider=self.renderer_probe_provider,
            )

        changed_semantic = copy.deepcopy(self.semantic_value)
        changed_semantic["semantic_profiles"][0]["content_template_slot_id"] = (
            "rethreaded-content-template-slot"
        )
        with self.assertRaises(
            independent.PersonaV2FormalSourceRecipeCatalogValidationError
        ):
            self._independent_validate(self.value, semantic_value=changed_semantic)


if __name__ == "__main__":
    unittest.main()
