import copy
import os
import subprocess
import sys
import unittest

from eval import persona_v2_contract as envelope
from eval import persona_v2_overlay_contract as overlay
from eval import persona_v2_realism_profile as realism


EXPECTED_CANONICAL_BYTES = 69_114
EXPECTED_SHA256 = "e79d90e38cdfe62c4ed842a6cb20e4bd674d7fee7821e22fde701563415a7678"
EXPECTED_INPUT_BINDINGS = [
    (
        "envelope",
        "core",
        71_979,
        "1d49e79049b409ee5bd82d0b307db5055c2a58544df81858b77552ea82bff370",
    ),
    (
        "topology",
        "topology",
        134_195,
        "204c9a136438c0dfff3718549c2fcb6009e6ccbe9debdd0cfe54bfaa4290b68f",
    ),
    (
        "joint-problem",
        "joint",
        744_137,
        "8551472e4993f21ff71f886b3f80b9b02410c409476d0be91d773db335907074",
    ),
    (
        "joint-solver-policy",
        "solver",
        83_004,
        "2a6c169a5cd02b01e330abf0f3a828d0d947a2f66b18f19e97a682d2edd50857",
    ),
    (
        "realism-profile",
        "realism",
        36_811,
        "a32bbb0fd7c88c57205454d8555163ad97b2b1a3024e5a5d7f7234bf56766f05",
    ),
    (
        "variant-catalog",
        "variant",
        211_733,
        "abbe522ff37a9a091f28b7a230928fd598054498eb80cab99f08d21889f26cec",
    ),
]


class PersonaV2OverlayContractTests(unittest.TestCase):
    def test_identity_bindings_completion_scope_and_negative_authority_are_exact(self):
        value = overlay.build_overlay_contract()
        self.assertEqual(value["artifact_schema"], overlay.ARTIFACT_SCHEMA)
        self.assertEqual(value["artifact_kind"], overlay.ARTIFACT_KIND)
        self.assertEqual(value["artifact_schema_version"], 2)
        self.assertEqual(value["fixture_id"], envelope.FIXTURE_ID)
        self.assertEqual(value["fixture_schema_version"], 2)
        self.assertIs(value["g0_contract_frozen"], False)
        for key, flag in value["authority"].items():
            self.assertIs(type(flag), bool, key)
            self.assertIs(flag, False, key)

        claims = value["completion_claims"]
        for key in (
            "attachment_semantics_complete",
            "content_relation_semantics_complete",
            "logical_document_scoring_semantics_complete",
            "membership_shard_schema_complete",
            "overlay_integer_target_marginals_complete",
            "placement_demand_marginals_complete",
            "search_participation_semantics_complete",
        ):
            self.assertIs(claims[key], True, key)
        for key in (
            "eight_axis_ledger_schema_complete",
            "logical_document_instance_assignment_complete",
            "observed_eight_axis_ledger_instances_present",
            "overlay_membership_instances_present",
            "placement_scope_assignment_complete",
            "planned_eight_axis_ledger_instances_present",
            "source_format_feasibility_complete",
        ):
            self.assertIs(claims[key], False, key)

        bindings = value["input_bindings"]
        self.assertEqual(
            [
                (
                    row["name"],
                    row["dependency_role"],
                    row["canonical_bytes"],
                    row["sha256"],
                )
                for row in bindings
            ],
            EXPECTED_INPUT_BINDINGS,
        )
        for row in bindings:
            self.assertRegex(row["sha256"], r"^[0-9a-f]{64}$")
            self.assertGreater(row["canonical_bytes"], 0)

        raw = overlay.canonical_json_bytes(value)
        self.assertEqual(len(raw), EXPECTED_CANONICAL_BYTES)
        self.assertEqual(overlay.overlay_contract_sha256(value), EXPECTED_SHA256)
        self.assertLess(len(raw), overlay.MAX_OVERLAY_CONTRACT_BYTES)
        self.assertRegex(overlay.overlay_contract_sha256(value), r"^[0-9a-f]{64}$")
        self.assertTrue(overlay.validate_overlay_contract(value))

    def test_suite_relation_membership_and_placement_marginals_are_exact(self):
        targets = overlay.build_overlay_contract()["suite_target_marginals"]
        self.assertEqual(
            targets,
            {
                "pilot": {
                    "attachment_exact_duplicate_overlap_count": 139,
                    "attachment_membership_count": 569,
                    "conflict_copy_cluster_count": 156,
                    "content_relation_cluster_count": 1_987,
                    "content_relation_endpoint_reference_count": 3_974,
                    "exact_duplicate_cluster_count": 508,
                    "membership_row_count": 2_556,
                    "near_revision_cluster_count": 1_323,
                    "placement_demand_by_scope_class": {
                        "primary-to-primary": 868,
                        "primary-to-secondary": 628,
                        "secondary-to-primary": 309,
                        "secondary-to-secondary": 182,
                    },
                },
                "full-minus-pilot": {
                    "attachment_exact_duplicate_overlap_count": 1_251,
                    "attachment_membership_count": 5_121,
                    "conflict_copy_cluster_count": 1_404,
                    "content_relation_cluster_count": 17_883,
                    "content_relation_endpoint_reference_count": 35_766,
                    "exact_duplicate_cluster_count": 4_572,
                    "membership_row_count": 23_004,
                    "near_revision_cluster_count": 11_907,
                    "placement_demand_by_scope_class": {
                        "primary-to-primary": 7_800,
                        "primary-to-secondary": 5_660,
                        "secondary-to-primary": 2_786,
                        "secondary-to-secondary": 1_637,
                    },
                },
                "full": {
                    "attachment_exact_duplicate_overlap_count": 1_390,
                    "attachment_membership_count": 5_690,
                    "conflict_copy_cluster_count": 1_560,
                    "content_relation_cluster_count": 19_870,
                    "content_relation_endpoint_reference_count": 39_740,
                    "exact_duplicate_cluster_count": 5_080,
                    "membership_row_count": 25_560,
                    "near_revision_cluster_count": 13_230,
                    "placement_demand_by_scope_class": {
                        "primary-to-primary": 8_668,
                        "primary-to-secondary": 6_288,
                        "secondary-to-primary": 3_095,
                        "secondary-to-secondary": 1_819,
                    },
                },
            },
        )
        for section in (
            tuple(
                key
                for key in targets["full"]
                if key != "placement_demand_by_scope_class"
            ),
            tuple(overlay.PLACEMENT_CLASS_ORDER),
        ):
            full = (
                targets["full"]["placement_demand_by_scope_class"]
                if section == tuple(overlay.PLACEMENT_CLASS_ORDER)
                else targets["full"]
            )
            pilot = (
                targets["pilot"]["placement_demand_by_scope_class"]
                if section == tuple(overlay.PLACEMENT_CLASS_ORDER)
                else targets["pilot"]
            )
            residual = (
                targets["full-minus-pilot"]["placement_demand_by_scope_class"]
                if section == tuple(overlay.PLACEMENT_CLASS_ORDER)
                else targets["full-minus-pilot"]
            )
            for key in section:
                self.assertEqual(residual[key], full[key] - pilot[key])

    def test_persona_targets_rederive_from_realism_without_membership(self):
        value = overlay.build_overlay_contract()
        profile = realism.build_realism_profile()
        by_persona = {
            row["persona_id"]: row for row in value["persona_target_marginals"]
        }
        realism_by_persona = {row["persona_id"]: row for row in profile["personas"]}
        weights = {
            row["placement_profile_id"]: row["weights_bp"]
            for row in profile["catalogs"]["placement_profiles"]
        }
        self.assertEqual(list(by_persona), list(envelope.PERSONA_IDS))
        for persona_id in envelope.PERSONA_IDS:
            actual = by_persona[persona_id]
            source = realism_by_persona[persona_id]
            self.assertEqual(
                actual["placement_profile_id"], source["placement_profile_id"]
            )
            for profile_id in ("pilot", "full"):
                target = actual["targets"][profile_id]
                source_counts = source["overlay_targets"][profile_id]
                self.assertEqual(
                    target["exact_duplicate_cluster_count"],
                    source_counts["exact_duplicate"],
                )
                self.assertEqual(
                    target["near_revision_cluster_count"],
                    source_counts["near_revision"],
                )
                self.assertEqual(
                    target["conflict_copy_cluster_count"],
                    source_counts["conflict_copy"],
                )
                self.assertEqual(
                    target["attachment_membership_count"],
                    source_counts["standalone_attachment"],
                )
                # Independently repeat the fixed Hamilton rule.
                count = source_counts["relation_cluster_count"]
                profile_weights = weights[source["placement_profile_id"]]
                floors = [count * weight // 10_000 for weight in profile_weights]
                remaining = count - sum(floors)
                order = sorted(
                    range(4),
                    key=lambda index: (
                        -(count * profile_weights[index] % 10_000),
                        index,
                    ),
                )
                for index in order[:remaining]:
                    floors[index] += 1
                self.assertEqual(
                    target["placement_demand_by_scope_class"],
                    dict(zip(overlay.PLACEMENT_CLASS_ORDER, floors)),
                )
            for key, full_value in actual["targets"]["full"].items():
                if key == "placement_demand_by_scope_class":
                    for placement_class, count in full_value.items():
                        self.assertEqual(
                            actual["targets"]["full-minus-pilot"][key][
                                placement_class
                            ],
                            count
                            - actual["targets"]["pilot"][key][placement_class],
                        )
                else:
                    self.assertEqual(
                        full_value,
                        10 * actual["targets"]["pilot"][key],
                    )
                    self.assertEqual(
                        actual["targets"]["full-minus-pilot"][key],
                        full_value - actual["targets"]["pilot"][key],
                    )

    def test_relation_attachment_search_and_origin_semantics_are_frozen(self):
        value = overlay.build_overlay_contract()
        relations = {
            row["relation_kind"]: row
            for row in value["content_relation_semantics"]
        }
        self.assertEqual(list(relations), list(overlay.CONTENT_RELATION_ORDER))
        exact = relations["exact-duplicate"]
        self.assertEqual(exact["raw_identity_relation"], "same-raw-sha256")
        self.assertEqual(exact["document_revision_relation"], "same-logical-revision")
        self.assertEqual(exact["derivative_role"], "exact-copy-role")
        near = relations["near-revision"]
        self.assertEqual(near["raw_identity_relation"], "different-raw-sha256")
        self.assertEqual(
            near["document_revision_relation"],
            "distinct-strictly-ordered-revisions",
        )
        self.assertEqual(near["anchor_role"], "earlier-logical-revision")
        conflict = relations["conflict-copy"]
        self.assertEqual(conflict["branch_relation"], "distinct-unordered-branches")
        self.assertEqual(conflict["derivative_role"], "conflicting-branch-copy")
        self.assertIn("conflicting-typed-fact", conflict["decoded_payload_relation"])
        for row in relations.values():
            self.assertEqual(row["logical_document_relation"], "same-logical-document")
            self.assertIn("W0", row["checkpoint_history_relation"])
        global_relation = value["content_relation_global_contract"]
        self.assertEqual(
            global_relation["cluster_cardinality_physical_materializations"], 2
        )
        self.assertIs(global_relation["clusters_are_physical-member-disjoint"], True)
        self.assertIs(
            global_relation["exact_near_conflict_membership_is_mutually_exclusive"],
            True,
        )
        self.assertIs(
            global_relation["overlay_may_change_physical_file_marginals"], False
        )
        self.assertIs(
            global_relation["overlay_may_change_contract_chunk_target"], False
        )

        attachment = value["attachment_contract"]
        self.assertEqual(attachment["allowed_host_variant_ids"], ["eml"])
        self.assertEqual(attachment["inclusive_members_per_host_minimum"], 1)
        self.assertEqual(attachment["inclusive_members_per_host_maximum"], 5)
        self.assertIs(attachment["nested_attachment_member_allowed"], False)
        self.assertIs(
            attachment["embedded_member_adds_physical_file_or_contract_chunk"],
            False,
        )
        self.assertEqual(
            attachment["attachment_membership_count_unit"],
            "one-row-equals-one-unique-standalone-member-intent",
        )
        self.assertIs(
            attachment["standalone_member_intent_may_appear_in_multiple_attachment_rows"],
            False,
        )
        self.assertIs(
            attachment["overlap_exact_cluster_may_contain_both_attachment_members"],
            False,
        )
        self.assertIs(
            attachment["embedded_only_evidence_may_satisfy_member_logical_document_target"],
            False,
        )
        self.assertEqual(
            attachment["host_source_result_projects_to"],
            "host-logical-document-revision",
        )
        self.assertIs(
            attachment["exact_duplicate_overlap_is_the_only_content_relation_overlap"],
            True,
        )

        search = value["search_and_scoring_contract"]
        self.assertEqual(
            search["default_recall_denominator_identity"],
            "distinct-logical-document-key",
        )
        self.assertIs(search["content_relation_raw_only_endpoint_allowed"], False)
        self.assertIs(
            search["attachment_embedded_only_evidence_target_eligible"], False
        )
        self.assertEqual(
            search["attachment_standalone_result_projection"],
            "member-logical-document-revision",
        )
        self.assertIs(
            search["duplicate_or_revision_paths_may_increase_recall_denominator"],
            False,
        )
        origins = value["origin_and_profile_contract"]
        self.assertEqual(origins["origin_values"], ["pilot", "full-residual"])
        self.assertIs(origins["residual_membership_may_reference_pilot_intent"], False)
        self.assertIs(
            origins["pilot_membership_bytes_and_sha256_reused_unchanged_in_full"],
            True,
        )

    def test_membership_and_eight_axis_schemas_have_no_instances_or_final_ids(self):
        value = overlay.build_overlay_contract()
        membership = value["membership_shard_schema"]
        self.assertEqual(
            membership["artifact_schema"],
            "kcs.persona.pc-overlay-membership-shard/v2",
        )
        self.assertEqual(membership["max_rows_per_shard"], 4_096)
        self.assertEqual(membership["max_shard_body_bytes"], 4 * 2**20)
        self.assertEqual(membership["max_canonical_jsonl_row_bytes_including_lf"], 768)
        self.assertIs(membership["persona_local_only"], True)
        self.assertEqual(
            membership["hash_dag_order"],
            [
                "source-profile-catalog",
                "source-intent-shards",
                "intent-only-manifest",
                "overlay-membership-shards",
                "overlay-manifest",
            ],
        )
        self.assertIs(
            membership["source_intent_manifest_back_reference_to_overlay_allowed"],
            False,
        )
        self.assertIs(
            membership["body_encoding"]["each_row_terminated_by_single_lf"], True
        )
        self.assertIs(
            membership["deterministic_row_sort"]["hash-ordering-allowed"], False
        )
        self.assertEqual(
            membership["deterministic_row_sort"]["attachment_membership_key"],
            [
                "row-kind-ordinal-1",
                "relation-kind-sentinel-ordinal-0",
                "attachment-key-ascending-ASCII-bytes",
            ],
        )
        self.assertEqual(
            membership["membership_key_syntax"],
            [
                {
                    "field_name": "attachment_key",
                    "syntax": "lowercase-ASCII-regex-^[a-z][a-z0-9-]{0,119}$",
                },
                {
                    "field_name": "cluster_key",
                    "syntax": "lowercase-ASCII-regex-^[a-z][a-z0-9-]{0,119}$",
                },
            ],
        )
        self.assertIn("greedily-append-consecutive-rows", membership["shard_partition_rule"])
        self.assertEqual(
            set(membership["origin_manifest_schema"]["origin_to_target_profile"]),
            {"pilot", "full-residual"},
        )
        self.assertEqual(
            [row["profile_id"] for row in membership["search_participation_profiles"]],
            ["content-relation-v2", "attachment-structural-v2"],
        )
        required_cross_row = {
            "attachment-standalone-member-intent-used-by-exactly-one-attachment-row",
            "attachment-exact-overlap-is-one-standalone-intent-to-one-exact-cluster",
            "attachment-exact-overlap-cluster-has-exactly-one-attachment-endpoint",
            "content-relation-endpoint-intent-used-by-exactly-one-content-cluster",
            "placement-class-counts-equal-bound-persona-origin-targets",
        }
        self.assertTrue(required_cross_row.issubset(membership["cross_row_constraints"]))
        self.assertEqual(
            value["target_count_unit_contract"]["attachment_membership_count"],
            "attachment-rows-equals-unique-standalone-member-intents",
        )
        self.assertIs(
            membership["source_or_materialization_or_final_ids_allowed"], False
        )
        self.assertEqual(
            [row["row_kind"] for row in membership["row_schemas"]],
            ["content-relation", "attachment-membership"],
        )

        ledger = value["eight_axis_ledger_schema"]
        self.assertEqual(ledger["axis_order"], list(overlay.LEDGER_AXIS_ORDER))
        self.assertEqual(
            [row["axis_id"] for row in ledger["axes"]],
            list(overlay.LEDGER_AXIS_ORDER),
        )
        self.assertEqual(len(ledger["axes"]), 8)
        self.assertIs(ledger["planned_and_observed_rows_are_distinct"], True)
        self.assertIs(ledger["observed_evidence_required"], True)
        self.assertIn("different-artifact-schemas", ledger["phase_separation"])
        self.assertIn("axis-order-ordinal", ledger["canonical_row_order"])
        self.assertEqual(ledger["max_canonical_jsonl_row_bytes_including_lf"], 2_048)
        self.assertEqual(
            set(ledger["instance_artifact_schemas"]), {"planned", "observed"}
        )
        marginals = ledger["profile_marginal_contract"]
        self.assertEqual(
            marginals["checkpoint_order"],
            list(envelope.HISTORY_CHECKPOINTS["pilot"]),
        )
        self.assertEqual(
            marginals["full_minus_pilot_rule"],
            "coordinatewise-full-minus-pilot",
        )
        residual_checkpoints = {
            row["checkpoint"]: (
                row["current_contract_chunks_per_persona"],
                row["history_only_contract_chunks_per_persona"],
            )
            for row in marginals["checkpoint_chunk_marginals"][
                "full-minus-pilot"
            ]
        }
        self.assertEqual(residual_checkpoints["W0"], (108_000, 0))
        self.assertEqual(residual_checkpoints["W4"], (108_000, 54_000))
        self.assertEqual(
            residual_checkpoints["W5-pre-purge"], (112_320, 58_320)
        )
        self.assertEqual(
            residual_checkpoints["W5-final"], (108_000, 54_000)
        )
        file_rows = marginals["w0_physical_file_marginals_by_persona"]
        self.assertEqual(
            [row["persona_id"] for row in file_rows],
            list(envelope.PERSONA_IDS),
        )
        self.assertEqual(sum(row["pilot"] for row in file_rows), 20_300)
        self.assertEqual(
            sum(row["full-minus-pilot"] for row in file_rows), 182_700
        )
        self.assertEqual(sum(row["full"] for row in file_rows), 203_000)
        for row in file_rows:
            self.assertEqual(
                row["full-minus-pilot"], row["full"] - row["pilot"]
            )
        self.assertEqual(
            ledger["hash_dag_order"],
            [
                "source-intent-origin-manifests",
                "history-intent-manifest",
                "overlay-membership-manifest",
                "canonical-allocation-solution",
                "final-source-plan",
                "planned-eight-axis-ledger",
                "filesystem-and-KCS-history-execution",
                "root-attestation-and-history-execution-receipt",
                "observed-eight-axis-ledger",
            ],
        )
        self.assertIn(
            "overlay-membership-origin-manifests-bind-source-intent-origin-manifest-sha256",
            ledger["hash_dag_required_edges"],
        )
        self.assertNotIn(
            "overlay-membership-manifest-binds-input-closure-and-history-intent-manifest-sha256s",
            ledger["hash_dag_required_edges"],
        )
        self.assertIn(
            "planned-eight-axis-ledger-must-not-bind-observed-eight-axis-ledger-sha256",
            ledger["hash_back_reference_rules"],
        )
        self.assertIn(
            "observed-eight-axis-ledger-is-terminal-and-no-earlier-node-may-bind-its-sha256",
            ledger["hash_back_reference_rules"],
        )
        self.assertIn(
            "canonical_allocation_solution_sha256",
            ledger["manifest_schemas"]["planned"]["exact_fields"],
        )
        self.assertIn(
            "W0-physical-materialization-count-reconciles-to-exact-target-profile-W0-file-marginals",
            ledger["cross_axis_reconciliation_rules"],
        )
        self.assertIn(
            "contract-contributor-observed-chunks-reconcile-to-exact-target-profile-checkpoint-chunk-marginals",
            ledger["cross_axis_reconciliation_rules"],
        )
        field_types = ledger["field_type_contract"]
        self.assertEqual(
            set(field_types["catalog_bound_enum_fields"]),
            set(field_types["enum_field_domain_ids"]),
        )
        enum_domains = {
            row["domain_id"]: row for row in field_types["enum_domains"]
        }
        self.assertEqual(len(enum_domains), len(field_types["enum_domains"]))
        for field_name, domain_id in field_types["enum_field_domain_ids"].items():
            with self.subTest(enum_field=field_name):
                self.assertIn(domain_id, enum_domains)
                self.assertTrue(enum_domains[domain_id]["values"])
                self.assertEqual(
                    len(enum_domains[domain_id]["values"]),
                    len(set(enum_domains[domain_id]["values"])),
                )
        self.assertEqual(
            enum_domains["checkpoint-v2"]["values"],
            ["W0", "W1", "W2", "W3", "W4", "W5-pre-purge", "W5-final"],
        )
        self.assertEqual(
            enum_domains["logical-visibility-v2"]["values"],
            ["absent", "current", "history-only", "purged"],
        )
        self.assertEqual(
            enum_domains["gate-role-v2"]["values"],
            ["contract_contributor", "incidental_searchable", "raw_only"],
        )
        self.assertEqual(
            field_types["enum_field_domain_ids"]["observed_path_case_state"],
            "path-case-state-v2",
        )
        dynamic_axes = {
            "physical-materialization",
            "logical-document",
            "gate-search-role-and-chunks",
            "current-and-history-version",
            "allocated-bytes",
            "host-metadata-and-exclusion",
        }
        static_axes = {
            "container-member-and-attachment",
            "content-relation-cluster",
        }
        for row in ledger["axes"]:
            if row["axis_id"] in dynamic_axes:
                self.assertEqual(
                    row["checkpoint_domain"],
                    "all-envelope-checkpoints-for-bound-profile",
                )
                self.assertIn("checkpoint", row["identity_fields"])
            else:
                self.assertIn(row["axis_id"], static_axes)
                self.assertEqual(row["checkpoint_domain"], "W0-overlay-static-only")
                self.assertNotIn("checkpoint", row["identity_fields"])
        history_axis = next(
            row
            for row in ledger["axes"]
            if row["axis_id"] == "current-and-history-version"
        )
        self.assertIn("origin", history_axis["identity_fields"])
        self.assertIn("branch_key", history_axis["identity_fields"])
        for row in ledger["axes"]:
            self.assertEqual(
                row["planned_exact_fields"],
                ["axis_id", *row["identity_fields"], *row["planned_fields"]],
            )
            self.assertEqual(
                row["observed_exact_fields"],
                [
                    "axis_id",
                    *row["identity_fields"],
                    *row["observed_fields"],
                    "attestation_evidence_sha256",
                ],
            )

        # Only schemas and aggregate targets are present.  No concrete row key or
        # scope/logical/source/materialization/final identity is instantiated.
        self.assertNotIn("membership_rows", value)
        self.assertNotIn("scope_assignments", value)
        self.assertNotIn("logical_document_instances", value)
        self.assertNotIn("planned_ledgers", value)
        self.assertNotIn("observed_ledgers", value)
        forbidden_instance_keys = {
            "attachment_key",
            "cluster_key",
            "final_source_id",
            "intent_key",
            "logical_document_key",
            "materialization_id",
            "payload_equivalence_key",
            "solved_scope_key",
            "source_id",
        }

        def visit(node):
            if type(node) is dict:
                self.assertTrue(forbidden_instance_keys.isdisjoint(node))
                for child in node.values():
                    visit(child)
            elif type(node) is list:
                for child in node:
                    visit(child)

        visit(value)
        self.assertIn(
            "renderer-and-standalone-validator-feasibility-not-proved",
            value["remaining_blockers"],
        )
        self.assertFalse(
            value["completion_claims"]["conflict_fact_realizability_proved"]
        )
        self.assertIn(
            "current-fact-graph-has-no-w0-current-unordered-conflict-pairs",
            value["remaining_blockers"],
        )
        with self.assertRaises(overlay.PersonaV2OverlayContractError):
            overlay.require_overlay_membership_and_ledgers()

    def test_tamper_strict_types_and_detachment_fail_closed(self):
        first = overlay.build_overlay_contract()
        tampered = copy.deepcopy(first)
        tampered["suite_target_marginals"]["pilot"][
            "exact_duplicate_cluster_count"
        ] -= 1
        with self.assertRaises(overlay.PersonaV2OverlayContractError):
            overlay.validate_overlay_contract(tampered)

        tampered = copy.deepcopy(first)
        tampered["membership_shard_schema"]["cross_row_constraints"].remove(
            "attachment-exact-overlap-is-one-standalone-intent-to-one-exact-cluster"
        )
        with self.assertRaises(overlay.PersonaV2OverlayContractError):
            overlay.validate_overlay_contract(tampered)

        for replacement in (True, 1.0, None, "e\u0301", "\ud800"):
            with self.subTest(replacement=repr(replacement)):
                tampered = overlay.build_overlay_contract()
                tampered["persona_target_marginals"][0]["targets"]["pilot"][
                    "membership_row_count"
                ] = replacement
                with self.assertRaises(overlay.PersonaV2OverlayContractError):
                    overlay.validate_overlay_contract(tampered)

        first["persona_target_marginals"][0]["persona_id"] = "poisoned"
        self.assertEqual(
            overlay.build_overlay_contract()["persona_target_marginals"][0][
                "persona_id"
            ],
            "p01",
        )

    def test_hash_is_independent_of_hashseed_timezone_under_c_locale(self):
        script = (
            "from eval import persona_v2_overlay_contract as o; "
            "v=o.build_overlay_contract(); "
            "print(o.overlay_contract_sha256(v),len(o.canonical_json_bytes(v)))"
        )
        expected = None
        for seed, timezone in (("0", "UTC"), ("1", "Asia/Tokyo"), ("42", "UTC")):
            environment = os.environ.copy()
            environment.update(
                {"PYTHONHASHSEED": seed, "TZ": timezone, "LC_ALL": "C"}
            )
            output = subprocess.check_output(
                [sys.executable, "-c", script],
                cwd=os.getcwd(),
                env=environment,
                text=True,
            ).strip()
            if expected is None:
                expected = output
            self.assertEqual(output, expected)
        self.assertEqual(expected, f"{EXPECTED_SHA256} {EXPECTED_CANONICAL_BYTES}")


if __name__ == "__main__":
    unittest.main()
