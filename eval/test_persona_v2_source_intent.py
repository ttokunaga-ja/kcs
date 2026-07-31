import copy
import hashlib
import inspect
import json
import unittest

from eval import persona_v2_artifact_common as artifact_common
from eval import persona_v2_contract as envelope
from eval import persona_v2_fact_graph as fact_graph
from eval import persona_v2_realism_profile as realism
from eval import persona_v2_route_affinity as route_affinity
from eval import persona_v2_source_intent as source_intent
from eval import persona_v2_source_profile_catalog as source_profiles
from eval import persona_v2_topology as topology
from eval import persona_v2_variant_catalog as variants


# Filled from canonical regeneration.  These pins make a change to any
# representative intent, normalized catalog, or corpus-semantic dependency an
# explicit review event.
EXPECTED_PERSONA_BINDINGS = (
    ("p01", 9_886, "0404e234e447d8bf7af2822eb2fabefd59235d356d8ea3237811883f8b3ffd97", 436, "md"),
    ("p02", 9_878, "5ed7115a064043acf8bc1c1e88fb37505639c0b0825fafa405933624851771d0", 436, "md"),
    ("p03", 9_915, "921a1ca0d2340725b1546acb96f4597cc349d9051b46e9db35e08e45b190e327", 446, "pdf-text"),
    ("p04", 9_918, "9ae123b466eaee2034336992df91b2b6a86a9180198ec5415f6ab5033fcc6dea", 436, "py"),
    ("p05", 9_892, "664a0a3f0de6ccbfe8170d117b0e0dacf8e368f4747a674140bdfe33e33bc5eb", 436, "md"),
    ("p06", 9_926, "f4a47d3a44ad3c9a4571b6e0aebd2a15f8bff777de235c4df472c597874e3de2", 446, "pdf-text"),
    ("p07", 9_956, "7815b04f937e87bcf269243a02c2f9c1c62431dc30f0339e92e02e87d5c8e4f8", 446, "pdf-text"),
    ("p08", 9_932, "b65b1b4be3086ac64ed1b8bccbc820578bed2ed48021190b9dfcaa655f5bd781", 446, "pdf-text"),
    ("p09", 9_898, "b18db22f8895ca93f3cf34284d5e16d604f48c968f710107ba3da6131d85f608", 437, "txt"),
    ("p10", 9_930, "51c89363b262322ffad96ddc0a08acc20a0055eaeb6b5729cd2b91b623f0f61c", 446, "pdf-text"),
    ("p11", 9_934, "ec781d968e47368da2af98919b3803ea62d18a4566fc8612ac5982d7f6096204", 446, "pdf-text"),
    ("p12", 9_903, "ad4e1606f14adeb13c4b65e2af967fdcb9cd01aa1f5b6ab5676a1261c61dd7d2", 436, "md"),
    ("p13", 9_922, "4292555cc17ac00fb1961e5b1dfe00af2b5e2e419bc95f6d5221e42d591d9c02", 446, "pdf-text"),
    ("p14", 9_917, "939777f064bc1c6aa5102c92884d48e7118ae440440f047cf8678fd8bc88071f", 446, "pdf-text"),
    ("p15", 9_933, "ef69c2ea69ce8c095c01e0d963952450e71ccf13c2ddc138a8b563286f121589", 446, "pdf-text"),
    ("p16", 9_953, "76176dfd4ce315057257a3b11e885bfef5b664e77fe4b56c726d03503295cf9d", 446, "pdf-text"),
    ("p17", 9_931, "b05d80a22697c76c9c29289ff55fbe40d4a46beb7cc74b70652ab9c630a25dca", 446, "pdf-text"),
    ("p18", 9_918, "8e637a6551c0f17fa1b72eeae7819ba3ceca76312127fec66c9f1afba3693354", 446, "pdf-text"),
    ("p19", 9_911, "9871e9a48e07a20b4a5519dcbb97479bbae5031ebc8fec393318f635cae6f8e0", 446, "pdf-text"),
    ("p20", 9_934, "162a25615b1aeadb22a2cae298bd5cc1d7aaee604be826b66d4bc326df5facea", 446, "pdf-text"),
)


def _sha256_paths(value, path=()):
    paths = set()
    if type(value) is dict:
        for key, item in value.items():
            child = path + (key,)
            if key.endswith("sha256"):
                paths.add(child)
            paths.update(_sha256_paths(item, child))
    elif type(value) is list:
        for item in value:
            paths.update(_sha256_paths(item, path + ("[]",)))
    return frozenset(paths)


def _field_names(value):
    names = set()
    if type(value) is dict:
        names.update(value)
        for item in value.values():
            names.update(_field_names(item))
    elif type(value) is list:
        for item in value:
            names.update(_field_names(item))
    return names


class PersonaV2SourceIntentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.values = source_intent.build_source_intent_origin_shard_suite()
        cls.topology = topology.build_topology_contract()
        cls.realism = realism.build_realism_profile()
        cls.variants = variants.build_variant_catalog()
        cls.source_profiles = source_profiles.build_source_profile_catalog()
        cls.route = route_affinity.build_route_affinity()
        cls.fact_graphs = fact_graph.build_fact_graph_suite()

    def test_all_twenty_personas_have_one_explicit_non_authorizing_slice(self):
        self.assertEqual(
            [value["persona_id"] for value in self.values],
            list(envelope.PERSONA_IDS),
        )
        self.assertEqual(len(self.values), 20)
        self.assertEqual(
            sum(len(value["intent_rows"]) for value in self.values), 20
        )
        self.assertEqual(
            sum(
                value["coverage"]["declared_persona_full_w0_physical_sources"]
                for value in self.values
            ),
            203_000,
        )
        for persona_id, value in zip(envelope.PERSONA_IDS, self.values):
            self.assertEqual(value["artifact_schema"], source_intent.ARTIFACT_SCHEMA)
            self.assertEqual(value["artifact_kind"], source_intent.ARTIFACT_KIND)
            self.assertEqual(value["artifact_schema_version"], 2)
            self.assertEqual(value["fixture_id"], envelope.FIXTURE_ID)
            self.assertEqual(value["fixture_schema_version"], 2)
            self.assertEqual(value["persona_id"], persona_id)
            self.assertIs(value["g0_contract_frozen"], False)
            self.assertEqual(set(value["authority"]), source_intent.AUTHORITY_FIELDS)
            for key, flag in value["authority"].items():
                self.assertIs(type(flag), bool, key)
                self.assertIs(flag, False, key)
            for key, flag in value["isolation_policy"].items():
                self.assertIs(type(flag), bool, key)
                self.assertIs(flag, False, key)

            claims = value["completion_claims"]
            self.assertIs(
                claims["source_intent_origin_shard_vertical_slice_complete"], True
            )
            self.assertIs(claims["representative_origin_row_complete"], True)
            self.assertIs(claims["candidate_source_profile_projection_bound"], True)
            for key in (
                "bounded_jsonl_loader_bound_to_source_shard_frame",
                "external_frame_header_schema_dispatcher_available",
                "fact_membership_exact_projection_bound",
                "formal_source_recipe_profile_bound",
                "full_persona_package_bound_proved",
                "history_event_recipe_bound",
                "overlay_instances_bound",
                "source_intent_inventory_complete",
                "source_intent_manifest_complete",
                "source_level_exact_allocation_complete",
            ):
                self.assertIs(claims[key], False, key)
            self.assertEqual(value["coverage"]["represented_intent_count"], 1)
            self.assertEqual(
                value["coverage"]["represented_origin_counts"],
                {"full-residual": 0, "pilot": 1},
            )
            self.assertEqual(
                value["coverage"]["declared_suite_full_w0_physical_sources"],
                203_000,
            )
            self.assertLess(
                len(source_intent.canonical_json_bytes(value)),
                source_intent.MAX_SHARD_BYTES,
            )
            self.assertTrue(
                source_intent.validate_source_intent_origin_shard(persona_id, value)
            )

    def test_canonical_bytes_and_digests_are_exactly_pinned(self):
        actual = tuple(
            (
                value["persona_id"],
                len(source_intent.canonical_json_bytes(value)),
                source_intent.source_intent_origin_shard_sha256(
                    value["persona_id"], value
                ),
                value["intent_row_byte_counts_including_lf"][0],
                value["catalogs"]["source_profiles"][0]["variant_id"],
            )
            for value in self.values
        )
        self.assertEqual(actual, EXPECTED_PERSONA_BINDINGS)
        for value in self.values:
            raw = source_intent.canonical_json_bytes(value)
            self.assertEqual(
                hashlib.sha256(raw).hexdigest(),
                source_intent.source_intent_origin_shard_sha256(
                    value["persona_id"], value
                ),
            )

    def test_only_corpus_semantic_bodies_are_bound_one_way(self):
        topology_sha = topology.topology_contract_sha256(self.topology)
        realism_sha = realism.realism_profile_sha256(self.realism)
        variant_sha = variants.variant_catalog_sha256(self.variants)
        profile_sha = source_profiles.source_profile_catalog_sha256(
            self.source_profiles
        )
        route_sha = route_affinity.route_affinity_sha256(self.route)
        facts = {value["persona_id"]: value for value in self.fact_graphs}
        expected_names = [
            "topology",
            "realism-profile",
            "variant-catalog",
            "source-profile-catalog",
            "route-affinity-body",
            "typed-fact-graph",
        ]
        expected_shared = [
            topology_sha,
            realism_sha,
            variant_sha,
            profile_sha,
            route_sha,
        ]
        for value in self.values:
            bindings = value["input_bindings"]
            self.assertEqual(value["input_binding_order"], expected_names)
            self.assertEqual([row["name"] for row in bindings], expected_names)
            self.assertEqual(
                [row["sha256"] for row in bindings[:5]], expected_shared
            )
            persona_id = value["persona_id"]
            self.assertEqual(bindings[-1]["persona_id"], persona_id)
            self.assertEqual(
                bindings[-1]["sha256"],
                hashlib.sha256(
                    fact_graph.canonical_json_bytes(facts[persona_id])
                ).hexdigest(),
            )
            self.assertEqual(
                _sha256_paths(value),
                frozenset({("input_bindings", "[]", "sha256")}),
            )
            namespace = value["identity_namespace_policy"]
            self.assertEqual(
                namespace["future_identity_namespace_basis"],
                "content-affecting-corpus-semantic-inputs-only",
            )
            self.assertIs(namespace["route_body_binding_required"], True)
            self.assertIs(
                namespace["non_content_review_or_evidence_receipt_bytes_included"],
                False,
            )
            self.assertIs(
                namespace["receipt_replacement_may_change_intent_bytes"], False
            )

        module_source = inspect.getsource(source_intent)
        self.assertNotIn("persona_v2_route_review_receipt", module_source)
        self.assertFalse(
            any(
                row["name"] == "route-review-receipt"
                for value in self.values
                for row in value["input_bindings"]
            )
        )

    def test_candidate_profiles_prebind_format_and_local_byte_formula_only(self):
        ready_profiles = {
            row["variant_id"]: row
            for row in self.source_profiles["source_profile_rows"]
            if row["bounded_feasibility"]["vertical_slice_ready"]
        }
        for ordinal, value in enumerate(self.values, start=1):
            persona_id = value["persona_id"]
            candidates = [
                row
                for row in self.variants["persona_variant_marginals"]
                if row["persona_id"] == persona_id
                and row["variant_id"] in ready_profiles
                and row["pilot_count"] > 0
            ]
            selected = min(
                candidates,
                key=lambda row: (
                    -row["pilot_count"],
                    row["variant_id"].encode("ascii"),
                ),
            )
            upstream = ready_profiles[selected["variant_id"]]
            projected = value["catalogs"]["source_profiles"][0]
            self.assertEqual(projected["variant_id"], selected["variant_id"])
            self.assertEqual(projected["family"], upstream["family"])
            self.assertEqual(projected["gate_role"], "contract_contributor")
            self.assertEqual(
                projected["source_profile_id"],
                upstream["bounded_feasibility_profile_id"],
            )
            self.assertEqual(projected["formal_source_recipe_profile_id"], "not-bound")
            self.assertEqual(
                value["intent_rows"][0]["source_profile_id"],
                projected["source_profile_id"],
            )
            quota = value["catalogs"]["quota_contexts"][0]
            self.assertEqual(quota["target_complexity"], ordinal * 3)
            formula = projected["byte_formula"]
            expected_bytes = formula["base_bytes_at_complexity_one"] + (
                quota["target_complexity"] - 1
            ) * formula["increment_bytes_per_additional_complexity"]
            self.assertEqual(quota["target_bytes"], expected_bytes)
            self.assertGreaterEqual(
                quota["target_bytes"], formula["minimum_rendered_bytes"]
            )
            self.assertLessEqual(
                quota["target_bytes"], formula["maximum_rendered_bytes"]
            )
            self.assertEqual(
                value["coverage"]["selected_variant_pilot_count"],
                selected["pilot_count"],
            )
            self.assertEqual(
                value["coverage"]["selected_variant_full_count"],
                selected["full_count"],
            )

    def test_scope_fact_content_placement_and_quota_contexts_are_exact(self):
        topology_rows = {row["persona_id"]: row for row in self.topology["personas"]}
        realism_rows = {row["persona_id"]: row for row in self.realism["personas"]}
        fact_values = {row["persona_id"]: row for row in self.fact_graphs}
        membership_keys = set()
        for value in self.values:
            persona_id = value["persona_id"]
            row = value["intent_rows"][0]
            catalogs = value["catalogs"]
            scope_set = catalogs["eligible_scope_sets"][0]
            self.assertEqual(row["eligible_scope_set_id"], scope_set["eligible_scope_set_id"])
            self.assertEqual(
                scope_set["scope_keys"],
                [candidate["scope_key"] for candidate in topology_rows[persona_id]["scopes"]],
            )
            self.assertEqual(len(scope_set["scope_keys"]), 20)

            graph = fact_values[persona_id]["graphs"][0]
            expected_fact_ids = []
            referenced_entities = set()
            for fact in graph["facts"]:
                states = {
                    state["checkpoint"]: state["state"]
                    for state in fact["visibility_by_checkpoint"]
                }
                if states["W0"] == "current":
                    expected_fact_ids.append(fact["fact_id"])
                    referenced_entities.add(fact["subject_entity_id"])
                    if fact["typed_value"].get("kind") == "entity-reference":
                        referenced_entities.add(fact["typed_value"]["entity_id"])
            expected_fact_ids.sort()
            fact_set = catalogs["present_fact_sets"][0]
            self.assertEqual(row["present_fact_set_key"], fact_set["present_fact_set_key"])
            self.assertNotIn(row["present_fact_set_key"], membership_keys)
            membership_keys.add(row["present_fact_set_key"])
            self.assertEqual(fact_set["present_fact_ids"], expected_fact_ids)
            self.assertEqual(len(expected_fact_ids), 8)
            self.assertEqual(len(expected_fact_ids), len(set(expected_fact_ids)))
            self.assertEqual(
                fact_set["synthetic_entity_ids"],
                sorted(
                    entity["entity_id"]
                    for entity in graph["entities"]
                    if entity["entity_id"] in referenced_entities
                ),
            )
            self.assertEqual(fact_set["project_or_case_id"], graph["project_or_case_id"])

            chain = graph["revision_chains"][0]
            self.assertIn(chain["prior_fact_ids"][0], expected_fact_ids)
            self.assertNotIn(chain["current_fact_id"], expected_fact_ids)
            quota = catalogs["quota_contexts"][0]
            self.assertEqual(quota["allowed_history_cohort_ids"], ["P", "X", "Y"])
            self.assertEqual(
                quota["allowed_quota_bucket_ids"], list(envelope.DENSITY_BUCKET_ORDER)
            )
            self.assertEqual(quota["history_cohort_assignment_status"], "solver-unassigned")
            self.assertNotIn("history_cohort_id", quota)
            self.assertNotIn("requested_quota", quota)
            self.assertIs(quota["contributor_eligibility"], True)
            self.assertEqual(quota["expected_incidental_chunks_upper"], 0)

            profile = realism_rows[persona_id]
            placement = catalogs["placement_contexts"][0]
            self.assertEqual(
                placement["permission_profile_id"], profile["permission_profile_id"]
            )
            self.assertIn(placement["sensitivity_tier"], profile["sensitivity_tiers"])

    def test_fact_set_ownership_requires_exact_total_set_projection(self):
        for value in self.values:
            contract = value["fact_set_projection_contract"]
            self.assertEqual(
                contract["canonical_owner"],
                "source-intent-origin-shard-present-fact-set",
            )
            self.assertEqual(
                contract["downstream_projection_rule"], "exact-total-set-equality"
            )
            self.assertIs(contract["duplicate_fact_references_allowed"], False)
            self.assertIs(contract["extra_fact_references_allowed"], False)
            self.assertIs(contract["missing_fact_references_allowed"], False)
            self.assertIs(
                value["completion_claims"]["fact_membership_exact_projection_bound"],
                False,
            )

    def test_origins_separate_solver_delta_and_reuse_pilot_bytes(self):
        for value in self.values:
            contract = value["origin_contract"]
            self.assertEqual(
                contract["allowed_intent_origins"], ["pilot", "full-residual"]
            )
            self.assertEqual(
                contract["solver_delta_to_intent_origin"],
                {"full-minus-pilot": "full-residual"},
            )
            self.assertIs(
                contract["solver_delta_value_allowed_as_intent_origin"], False
            )
            self.assertEqual(
                contract["aggregate_profile_to_intent_origins"],
                {
                    "full": ["pilot", "full-residual"],
                    "pilot": ["pilot"],
                },
            )
            self.assertIs(contract["full_manifest_reuses_pilot_shard_bytes"], True)
            self.assertIs(contract["full_residual_uses_separate_shards"], True)
            self.assertEqual(value["intent_rows"][0]["origin"], "pilot")
            self.assertNotEqual(
                value["intent_rows"][0]["origin"], "full-minus-pilot"
            )

    def test_intent_row_and_shard_bounds_include_jsonl_lf(self):
        maximum_actual = 0
        for value in self.values:
            row = value["intent_rows"][0]
            self.assertEqual(set(row), source_intent.INTENT_ROW_FIELDS)
            raw = artifact_common.canonical_json_bytes(
                row,
                label="test source-intent row",
                max_bytes=source_intent.MAX_INTENT_ROW_BODY_BYTES,
            )
            record_bytes = len(raw) + source_intent.JSONL_RECORD_TERMINATOR_BYTES
            maximum_actual = max(maximum_actual, record_bytes)
            self.assertEqual(
                value["intent_row_byte_counts_including_lf"], [record_bytes]
            )
            self.assertLessEqual(
                record_bytes, source_intent.MAX_INTENT_JSONL_RECORD_BYTES
            )
            self.assertEqual(
                value["canonical_limits"][
                    "max_intent_jsonl_record_bytes_including_terminator"
                ],
                768,
            )
            self.assertEqual(
                value["canonical_limits"]["max_eligible_scope_keys_per_set"], 20
            )
            self.assertEqual(
                value["canonical_limits"]["max_present_fact_ids_per_set"], 32
            )
            self.assertEqual(
                value["canonical_limits"]["max_synthetic_entity_ids_per_set"],
                16,
            )
            self.assertIs(
                value["completion_claims"]["full_persona_package_bound_proved"],
                False,
            )
        self.assertGreater(maximum_actual, 0)

        probe = source_intent.build_lexically_maximum_intent_row_probe()
        probe_raw = json.dumps(
            probe,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.assertEqual(set(probe), source_intent.INTENT_ROW_FIELDS)
        self.assertLessEqual(len(probe_raw) + 1, 768)
        self.assertLessEqual(
            source_intent.MAX_INTENTS_PER_SHARD
            * source_intent.MAX_INTENT_JSONL_RECORD_BYTES,
            3 * 2**20,
        )
        p12 = self.values[envelope.PERSONA_IDS.index("p12")]
        self.assertEqual(
            p12["coverage"]["declared_persona_full_w0_physical_sources"], 16_000
        )
        self.assertEqual(p12["coverage"]["represented_intent_count"], 1)
        self.assertIn(
            "p12-16000-intent-overlay-manifest-package-cap-not-proved",
            p12["remaining_blockers"],
        )

    def test_no_downstream_identity_evaluation_or_cycle_fields_are_embedded(self):
        for value in self.values:
            names = _field_names(value)
            self.assertTrue(source_intent.PROHIBITED_FIELD_NAMES.isdisjoint(names))
            raw = source_intent.canonical_json_bytes(value).lower()
            for token in (
                b'"query',
                b'"semantic_oracle',
                b'"materialization_id',
                b'"solution_sha256',
                b'"source_plan_sha256',
                b'route-review-receipt',
            ):
                self.assertNotIn(token, raw)

        for alias in (
            "oracle_id",
            "planned_event_id",
            "query_spec_id",
            "final_materialization_key",
            "result_observed_rank",
            "source_plan_id",
        ):
            with self.subTest(alias=alias):
                with self.assertRaisesRegex(
                    source_intent.PersonaV2SourceIntentError,
                    "prohibited downstream field",
                ):
                    source_intent._assert_no_prohibited_fields({alias: "candidate"})
        with self.assertRaisesRegex(
            source_intent.PersonaV2SourceIntentError,
            "prohibited downstream field",
        ):
            source_intent._assert_no_prohibited_fields(
                {"nested": {"authorizes_source_plan": False}}
            )

    def test_detachment_exact_regeneration_and_fail_closed_mutations(self):
        first = source_intent.build_source_intent_origin_shard("p01")
        second = source_intent.build_source_intent_origin_shard("p01")
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        first["catalogs"]["present_fact_sets"][0]["present_fact_ids"].append(
            "fact-syn-999"
        )
        self.assertNotEqual(first, second)
        self.assertNotIn(
            "fact-syn-999",
            source_intent.build_source_intent_origin_shard("p01")["catalogs"][
                "present_fact_sets"
            ][0]["present_fact_ids"],
        )

        mutations = (
            lambda value: value["authority"].__setitem__(
                "authorizes_physical_write", True
            ),
            lambda value: value["authority"].__setitem__(
                "authorizes_history_mutation", 0
            ),
            lambda value: value["intent_rows"][0].__setitem__(
                "origin", "full-minus-pilot"
            ),
            lambda value: value["catalogs"]["present_fact_sets"][0][
                "present_fact_ids"
            ].append(
                value["catalogs"]["present_fact_sets"][0]["present_fact_ids"][0]
            ),
            lambda value: value["input_bindings"].append(
                {
                    "artifact_kind": "foreign",
                    "artifact_schema": "foreign/v1",
                    "artifact_schema_version": 1,
                    "canonical_bytes": 1,
                    "dependency_role": "review-evidence",
                    "name": "route-review-receipt",
                    "sha256": "0" * 64,
                }
            ),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                value = copy.deepcopy(second)
                mutate(value)
                with self.assertRaises(source_intent.PersonaV2SourceIntentError):
                    source_intent.validate_source_intent_origin_shard("p01", value)

    def test_unknown_personas_and_completion_claim_fail_closed(self):
        for invalid in (None, 1, True, "p00", "p21"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(source_intent.PersonaV2SourceIntentError):
                    source_intent.build_source_intent_origin_shard(invalid)
                with self.assertRaises(source_intent.PersonaV2SourceIntentError):
                    source_intent.validate_source_intent_origin_shard(invalid, {})
                with self.assertRaises(source_intent.PersonaV2SourceIntentError):
                    source_intent.source_intent_origin_shard_sha256(invalid)
        with self.assertRaisesRegex(
            source_intent.PersonaV2SourceIntentError,
            "203,000 source intents",
        ):
            source_intent.require_complete_source_intent_inventory()


if __name__ == "__main__":
    unittest.main()
