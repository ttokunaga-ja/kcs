import copy
import unittest

from eval import persona_v2_contract as envelope
from eval import persona_v2_query_intent as query_intent


EXPECTED_P01_CANONICAL_BYTES = 65_798
EXPECTED_P01_SHA256 = (
    "5478902782eaa7f92952e3f09cf73a8e1af0bf1360e34edad2eca044e6211729"
)


def _walk_keys(value):
    if type(value) is list:
        for item in value:
            yield from _walk_keys(item)
    elif type(value) is dict:
        for key, item in value.items():
            yield key
            yield from _walk_keys(item)


class PersonaV2QueryIntentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = query_intent.build_query_intent("p01")

    def test_identity_limit_determinism_and_negative_authority_are_exact(self):
        value = self.value
        self.assertEqual(value["artifact_schema"], query_intent.ARTIFACT_SCHEMA)
        self.assertEqual(value["artifact_kind"], query_intent.ARTIFACT_KIND)
        self.assertEqual(value["artifact_schema_version"], 2)
        self.assertEqual(value["fixture_id"], envelope.FIXTURE_ID)
        self.assertEqual(value["persona_id"], "p01")
        self.assertIs(value["g0_contract_frozen"], False)
        self.assertTrue(all(flag is False for flag in value["authority"].values()))

        raw = query_intent.canonical_json_bytes(value)
        self.assertEqual(len(raw), EXPECTED_P01_CANONICAL_BYTES)
        self.assertLess(len(raw), query_intent.MAX_QUERY_INTENT_BYTES)
        self.assertEqual(
            query_intent.query_intent_sha256("p01", value),
            EXPECTED_P01_SHA256,
        )
        self.assertTrue(query_intent.validate_query_intent("p01", value))

    def test_cardinality_strata_and_machine_selectors_are_exact(self):
        value = self.value
        positives = value["positive_query_intents"]
        negatives = value["negative_query_intents"]
        self.assertEqual(len(positives), 90)
        self.assertEqual(len(negatives), 15)

        expected = {
            (scenario_id, stratum_id): 10
            for scenario_id, strata in query_intent.SCENARIO_STRATA
            for stratum_id in strata
        }
        actual = {}
        for row in positives:
            key = (row["scenario_id"], row["stratum_id"])
            actual[key] = actual.get(key, 0) + 1
            self.assertEqual(row["evaluation_checkpoint"], "W5-final")
            self.assertEqual(
                row["selector"],
                query_intent.SELECTOR_BY_STRATUM[row["stratum_id"]],
            )
            self.assertEqual(
                row["required_evidence_state"],
                query_intent.REQUIRED_EVIDENCE_STATE_BY_STRATUM[
                    row["stratum_id"]
                ],
            )
            self.assertIs(row["expected_empty"], False)
            self.assertEqual(row["top_k"], 10)
            self.assertEqual(
                row["dedup_projection"],
                "logical-document-key-semantic-candidate",
            )
        self.assertEqual(actual, expected)

        by_scenario = {}
        for row in negatives:
            by_scenario[row["scenario_id"]] = (
                by_scenario.get(row["scenario_id"], 0) + 1
            )
            self.assertEqual(
                row["selector"],
                query_intent.NEGATIVE_SELECTOR_BY_SCENARIO[row["scenario_id"]],
            )
            self.assertEqual(row["required_evidence_state"], "purged-absent")
            self.assertIs(row["expected_empty"], True)
            self.assertIs(row["recall_denominator_member"], False)
            self.assertEqual(row["false_positive_at_10_must_equal"], 0)
            self.assertEqual(row["top_k"], 10)
        self.assertEqual(by_scenario, {"M3-1": 5, "M3-2": 5, "M3-3": 5})

    def test_query_data_has_no_text_final_identity_or_observed_output(self):
        forbidden = {
            "chunk_id",
            "final_materialization_id",
            "final_source_id",
            "latency",
            "materialization_id",
            "normalized_section_id",
            "path",
            "query_template",
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
        direction = self.value["dependency_direction_contract"]
        self.assertIs(direction["corpus_renderer_access_allowed"], False)
        self.assertIs(
            direction["corpus_renderer_projection_contains_query_intent"], False
        )
        self.assertIs(direction["query_or_oracle_change_may_change_corpus_root"], False)
        self.assertIs(
            direction["query_or_oracle_change_may_change_source_id_preimage"],
            False,
        )
        self.assertTrue(
            query_intent.require_consumer_access("semantic-oracle-builder")
        )
        for role in ("corpus-renderer", "source-id-deriver", ""):
            with self.assertRaises(query_intent.PersonaV2QueryIntentError):
                query_intent.require_consumer_access(role)

    def test_targets_are_explicitly_unresolved_until_total_membership_exists(self):
        contract = self.value["target_resolution_contract"]
        self.assertIs(contract["source_intent_targets_bound"], False)
        self.assertIs(contract["fact_membership_targets_bound"], False)
        self.assertIs(contract["history_intent_targets_bound"], False)
        self.assertIs(contract["membership_totality_proved"], False)
        self.assertIs(
            contract["all_expected_targets_must_exact_resolve_before_g0"], True
        )
        rows = (
            self.value["positive_query_intents"]
            + self.value["negative_query_intents"]
        )
        for key in (
            "query_key",
            "target_intent_key",
            "target_logical_document_key",
        ):
            values = [row[key] for row in rows]
            self.assertEqual(len(values), len(set(values)))

    def test_multilingual_locale_strata_use_non_primary_language(self):
        positives = self.value["positive_query_intents"]
        for stratum_id in (
            "locale-language-fact",
            "locale-language-history",
            "locale-language-lifecycle",
        ):
            rows = [row for row in positives if row["stratum_id"] == stratum_id]
            self.assertEqual(len(rows), 10)
            self.assertTrue(any(row["language"] == "en" for row in rows))

    def test_suite_specs_are_global_unique_and_replay_rows_are_not_under_counted(self):
        suite = query_intent.build_query_intent_suite()
        self.assertEqual([row["persona_id"] for row in suite], list(envelope.PERSONA_IDS))
        self.assertTrue(
            all(
                len(query_intent.canonical_json_bytes(value))
                < query_intent.MAX_QUERY_INTENT_BYTES
                for value in suite
            )
        )
        all_rows = [
            item
            for value in suite
            for item in (
                value["positive_query_intents"] + value["negative_query_intents"]
            )
        ]
        self.assertEqual(len(all_rows), 2_100)
        self.assertEqual(
            sum(value["summary"]["positive_query_count"] for value in suite),
            1_800,
        )
        self.assertEqual(
            sum(value["summary"]["negative_query_count"] for value in suite),
            300,
        )
        for key in (
            "query_key",
            "target_intent_key",
            "target_logical_document_key",
        ):
            values = [row[key] for row in all_rows]
            self.assertEqual(len(values), len(set(values)))
        self.assertEqual(
            sum(
                value["replay_evaluation_contract"][
                    "total_observation_rows_required"
                ]
                for value in suite
            ),
            6_300,
        )

    def test_mutation_or_wrong_persona_fails_closed(self):
        changed = copy.deepcopy(self.value)
        changed["positive_query_intents"][0]["selector"] = "all-history"
        with self.assertRaises(query_intent.PersonaV2QueryIntentError):
            query_intent.validate_query_intent("p01", changed)
        with self.assertRaises(query_intent.PersonaV2QueryIntentError):
            query_intent.validate_query_intent("p02", self.value)
        with self.assertRaises(query_intent.PersonaV2QueryIntentError):
            query_intent.build_query_intent("p99")


if __name__ == "__main__":
    unittest.main()
