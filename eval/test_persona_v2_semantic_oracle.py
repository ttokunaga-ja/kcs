import copy
import unittest

from eval import persona_v2_contract as envelope
from eval import persona_v2_fact_graph as fact_graph
from eval import persona_v2_query_intent as query_intent
from eval import persona_v2_semantic_oracle as semantic_oracle


EXPECTED_P01_CANONICAL_BYTES = 199_521
EXPECTED_P01_SHA256 = (
    "653508e88689f34e70d8702e4d59bfde9bde1dbf8f45190963a043435571a0c3"
)


def _walk_keys(value):
    if type(value) is list:
        for item in value:
            yield from _walk_keys(item)
    elif type(value) is dict:
        for key, item in value.items():
            yield key
            yield from _walk_keys(item)


class PersonaV2SemanticOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = semantic_oracle.build_semantic_oracle("p01")
        cls.graph = fact_graph.build_fact_graph("p01")
        cls.query = query_intent.build_query_intent("p01")

    def test_identity_limit_determinism_bindings_and_negative_authority_are_exact(self):
        value = self.value
        self.assertEqual(value["artifact_schema"], semantic_oracle.ARTIFACT_SCHEMA)
        self.assertEqual(value["artifact_kind"], semantic_oracle.ARTIFACT_KIND)
        self.assertEqual(value["artifact_schema_version"], 2)
        self.assertEqual(value["fixture_id"], envelope.FIXTURE_ID)
        self.assertEqual(value["persona_id"], "p01")
        self.assertIs(value["g0_contract_frozen"], False)
        self.assertTrue(all(flag is False for flag in value["authority"].values()))
        self.assertEqual(
            [row["name"] for row in value["input_bindings"]],
            ["fact-graph", "query-intent"],
        )
        self.assertEqual(
            value["input_bindings"][1]["sha256"],
            query_intent.query_intent_sha256("p01", self.query),
        )

        raw = semantic_oracle.canonical_json_bytes(value)
        self.assertEqual(len(raw), EXPECTED_P01_CANONICAL_BYTES)
        self.assertLess(len(raw), semantic_oracle.MAX_SEMANTIC_ORACLE_BYTES)
        self.assertEqual(
            semantic_oracle.semantic_oracle_sha256("p01", value),
            EXPECTED_P01_SHA256,
        )
        self.assertTrue(semantic_oracle.validate_semantic_oracle("p01", value))

    def test_every_positive_binds_exact_fact_predicate_revision_and_membership_key(self):
        facts = {
            fact["fact_id"]: fact
            for graph in self.graph["graphs"]
            for fact in graph["facts"]
        }
        revisions = {
            chain["revision_chain_id"]
            for graph in self.graph["graphs"]
            for chain in graph["revision_chains"]
        }
        membership_keys = []
        for row in self.value["positive_oracle_rows"]:
            membership = row["abstract_answer_membership"]
            membership_keys.append(membership["answer_membership_key"])
            self.assertEqual(len(membership["expected_fact_ids"]), 1)
            fact = facts[membership["expected_fact_ids"][0]]
            self.assertEqual(
                membership["expected_predicate_ids"], [fact["predicate_id"]]
            )
            self.assertTrue(
                set(membership["expected_revision_chain_ids"]).issubset(revisions)
            )
            self.assertEqual(membership["semantic_section_role"], "answer-bearing-section")
            self.assertTrue(membership["target_intent_key"].startswith("intent-p01-"))
            self.assertTrue(
                membership["target_logical_document_key"].startswith(
                    "logical-document-p01-"
                )
            )
            self.assertEqual(len(row["distractors"]), 3)
            self.assertTrue(
                all(
                    distractor["language"] == row["language"]
                    and distractor["excluded_from_abstract_relevance"] is True
                    for distractor in row["distractors"]
                )
            )
        self.assertEqual(len(membership_keys), 90)
        self.assertEqual(len(membership_keys), len(set(membership_keys)))

    def test_strata_evidence_is_exact_and_locale_lifecycle_is_unambiguous(self):
        rows = self.value["positive_oracle_rows"]
        by_stratum = {}
        for row in rows:
            by_stratum.setdefault(row["stratum_id"], []).append(row)
            self.assertEqual(row["top_k"], 10)
            self.assertIs(row["expected_empty"], False)
            query_row = next(
                item
                for item in self.query["positive_query_intents"]
                if item["query_key"] == row["query_intent_key"]
            )
            self.assertEqual(
                row["evidence_contract"]["selector"], query_row["selector"]
            )
            self.assertEqual(
                row["evidence_contract"]["required_evidence_state"],
                query_row["required_evidence_state"],
            )
        self.assertEqual(set(by_stratum), set(query_intent.SELECTOR_BY_STRATUM))
        self.assertTrue(all(len(values) == 10 for values in by_stratum.values()))
        self.assertEqual(
            {row["evidence_contract"]["operation_kind"] for row in by_stratum["rename-move"]},
            {"same-scope-rename", "searchable-cross-scope-move"},
        )
        for row in by_stratum["locale-language-lifecycle"]:
            evidence = row["evidence_contract"]
            self.assertEqual(evidence["selector"], "--all-history")
            self.assertEqual(evidence["lifecycle_operation_kind"], "archive")
            self.assertEqual(
                evidence["required_evidence_state"],
                "locale-language-lifecycle-history",
            )

    def test_restored_and_final_deleted_sets_are_distinct_and_strict(self):
        rows = self.value["positive_oracle_rows"]
        restored = [row for row in rows if row["stratum_id"] == "restored"]
        deleted = [row for row in rows if row["stratum_id"] == "deleted"]
        self.assertEqual(len(restored), 10)
        self.assertEqual(len(deleted), 10)
        restore_anchors = {
            row["evidence_contract"]["restore_anchor_key"] for row in restored
        }
        self.assertEqual(len(restore_anchors), 10)
        restored_documents = {
            row["abstract_answer_membership"]["target_logical_document_key"]
            for row in restored
        }
        deleted_documents = {
            row["abstract_answer_membership"]["target_logical_document_key"]
            for row in deleted
        }
        self.assertFalse(restored_documents & deleted_documents)
        for row in restored:
            evidence = row["evidence_contract"]
            self.assertEqual(
                evidence["required_event_order"],
                ["delete", "restore", "destination-index"],
            )
            self.assertIs(evidence["new_restored_materialization_required"], True)
            self.assertIs(evidence["destination_index_receipt_required"], True)
            self.assertIs(
                evidence["same_content_other_current_copy_sufficient"], False
            )
            self.assertIs(evidence["raw_only_structural_sentinel_sufficient"], False)
        for row in deleted:
            evidence = row["evidence_contract"]
            self.assertEqual(evidence["selector"], "--include-deleted")
            self.assertEqual(evidence["required_evidence_state"], "final-deleted")
            self.assertIs(evidence["live_current_copy_sufficient"], False)

    def test_negative_rows_are_empty_relevance_and_replay_observations_are_exact(self):
        negatives = self.value["negative_oracle_rows"]
        self.assertEqual(len(negatives), 15)
        for row in negatives:
            self.assertEqual(row["abstract_answer_membership"], [])
            self.assertIs(row["expected_empty"], True)
            self.assertEqual(row["false_positive_at_10_must_equal"], 0)
            self.assertEqual(row["top_k"], 10)
            self.assertEqual(
                row["evidence_contract"]["required_evidence_state"],
                "purged-absent",
            )
        self.assertEqual(
            self.value["replay_evaluation_contract"],
            {
                "negative_observation_rows_required": 45,
                "positive_observation_rows_required": 270,
                "query_spec_rows_per_persona": 105,
                "replay_count": 3,
                "same_semantic_oracle_reused_unchanged_across_replays": True,
                "total_observation_rows_required": 315,
            },
        )

    def test_oracle_has_no_final_identity_and_cannot_affect_corpus_namespace(self):
        forbidden = {
            "chunk_id",
            "expected_chunk_ids",
            "expected_materialization_ids",
            "expected_section_ids",
            "expected_source_ids",
            "final_materialization_id",
            "final_source_id",
            "latency",
            "materialization_id",
            "normalized_section_id",
            "path",
            "query_text",
            "rank",
            "raw_hash",
            "raw_sha256",
            "rendered_query",
            "rendered_query_text",
            "score",
            "section_id",
            "source_id",
        }
        self.assertFalse(set(_walk_keys(self.value)) & forbidden)
        compiled = self.value["compiled_relevance_contract"]
        self.assertIs(compiled["actual_identity_membership_present"], False)
        self.assertIs(compiled["formal_mvp_relevance_projection_present"], False)
        self.assertIs(compiled["semantic_logical_document_projection_only"], True)
        direction = self.value["dependency_direction_contract"]
        self.assertIs(direction["corpus_renderer_access_allowed"], False)
        self.assertIs(
            direction["corpus_namespace_or_bytes_may_depend_on_this_artifact"],
            False,
        )
        self.assertIs(direction["oracle_change_may_change_corpus_root"], False)
        self.assertIs(direction["oracle_change_may_change_source_id_preimage"], False)
        self.assertTrue(
            semantic_oracle.require_consumer_access("query-renderer")
        )
        for role in ("corpus-renderer", "source-id-deriver", ""):
            with self.assertRaises(
                semantic_oracle.PersonaV2SemanticOracleError
            ):
                semantic_oracle.require_consumer_access(role)
        self.assertIs(
            self.value["completion_claims"]["membership_totality_proved"], False
        )

    def test_suite_has_200_one_to_one_restore_anchors_and_disjoint_deleted_set(self):
        suite = semantic_oracle.build_semantic_oracle_suite()
        self.assertTrue(
            all(
                len(semantic_oracle.canonical_json_bytes(value))
                < semantic_oracle.MAX_SEMANTIC_ORACLE_BYTES
                for value in suite
            )
        )
        anchors = []
        restored_documents = []
        deleted_documents = []
        restored_intents = []
        for value in suite:
            for row in value["positive_oracle_rows"]:
                membership = row["abstract_answer_membership"]
                if row["stratum_id"] == "restored":
                    anchors.append(row["evidence_contract"]["restore_anchor_key"])
                    restored_documents.append(
                        membership["target_logical_document_key"]
                    )
                    restored_intents.append(membership["target_intent_key"])
                elif row["stratum_id"] == "deleted":
                    deleted_documents.append(
                        membership["target_logical_document_key"]
                    )
        self.assertEqual(len(anchors), 200)
        self.assertEqual(len(set(anchors)), 200)
        self.assertEqual(len(set(restored_documents)), 200)
        self.assertEqual(len(set(restored_intents)), 200)
        self.assertEqual(len(set(deleted_documents)), 200)
        self.assertFalse(set(restored_documents) & set(deleted_documents))
        self.assertEqual(
            sum(
                value["replay_evaluation_contract"][
                    "total_observation_rows_required"
                ]
                for value in suite
            ),
            6_300,
        )

    def test_wrong_fact_mutation_or_wrong_persona_fails_closed(self):
        changed = copy.deepcopy(self.value)
        changed["positive_oracle_rows"][0]["abstract_answer_membership"][
            "expected_fact_ids"
        ] = ["fact-syn-002"]
        with self.assertRaises(semantic_oracle.PersonaV2SemanticOracleError):
            semantic_oracle.validate_semantic_oracle("p01", changed)
        with self.assertRaises(semantic_oracle.PersonaV2SemanticOracleError):
            semantic_oracle.validate_semantic_oracle("p02", self.value)
        with self.assertRaises(semantic_oracle.PersonaV2SemanticOracleError):
            semantic_oracle.build_semantic_oracle("p99")


if __name__ == "__main__":
    unittest.main()
