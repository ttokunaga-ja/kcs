"""Focused and adversarial gates for pre-solve lifecycle demand v2."""

from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import unittest
from unittest import mock

from eval import persona_v2_artifact_common as artifact_common
from eval import persona_v2_chunk_accounting as chunk_accounting
from eval import persona_v2_chunk_accounting_validator as chunk_accounting_validator
from eval import persona_v2_contract as envelope
from eval import persona_v2_lifecycle_demand as demand
from eval import persona_v2_lifecycle_demand_validator as independent
from eval import persona_v2_overlay_contract as overlay


EXPECTED_CANONICAL_BYTES = 463_571
EXPECTED_SHA256 = (
    "32e0aaf88632803d41266152b81e2cc2917111d69f6dfb03be0621920c8a0080"
)


class PersonaV2LifecycleDemandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = demand.build_lifecycle_demand()
        cls.accounting_value = chunk_accounting.build_chunk_accounting_contract()
        cls.envelope_value = envelope.build_envelope_contract()
        cls.overlay_value = overlay.build_overlay_contract()

    def _validate_independent(
        self,
        value,
        *,
        accounting_value=None,
        envelope_value=None,
        overlay_value=None,
    ):
        return independent.validate_lifecycle_demand(
            value,
            chunk_accounting_value=(
                self.accounting_value
                if accounting_value is None
                else accounting_value
            ),
            envelope_value=(
                self.envelope_value if envelope_value is None else envelope_value
            ),
            overlay_contract_value=(
                self.overlay_value if overlay_value is None else overlay_value
            ),
        )

    def _assert_independent_rejects_rehashed(self, value):
        raw = artifact_common.canonical_json_bytes(
            value,
            label="rehashed lifecycle demand",
            max_bytes=demand.MAX_LIFECYCLE_DEMAND_BYTES,
        )
        with (
            mock.patch.object(
                independent,
                "EXPECTED_LIFECYCLE_DEMAND_CANONICAL_BYTES",
                len(raw),
            ),
            mock.patch.object(
                independent,
                "EXPECTED_LIFECYCLE_DEMAND_SHA256",
                hashlib.sha256(raw).hexdigest(),
            ),
            self.assertRaises(
                independent.PersonaV2LifecycleDemandValidationError
            ),
        ):
            self._validate_independent(value)

    def test_canonical_pin_and_non_authorizing_boundary(self):
        raw = demand.canonical_json_bytes(self.value)
        self.assertEqual(len(raw), EXPECTED_CANONICAL_BYTES)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), EXPECTED_SHA256)
        self.assertEqual(demand.lifecycle_demand_sha256(self.value), EXPECTED_SHA256)
        self.assertTrue(demand.validate_lifecycle_demand(self.value))
        self.assertTrue(self._validate_independent(self.value))
        self.assertEqual(set(self.value["authority"]), demand.AUTHORITY_FIELDS)
        self.assertTrue(
            all(type(flag) is bool and flag is False for flag in self.value["authority"].values())
        )
        self.assertIs(self.value["g0_contract_frozen"], False)
        self.assertIs(self.value["compiled_history_plan"], False)
        self.assertIs(
            self.value["completion_claims"]["source_instance_matching_complete"],
            False,
        )
        self.assertIs(
            self.value["boundary_assertions"]["evaluation_target_mapping_present"],
            False,
        )
        self.assertIs(
            self.value["boundary_assertions"]["accounting_sidecar_bound"],
            True,
        )
        self.assertIs(
            self.value["completion_claims"]["chunk_accounting_contract_bound"],
            True,
        )
        accounting_raw = chunk_accounting.canonical_json_bytes(self.accounting_value)
        self.assertEqual(
            self.value["input_binding_order"],
            ["persona-v2-chunk-accounting"],
        )
        self.assertEqual(
            (
                self.value["input_bindings"][0]["canonical_bytes"],
                self.value["input_bindings"][0]["sha256"],
            ),
            (len(accounting_raw), hashlib.sha256(accounting_raw).hexdigest()),
        )
        self.assertEqual(
            (len(accounting_raw), hashlib.sha256(accounting_raw).hexdigest()),
            (
                demand.EXPECTED_CHUNK_ACCOUNTING_CANONICAL_BYTES,
                demand.EXPECTED_CHUNK_ACCOUNTING_SHA256,
            ),
        )

    def test_twenty_personas_each_have_exact_105_anonymous_capabilities(self):
        rows = self.value["persona_demands"]
        self.assertEqual(
            [row["origin_payload"]["persona_id"] for row in rows],
            list(demand.PERSONA_IDS),
        )
        suite_allocation_counts = {
            allocation_class: 0
            for allocation_class in demand.ALLOCATION_CLASS_ORDER
        }
        for row in rows:
            capabilities = row["origin_payload"]["anonymous_capabilities"]
            self.assertEqual(len(capabilities), 105)
            self.assertEqual(
                [item["anonymous_capability_key"] for item in capabilities],
                [f"anonymous-capability-{index:03d}" for index in range(1, 106)],
            )
            self.assertEqual(len({item["anonymous_capability_key"] for item in capabilities}), 105)
            per_allocation = {
                allocation_class: 0
                for allocation_class in demand.ALLOCATION_CLASS_ORDER
            }
            per_class = {}
            for item in capabilities:
                per_allocation[item["allocation_class"]] += 1
                per_class[item["capability_class_key"]] = (
                    per_class.get(item["capability_class_key"], 0) + 1
                )
                suite_allocation_counts[item["allocation_class"]] += 1
                if item["allocation_class"] == "I":
                    self.assertEqual(item["gate_role_requirement"], "incidental_searchable")
                    self.assertEqual(item["history_cohort_keys"], [])
                else:
                    self.assertEqual(item["gate_role_requirement"], "contract_contributor")
                    self.assertEqual(item["history_cohort_keys"], [item["allocation_class"]])
            self.assertEqual(
                per_allocation,
                {"P": 15, "X": 20, "Y": 30, "N": 0, "U": 35, "I": 5},
            )
            self.assertEqual(
                per_class,
                {
                    "m3-1-current": 30,
                    "same-scope-rename": 5,
                    "cross-scope-move": 5,
                    "old-wording-history": 10,
                    "locale-history": 10,
                    "archive-history": 10,
                    "final-deleted": 10,
                    "current-restored": 10,
                    "purged-negative": 15,
                },
            )
        self.assertEqual(
            suite_allocation_counts,
            {"P": 300, "X": 400, "Y": 600, "N": 0, "U": 700, "I": 100},
        )
        self.assertEqual(self.value["suite_summary"]["anonymous_capability_count"], 2_100)

    def test_full_profile_reuses_exact_pilot_origin_payload_bytes(self):
        for row in self.value["persona_demands"]:
            payload = row["origin_payload"]
            self.assertEqual(payload["origin_key"], "pilot")
            raw = artifact_common.canonical_json_bytes(
                payload,
                label="test pilot origin payload",
                max_bytes=256 * 1024,
            )
            bindings = row["profile_reuse_bindings"]
            self.assertEqual([item["profile_key"] for item in bindings], ["pilot", "full"])
            self.assertEqual(bindings[0]["origin_payload_canonical_bytes"], len(raw))
            self.assertEqual(bindings[0]["origin_payload_sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(
                bindings[0]["origin_payload_canonical_bytes"],
                bindings[1]["origin_payload_canonical_bytes"],
            )
            self.assertEqual(
                bindings[0]["origin_payload_sha256"],
                bindings[1]["origin_payload_sha256"],
            )
            self.assertTrue(
                all(
                    item["reuse_mode"] == "direct-byte-identical-origin-payload"
                    for item in bindings
                )
            )

    def test_event_catalog_covers_w1_w5_scope_location_and_exact_integer_deltas(self):
        events = self.value["event_templates"]
        self.assertEqual({row["wave"] for row in events}, set(demand.WAVE_ORDER))
        self.assertEqual(
            {row["allocation_class"] for row in events},
            set(demand.ALLOCATION_CLASS_ORDER),
        )
        scope_keys = {
            row["scope_relation_rule_key"] for row in self.value["scope_relation_rules"]
        }
        location_keys = {
            row["location_transition_rule_key"]
            for row in self.value["location_transition_rules"]
        }
        for row in events:
            self.assertIn(row["scope_relation_rule_key"], scope_keys)
            self.assertIn(row["location_transition_rule_key"], location_keys)
            for dimension in (
                "current_transition_units",
                "historical_transition_units",
            ):
                cell = row["delta_rule"][dimension]
                self.assertIs(type(cell["coefficient"]), int)
                self.assertIn(cell["coefficient"], {0, 1})
                self.assertIn(cell["direction"], {"preserve", "increase", "decrease"})
                if cell["coefficient"] == 0:
                    self.assertEqual(cell, {"coefficient": 0, "direction": "preserve", "symbol": "zero"})
                else:
                    self.assertIn(cell["direction"], {"increase", "decrease"})
                    self.assertNotEqual(cell["symbol"], "zero")
        self.assertEqual(
            [row["wave"] for row in self.value["wave_delta_rules"]],
            list(demand.WAVE_ORDER),
        )
        self.assertEqual(
            self.value["wave_delta_rules"][1]["current_transition_unit_terms"],
            [],
        )
        self.assertEqual(
            self.value["wave_delta_rules"][1]["historical_transition_unit_terms"],
            [],
        )
        self.assertEqual(
            self.value["wave_delta_rules"][4]["required_symbolic_equalities"],
            [{"left_symbol": "qN", "relation": "must-equal", "right_symbol": "qP"}],
        )

    def test_cross_scope_move_is_incidental_and_uses_four_exact_ledgers(self):
        class_contract = {
            row["capability_class_key"]: row
            for row in self.value["capability_class_contracts"]
        }["cross-scope-move"]
        self.assertEqual(class_contract["allocation_class"], "I")
        self.assertEqual(class_contract["gate_role_requirement"], "incidental_searchable")
        self.assertEqual(class_contract["history_cohort_keys"], [])
        self.assertEqual(class_contract["anonymous_capability_count_per_persona"], 5)

        events = {
            row["event_template_key"]: row for row in self.value["event_templates"]
        }
        move = events["lifecycle-template-w2-cross-scope-move-i-v2"]
        self.assertEqual(move["allocation_class"], "I")
        self.assertEqual(move["gate_role_requirement"], "incidental_searchable")
        self.assertEqual(move["history_cohort_keys"], [])
        self.assertEqual(
            move["operation_kind"],
            "cross-scope-source-delete-destination-ingest",
        )
        self.assertEqual(
            move["cardinality_binding_mode"],
            "post-w0-observed-ledger-symbol-with-pre-solve-upper",
        )
        self.assertEqual(
            move["delta_rule_interpretation"],
            "contract-participation-search-semantic-endpoint-only",
        )
        self.assertEqual(
            move["metric_projection_contract_keys"],
            ["cross-scope-move-metric-v1"],
        )

        metric = self.value["cross_scope_move_metric_contract"]
        self.assertEqual(metric["observed_symbol"], "qIM")
        self.assertEqual(metric["matched_move_source_count_symbol"], "nIM")
        self.assertEqual(metric["matched_move_source_count_exact"], 5)
        self.assertEqual(metric["pre_solve_upper_symbol"], "uIM")
        self.assertEqual(metric["anchor_count_per_persona"], 5)
        self.assertEqual(metric["per_anchor_observed_lower"], 1)
        self.assertEqual(metric["per_anchor_observed_upper"], 70)
        self.assertEqual(metric["pre_solve_upper"], 350)
        self.assertEqual(metric["observed_symbol_lower"], 5)
        self.assertEqual(metric["observed_symbol_upper"], 350)
        self.assertEqual(
            metric["observed_symbol_definition"],
            "per-person-sum-of-five-w0-observed-source-endpoint-chunk-counts",
        )
        self.assertIs(metric["per_anchor_positive_observation_required"], True)
        self.assertIs(metric["product_move_lineage_semantics_allowed"], False)
        self.assertIs(metric["actual_physical_delta_attested"], False)
        self.assertEqual(
            metric["delta_evidence_status"],
            "planned-conditional-not-actual-attested",
        )
        self.assertIs(metric["compiled_literal_delta_available"], False)
        self.assertIs(metric["compiled_literal_requires_w0_attestation"], True)
        self.assertEqual(
            metric["observed_symbol_aggregation_rule"],
            "sum-exact-five-matched-anchor-observations",
        )
        self.assertIs(metric["destination_objects_absent_before_move_required"], True)
        self.assertIs(
            metric["destination_live_materialization_absent_before_move_required"],
            True,
        )
        self.assertIs(metric["raw_objects_absent_before_move_required"], True)
        self.assertEqual(metric["source_scope_live_binding_multiplicity_exact"], 1)
        self.assertEqual(
            metric["raw_bytes_relation"],
            "byte-identical-source-to-destination",
        )
        self.assertEqual(
            metric["tool_profile_relation"], "must-match-source-exactly"
        )
        self.assertEqual(
            metric["generation_profile_relation"], "must-match-source-exactly"
        )
        self.assertEqual(
            metric["chunk_configuration_relation"], "must-match-source-exactly"
        )
        self.assertEqual(
            metric["chunk_set_relation"],
            "exact-carry-forward-source-to-destination",
        )
        self.assertEqual(
            metric["destination_endpoint_collision_precondition"],
            "no-live-historical-or-cas-endpoint-collision",
        )
        self.assertEqual(
            metric["planned_destination_endpoint_precondition"],
            "all-planned-destination-scope-chunk-endpoints-are-pairwise-distinct",
        )
        self.assertIs(
            metric["planned_destination_endpoints_pairwise_noncolliding_required"],
            True,
        )
        self.assertEqual(
            metric["planned_destination_managed_location_precondition"],
            "all-planned-destination-scope-path-materializations-are-pairwise-distinct",
        )
        self.assertIs(
            metric[
                "planned_destination_managed_locations_pairwise_distinct_required"
            ],
            True,
        )
        self.assertEqual(
            metric["planned_destination_materialization_absence_precondition"],
            "each-destination-scope-path-has-no-live-materialization-before-its-move",
        )
        self.assertEqual(
            metric["accounting_sidecar_binding_status"],
            "bound-and-authenticated",
        )
        operation = metric["accounting_operation_contract"]
        self.assertEqual(operation["operation_id"], "cross-scope-move-incidental")
        self.assertEqual(operation["source_participation"], "incidental_searchable")
        self.assertEqual(
            operation["runtime_interpretation"],
            "source-delete-plus-destination-ingest-across-independent-kcs-stores-not-product-cross-scope-lineage-inference",
        )
        self.assertEqual(len(operation["preconditions"]), 10)
        terms = {
            (row["metric_id"], row["projection"]): {
                "coefficient": row["coefficient"],
                "direction": row["direction"],
                "symbol": row["symbol"],
            }
            for row in operation["delta_terms"]
        }
        self.assertEqual(
            {metric_id for metric_id, _ in terms},
            {
                "search-semantic-endpoint-v1",
                "persona-global-chunk-hash-v1",
                "history-path-binding-v1",
                "physical-storage-v1",
            },
        )
        zero = {"coefficient": 0, "direction": "preserve", "symbol": "zero"}
        plus_q_im = {"coefficient": 1, "direction": "increase", "symbol": "qIM"}
        for projection in (
            "contract-current",
            "contract-history-only",
            "incidental-current",
        ):
            self.assertEqual(
                terms[("search-semantic-endpoint-v1", projection)],
                zero,
            )
        self.assertEqual(
            terms[("search-semantic-endpoint-v1", "incidental-history-only")],
            plus_q_im,
        )
        self.assertEqual(
            terms[("persona-global-chunk-hash-v1", "distinct-chunk-hashes")],
            zero,
        )
        self.assertEqual(
            terms[("history-path-binding-v1", "reachable-path-bindings")],
            plus_q_im,
        )
        self.assertEqual(
            terms[("physical-storage-v1", "chunk-cas-regular-objects")],
            plus_q_im,
        )
        self.assertEqual(
            terms[("physical-storage-v1", "chunk-cas-inodes")],
            plus_q_im,
        )
        self.assertEqual(
            terms[("physical-storage-v1", "raw-cas-regular-objects")],
            {"coefficient": 1, "direction": "increase", "symbol": "nIM"},
        )
        self.assertEqual(
            terms[("physical-storage-v1", "raw-cas-inodes")],
            {"coefficient": 1, "direction": "increase", "symbol": "nIM"},
        )
        self.assertEqual(
            terms[("physical-storage-v1", "managed-source-regular-files")],
            zero,
        )
        self.assertEqual(
            terms[("physical-storage-v1", "managed-source-inodes")],
            zero,
        )
        crosswalk_pairs = [
            (row["accounting_metric_id"], mapping["accounting_projection"])
            for row in metric["ledger_dimension_schema_crosswalk"]
            for mapping in row["projection_mappings"]
        ]
        self.assertEqual(crosswalk_pairs, list(terms))
        self.assertIs(metric["physical_file_inode_object_receipts_required"], True)
        self.assertIs(metric["physical_file_inode_object_receipts_attested"], False)
        self.assertEqual(metric["physical_projection_status"], "planned-conditional")
        self.assertIs(
            metric["physical_projection_requires_all_move_preconditions"], True
        )
        self.assertEqual(
            metric["symbol_capacity_relations"],
            [
                {
                    "left_symbol": "qIM",
                    "relation": "less-than-or-equal",
                    "right_symbol": "uIM",
                },
                {
                    "left_symbol": "uIM",
                    "relation": "equal-integer",
                    "right_integer": 350,
                },
                {
                    "left_symbol": "nIM",
                    "relation": "equal-integer",
                    "right_integer": 5,
                },
            ],
        )
        self.assertEqual(
            metric["w0_endpoint_chunk_sum_contract"]["component_count"],
            5,
        )

    def test_move_anchor_capacity_and_incidental_caps_close_without_ordinal_mapping(self):
        capacity = self.value["anchor_capacity_contract"]
        self.assertEqual(capacity["available_contributor_capacity_per_persona"], 105)
        self.assertEqual(
            capacity["contributor_capabilities_requiring_capacity_per_persona"],
            100,
        )
        self.assertEqual(capacity["unused_contributor_capacity_per_persona"], 5)
        self.assertEqual(
            capacity["unused_contributor_capacity_status"], "reserved-unused"
        )
        self.assertEqual(capacity["incidental_move_capabilities_unreserved_per_persona"], 5)
        self.assertEqual(capacity["mapping_status"], "unbound")
        self.assertIs(capacity["evaluation_ordinal_inference_allowed"], False)
        self.assertEqual(
            self.value["suite_summary"]["contract_contributor_capability_count"],
            2_000,
        )
        self.assertEqual(
            self.value["suite_summary"]["incidental_searchable_capability_count"],
            100,
        )
        rows = self.value["incidental_capacity_reservation"]
        self.assertEqual(
            [
                (
                    row["profile_key"],
                    row["incidental_current_upper"],
                    row["move_history_upper"],
                    row["combined_current_plus_move_history_upper"],
                    row["incidental_total_upper"],
                )
                for row in rows
            ],
            [
                ("pilot", 1_020, 350, 1_370, 2_040),
                ("full", 10_200, 350, 10_550, 20_400),
            ],
        )
        self.assertTrue(all(row["passes_total_upper"] is True for row in rows))

    def test_replacements_are_distinct_and_capacity_replaces_only(self):
        replacements = {
            row["replacement_contract_key"]: row
            for row in self.value["replacement_contracts"]
        }
        self.assertEqual(set(replacements), {"P-prime", "X-prime"})
        for row in replacements.values():
            self.assertEqual(row["allowed_relation_keys"], ["capacity-replaces"])
            self.assertIs(row["copying_replaced_content_satisfies"], False)
            self.assertEqual(row["variant_relation"], "must-match-replaced-source")
            self.assertEqual(
                row["origin_profile_relation"], "must-match-replaced-source"
            )
            self.assertEqual(
                row["replacement_pairing_rule"],
                "one-distinct-replacement-per-matched-logical-document",
            )
            self.assertEqual(
                row["transition_unit_relation"],
                "must-equal-replaced-selection",
            )
            self.assertEqual(row["source_instance_pairing_status"], "unbound")
            self.assertEqual(
                row["distinctness_contract"],
                {
                    "contract_chunk_set_relation": "must-be-distinct",
                    "logical_document_relation": "must-be-distinct",
                    "raw_payload_relation": "must-be-distinct",
                    "semantic_content_relation": "must-be-distinct",
                    "typed_fact_membership_relation": "must-be-distinct",
                },
            )

    def test_restore_is_export_reingest_and_paired_delete_with_net_zero(self):
        groups = {
            row["dependency_group_key"]: row
            for row in self.value["dependency_groups"]
        }
        restore = groups["w5-restore-x-net-zero"]
        self.assertEqual(
            restore["member_event_template_keys"],
            [
                "lifecycle-template-w5-export-deleted-x-v2",
                "lifecycle-template-w5-reingest-x-v2",
                "lifecycle-template-w5-delete-paired-x-prime-v2",
            ],
        )
        self.assertEqual(
            restore["ordered_dependencies"],
            [
                [
                    "lifecycle-template-w5-export-deleted-x-v2",
                    "lifecycle-template-w5-reingest-x-v2",
                ],
                [
                    "lifecycle-template-w5-reingest-x-v2",
                    "lifecycle-template-w5-delete-paired-x-prime-v2",
                ],
            ],
        )
        self.assertIs(restore["paired_x_prime_delete_required"], True)
        self.assertIs(restore["empty_selection_satisfies"], False)
        self.assertEqual(restore["shared_selection_symbol"], "qXR")
        self.assertEqual(
            restore["member_selection_relation"],
            "exact-same-matched-restored-subset",
        )
        self.assertEqual(
            restore["exported_payload_relation"],
            "byte-identical-to-matched-deleted-x",
        )
        self.assertEqual(
            restore["reingested_payload_relation"],
            "byte-identical-to-exported-payload",
        )
        self.assertEqual(
            restore["paired_replacement_selection_rule"],
            "delete-corresponding-x-prime-one-to-one",
        )
        self.assertEqual(restore["source_instance_matching_status"], "unbound")
        self.assertEqual(
            restore["symbolic_net_delta"],
            {
                "current_transition_units": {
                    "coefficient": 0,
                    "direction": "preserve",
                    "symbol": "zero",
                },
                "historical_transition_units": {
                    "coefficient": 0,
                    "direction": "preserve",
                    "symbol": "zero",
                },
            },
        )
        events = {
            row["event_template_key"]: row for row in self.value["event_templates"]
        }
        self.assertEqual(
            events["lifecycle-template-w5-reingest-x-v2"]["delta_rule"][
                "current_transition_units"
            ]["symbol"],
            "qXR",
        )
        self.assertEqual(
            events["lifecycle-template-w5-delete-paired-x-prime-v2"][
                "delta_rule"
            ]["historical_transition_units"]["symbol"],
            "qXR",
        )

    def test_lifecycle_states_are_pairwise_disjoint(self):
        contract = self.value["lifecycle_disjointness_contract"]
        self.assertIs(contract["pairwise_disjoint_required"], True)
        self.assertIs(contract["anonymous_capability_may_satisfy_multiple_states"], False)
        self.assertEqual(
            [(row["state"], row["required_count_per_persona"]) for row in contract["state_classes"]],
            [("final-deleted", 10), ("current-restored", 10), ("purged", 15)],
        )
        self.assertEqual(
            [row["transition_unit_symbol"] for row in contract["state_classes"]],
            ["qXD", "qXR", "qP"],
        )
        self.assertEqual(
            self.value["transition_algebra_model"]["symbolic_partition_rules"],
            [
                {
                    "part_symbols": ["qXD", "qXR"],
                    "relation": "exact-sum",
                    "whole_symbol": "qX",
                }
            ],
        )
        self.assertEqual(
            self.value["suite_summary"]["lifecycle_anchor_counts"],
            {"current-restored": 200, "final-deleted": 200, "purged": 300},
        )

    def test_persona_emphasis_witnesses_are_exact_five_and_structural_zero(self):
        rows = self.value["emphasis_witness_demands"]
        derive = [row for row in rows if row["witness_kind"] == "derive"]
        duplicate = [row for row in rows if row["witness_kind"] == "exact-duplicate"]
        self.assertEqual([row["persona_id"] for row in derive], ["p01", "p04", "p06", "p09"])
        self.assertEqual(
            [row["persona_id"] for row in duplicate],
            ["p04", "p05", "p08", "p10", "p14", "p19"],
        )
        for row in rows:
            self.assertEqual(row["required_witness_count"], 5)
            self.assertEqual(row["structural_transition_units"], 0)
            self.assertEqual(row["source_instance_matching_status"], "unbound")
        self.assertEqual(sum(row["required_witness_count"] for row in derive), 20)
        self.assertEqual(sum(row["required_witness_count"] for row in duplicate), 30)

    def test_later_layer_identifiers_queries_and_assigned_values_are_absent(self):
        raw = demand.canonical_json_bytes(self.value)
        for forbidden in (
            b'"absolute_path"',
            b'"chunk_id"',
            b'"final_materialization_id"',
            b'"final_source_id"',
            b'"materialization_id"',
            b'"oracle_key"',
            b'"planned_source_id"',
            b'"query_id"',
            b'"query_text"',
            b'"raw_id"',
            b'"scope_path"',
            b'"source_id"',
            b'"quota',
        ):
            self.assertNotIn(forbidden, raw)
        algebra = self.value["transition_algebra_model"]
        self.assertEqual(
            algebra["metric_identity_binding_status"],
            "ledger-identities-and-move-deltas-bound-to-authenticated-accounting-sidecar",
        )
        self.assertIs(algebra["all_event_metric_specific_delta_rules_present"], False)
        self.assertIs(algebra["cross_scope_move_metric_delta_rules_present"], True)
        self.assertEqual(
            algebra["contract_checkpoint_ledger_id"],
            "search-semantic-endpoint-v1",
        )
        self.assertEqual(algebra["contract_checkpoint_participation"], "contract")
        self.assertEqual(
            algebra["downstream_metric_candidates"],
            [
                "search-semantic-endpoint-v1",
                "persona-global-chunk-hash-v1",
                "history-path-binding-v1",
                "physical-storage-v1",
            ],
        )
        self.assertNotIn(
            "chunk-accounting-sidecar-not-bound",
            self.value["remaining_blockers"],
        )
        self.assertIn(
            "cross-scope-move-w0-observation-not-attested",
            self.value["remaining_blockers"],
        )

    def test_w3_and_w5_surface_edits_preserve_exact_fact_membership(self):
        events = {
            row["event_template_key"]: row for row in self.value["event_templates"]
        }
        for key in (
            "lifecycle-template-w3-edit-x-v2",
            "lifecycle-template-w3-edit-y-v2",
            "lifecycle-template-w3-edit-n-v2",
            "lifecycle-template-w5-correct-n-v2",
        ):
            self.assertIn(events[key]["operation_kind"], {"surface-edit", "surface-correction"})
            self.assertEqual(events[key]["fact_relation_rule"], "exact-fact-carry-forward")

    def test_dependency_and_wave_algebra_is_recomputed_from_event_rows(self):
        self.assertTrue(independent._assert_symbolic_algebra_recomputes(self.value) is None)

        changed = copy.deepcopy(self.value)
        events = {
            row["event_template_key"]: row for row in changed["event_templates"]
        }
        events["lifecycle-template-w5-reingest-x-v2"]["delta_rule"][
            "historical_transition_units"
        ] = {"coefficient": 0, "direction": "preserve", "symbol": "zero"}
        with self.assertRaises(
            independent.PersonaV2LifecycleDemandValidationError
        ):
            independent._assert_symbolic_algebra_recomputes(changed)

        changed = copy.deepcopy(self.value)
        changed["wave_delta_rules"][0]["historical_transition_unit_terms"].pop()
        with self.assertRaises(
            independent.PersonaV2LifecycleDemandValidationError
        ):
            independent._assert_symbolic_algebra_recomputes(changed)

    def test_validator_is_import_independent_and_builder_returns_detached_values(self):
        tree = ast.parse(inspect.getsource(independent))
        imported_modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported_modules.add(node.module or "")
        self.assertFalse(
            any(name.endswith("persona_v2_lifecycle_demand") for name in imported_modules)
        )
        changed = demand.build_lifecycle_demand()
        changed["persona_demands"][0]["origin_payload"]["anonymous_capabilities"].pop()
        fresh = demand.build_lifecycle_demand()
        self.assertEqual(
            len(fresh["persona_demands"][0]["origin_payload"]["anonymous_capabilities"]),
            105,
        )
        with self.assertRaises(demand.PersonaV2LifecycleDemandError):
            demand.validate_lifecycle_demand(changed)

    def test_rehashed_semantic_tampering_and_extra_keys_are_rejected(self):
        mutations = []

        changed = copy.deepcopy(self.value)
        changed["authority"]["authorizes_history_mutation"] = True
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["persona_demands"][0]["origin_payload"]["anonymous_capabilities"][0][
            "allocation_class"
        ] = "P"
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["replacement_contracts"][0]["allowed_relation_keys"].append("semantic-copy")
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["dependency_groups"][1]["member_event_template_keys"].pop()
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["emphasis_witness_demands"][0]["required_witness_count"] = 6
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["cross_scope_move_metric_contract"]["pre_solve_upper"] = 351
        mutations.append(changed)

        for field in (
            "raw_bytes_relation",
            "tool_profile_relation",
            "generation_profile_relation",
            "chunk_configuration_relation",
            "chunk_set_relation",
            "destination_endpoint_collision_precondition",
            "planned_destination_endpoint_precondition",
            "planned_destination_managed_location_precondition",
        ):
            changed = copy.deepcopy(self.value)
            changed["cross_scope_move_metric_contract"][field] = "weakened"
            mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["cross_scope_move_metric_contract"][
            "source_scope_live_binding_multiplicity_exact"
        ] = 2
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["cross_scope_move_metric_contract"]["accounting_operation_contract"][
            "delta_terms"
        ][3] = {
            "coefficient": 0,
            "direction": "preserve",
            "metric_id": "search-semantic-endpoint-v1",
            "projection": "incidental-history-only",
            "symbol": "zero",
        }
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["cross_scope_move_metric_contract"][
            "ledger_dimension_schema_crosswalk"
        ][2]["projection_mappings"][0]["accounting_projection"] = "weakened"
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["cross_scope_move_metric_contract"]["symbol_capacity_relations"][1][
            "right_integer"
        ] = 351
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["cross_scope_move_metric_contract"][
            "physical_file_inode_object_receipts_required"
        ] = False
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["input_bindings"][0]["sha256"] = "0" * 64
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["anchor_capacity_contract"][
            "evaluation_ordinal_inference_allowed"
        ] = True
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["incidental_capacity_reservation"][0][
            "combined_current_plus_move_history_upper"
        ] = 2_041
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["query_text"] = "forbidden"
        mutations.append(changed)

        for changed in mutations:
            self._assert_independent_rejects_rehashed(changed)

        changed_accounting = copy.deepcopy(self.accounting_value)
        move = next(
            row
            for row in changed_accounting["operation_delta_contracts"]
            if row["operation_id"] == "cross-scope-move-incidental"
        )
        move["delta_terms"][3]["coefficient"] = 0
        accounting_raw = chunk_accounting.canonical_json_bytes(changed_accounting)
        with (
            mock.patch.object(
                chunk_accounting_validator,
                "EXPECTED_ACCOUNTING_CANONICAL_BYTES",
                len(accounting_raw),
            ),
            mock.patch.object(
                chunk_accounting_validator,
                "EXPECTED_ACCOUNTING_SHA256",
                hashlib.sha256(accounting_raw).hexdigest(),
            ),
            mock.patch.object(
                independent,
                "EXPECTED_CHUNK_ACCOUNTING_CANONICAL_BYTES",
                len(accounting_raw),
            ),
            mock.patch.object(
                independent,
                "EXPECTED_CHUNK_ACCOUNTING_SHA256",
                hashlib.sha256(accounting_raw).hexdigest(),
            ),
            self.assertRaises(
                independent.PersonaV2LifecycleDemandValidationError
            ),
        ):
            self._validate_independent(
                self.value,
                accounting_value=changed_accounting,
            )

    def test_null_float_negative_and_hostile_repr_are_rejected(self):
        for replacement in (None, 1.0, -1):
            changed = copy.deepcopy(self.value)
            changed["suite_summary"]["persona_count"] = replacement
            with self.assertRaises(demand.PersonaV2LifecycleDemandError):
                demand.validate_lifecycle_demand(changed)

        class Hostile:
            def __repr__(self):
                raise AssertionError("repr must not be called")

        changed = copy.deepcopy(self.value)
        changed["suite_summary"]["persona_count"] = Hostile()
        with self.assertRaises(demand.PersonaV2LifecycleDemandError):
            demand.validate_lifecycle_demand(changed)

    def test_rehashed_bool_integer_aliases_are_rejected_everywhere(self):
        mutations = []

        changed = copy.deepcopy(self.value)
        changed["completion_claims"]["anonymous_capability_demand_complete"] = 1
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["boundary_assertions"]["source_instance_matching_complete"] = 0
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["lifecycle_disjointness_contract"]["pairwise_disjoint_required"] = 1
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["replacement_contracts"][0]["copying_replaced_content_satisfies"] = 0
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["emphasis_witness_demands"][0]["structural_transition_units"] = False
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["dependency_groups"][1]["paired_x_prime_delete_required"] = 1
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["suite_summary"]["allocation_class_capability_counts"]["N"] = False
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["cross_scope_move_metric_contract"]["pre_solve_upper"] = False
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["incidental_capacity_reservation"][0]["passes_total_upper"] = 1
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["cross_scope_move_metric_contract"][
            "accounting_operation_match_required"
        ] = 1
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["cross_scope_move_metric_contract"][
            "physical_file_inode_object_receipts_required"
        ] = 1
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["cross_scope_move_metric_contract"][
            "w0_endpoint_chunk_sum_contract"
        ]["component_count"] = False
        mutations.append(changed)

        changed = copy.deepcopy(self.value)
        changed["input_bindings"][0]["canonical_bytes"] = False
        mutations.append(changed)

        for changed in mutations:
            self._assert_independent_rejects_rehashed(changed)

    def test_snapshot_and_closing_reauthentication_detect_mutation(self):
        value = demand.build_lifecycle_demand()
        accounting_value = chunk_accounting.build_chunk_accounting_contract()
        original = independent._validate_lifecycle_demand_snapshot

        def mutate_after_snapshot(*snapshots):
            result = original(*snapshots)
            value["completion_claims"]["source_instance_matching_complete"] = True
            return result

        with (
            mock.patch.object(
                independent,
                "_validate_lifecycle_demand_snapshot",
                side_effect=mutate_after_snapshot,
            ),
            self.assertRaises(
                independent.PersonaV2LifecycleDemandValidationError
            ),
        ):
            self._validate_independent(
                value,
                accounting_value=accounting_value,
            )

        value = demand.build_lifecycle_demand()
        accounting_value = chunk_accounting.build_chunk_accounting_contract()

        def mutate_accounting_after_snapshot(*snapshots):
            result = original(*snapshots)
            accounting_value["completion_claims"]["actual_accounting_attested"] = True
            return result

        with (
            mock.patch.object(
                independent,
                "_validate_lifecycle_demand_snapshot",
                side_effect=mutate_accounting_after_snapshot,
            ),
            self.assertRaises(
                independent.PersonaV2LifecycleDemandValidationError
            ),
        ):
            self._validate_independent(
                value,
                accounting_value=accounting_value,
            )

    def test_compiled_plan_escalation_is_explicitly_unavailable(self):
        with self.assertRaises(demand.PersonaV2LifecycleDemandError):
            demand.require_compiled_history_plan()


if __name__ == "__main__":
    unittest.main()
