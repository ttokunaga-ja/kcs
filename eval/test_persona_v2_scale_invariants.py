"""Independent literal scale guards for non-authorizing persona-PC v2 planning.

The expected values in this module are intentionally duplicated literals.  The
tests compare those literals with the production planning catalogs instead of
recomputing expectations from the same production constants.  Passing this
suite proves cardinality consistency only; it grants no G0, solver, writer,
history-execution, KCS-execution, or observed-evidence authority.
"""

import unittest

from eval import persona_v2_contract as envelope
from eval import persona_v2_history_intent as history_intent
from eval import persona_v2_joint_problem as joint_problem
from eval import persona_v2_query_intent as query_intent
from eval import persona_v2_source_inventory_layout as source_inventory_layout
from eval import persona_v2_source_intent as source_intent


PERSONA_COUNT = 20
REPLAY_COUNT = 3
CHECKPOINT_ORDER = (
    "W0",
    "W1",
    "W2",
    "W3",
    "W4",
    "W5-pre-purge",
    "W5-final",
)

# Values are (pilot W0 physical sources, full W0 physical sources).  Keep this
# literal table independent of the envelope and source-intent implementations.
PERSONA_W0_PHYSICAL_SOURCE_COUNTS = {
    "p01": (1_200, 12_000),
    "p02": (1_500, 15_000),
    "p03": (1_000, 10_000),
    "p04": (1_000, 10_000),
    "p05": (1_200, 12_000),
    "p06": (800, 8_000),
    "p07": (700, 7_000),
    "p08": (800, 8_000),
    "p09": (900, 9_000),
    "p10": (1_100, 11_000),
    "p11": (1_000, 10_000),
    "p12": (1_600, 16_000),
    "p13": (700, 7_000),
    "p14": (1_300, 13_000),
    "p15": (800, 8_000),
    "p16": (800, 8_000),
    "p17": (800, 8_000),
    "p18": (1_200, 12_000),
    "p19": (900, 9_000),
    "p20": (1_000, 10_000),
}

EXPECTED_RESIDUAL_SOURCE_INTENT_SHARDS = {
    "p01": 3,
    "p02": 4,
    "p03": 3,
    "p04": 3,
    "p05": 3,
    "p06": 2,
    "p07": 2,
    "p08": 2,
    "p09": 2,
    "p10": 3,
    "p11": 3,
    "p12": 4,
    "p13": 2,
    "p14": 3,
    "p15": 2,
    "p16": 2,
    "p17": 2,
    "p18": 3,
    "p19": 2,
    "p20": 3,
}

LITERAL_HISTORY_CHECKPOINTS = {
    "pilot": {
        "W0": (12_000, 0),
        "W1": (12_000, 2_400),
        "W2": (12_000, 2_400),
        "W3": (12_000, 4_800),
        "W4": (12_000, 6_000),
        "W5-pre-purge": (12_480, 6_480),
        "W5-final": (12_000, 6_000),
    },
    "full": {
        "W0": (120_000, 0),
        "W1": (120_000, 24_000),
        "W2": (120_000, 24_000),
        "W3": (120_000, 48_000),
        "W4": (120_000, 60_000),
        "W5-pre-purge": (124_800, 64_800),
        "W5-final": (120_000, 60_000),
    },
}

LITERAL_EVENT_DELTAS = {
    "pilot": {
        "W0->W1": (0, 2_400),
        "W1->W2": (0, 0),
        "W2->W3": (0, 2_400),
        "W3->W4": (0, 1_200),
        "W4->W5-pre-purge": (480, 480),
        "W5-pre-purge->W5-final": (-480, -480),
    },
    "full": {
        "W0->W1": (0, 24_000),
        "W1->W2": (0, 0),
        "W2->W3": (0, 24_000),
        "W3->W4": (0, 12_000),
        "W4->W5-pre-purge": (4_800, 4_800),
        "W5-pre-purge->W5-final": (-4_800, -4_800),
    },
}

LITERAL_TWENTY_PERSON_REPLAY_TOTALS = {
    "pilot": {
        "W0": (240_000, 0),
        "W1": (240_000, 48_000),
        "W2": (240_000, 48_000),
        "W3": (240_000, 96_000),
        "W4": (240_000, 120_000),
        "W5-pre-purge": (249_600, 129_600),
        "W5-final": (240_000, 120_000),
    },
    "full": {
        "W0": (2_400_000, 0),
        "W1": (2_400_000, 480_000),
        "W2": (2_400_000, 480_000),
        "W3": (2_400_000, 960_000),
        "W4": (2_400_000, 1_200_000),
        "W5-pre-purge": (2_496_000, 1_296_000),
        "W5-final": (2_400_000, 1_200_000),
    },
}

LITERAL_THREE_REPLAY_TOTALS = {
    "pilot": {
        "W0": (720_000, 0),
        "W1": (720_000, 144_000),
        "W2": (720_000, 144_000),
        "W3": (720_000, 288_000),
        "W4": (720_000, 360_000),
        "W5-pre-purge": (748_800, 388_800),
        "W5-final": (720_000, 360_000),
    },
    "full": {
        "W0": (7_200_000, 0),
        "W1": (7_200_000, 1_440_000),
        "W2": (7_200_000, 1_440_000),
        "W3": (7_200_000, 2_880_000),
        "W4": (7_200_000, 3_600_000),
        "W5-pre-purge": (7_488_000, 3_888_000),
        "W5-final": (7_200_000, 3_600_000),
    },
}

LITERAL_GATE_ROLE_FILE_TOTALS = {
    "pilot": {
        "contract_contributor": 6_925,
        "incidental_searchable": 6_040,
        "raw_only": 7_335,
    },
    "full-minus-pilot": {
        "contract_contributor": 62_311,
        "incidental_searchable": 54_374,
        "raw_only": 66_015,
    },
    "full": {
        "contract_contributor": 69_236,
        "incidental_searchable": 60_414,
        "raw_only": 73_350,
    },
}


def _multiply_pair(pair, multiplier):
    return tuple(value * multiplier for value in pair)


def _checkpoint_deltas(rows):
    result = {}
    for before, after in zip(CHECKPOINT_ORDER, CHECKPOINT_ORDER[1:]):
        before_pair = rows[before]
        after_pair = rows[after]
        result[f"{before}->{after}"] = (
            after_pair[0] - before_pair[0],
            after_pair[1] - before_pair[1],
        )
    return result


class PersonaV2LiteralScaleInvariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.problem = joint_problem.build_joint_problem()

    def test_checkpoint_literals_event_deltas_and_production_catalog(self):
        self.assertEqual(history_intent.CHECKPOINT_ORDER, CHECKPOINT_ORDER)
        for profile in ("pilot", "full"):
            with self.subTest(profile=profile):
                literal = LITERAL_HISTORY_CHECKPOINTS[profile]
                self.assertEqual(tuple(literal), CHECKPOINT_ORDER)
                self.assertEqual(
                    dict(envelope.HISTORY_CHECKPOINTS[profile]), literal
                )
                self.assertEqual(
                    _checkpoint_deltas(literal), LITERAL_EVENT_DELTAS[profile]
                )

    def test_twenty_person_and_three_replay_checkpoint_totals(self):
        for profile in ("pilot", "full"):
            for checkpoint in CHECKPOINT_ORDER:
                with self.subTest(profile=profile, checkpoint=checkpoint):
                    per_person = LITERAL_HISTORY_CHECKPOINTS[profile][checkpoint]
                    per_replay = LITERAL_TWENTY_PERSON_REPLAY_TOTALS[profile][
                        checkpoint
                    ]
                    all_replays = LITERAL_THREE_REPLAY_TOTALS[profile][checkpoint]
                    self.assertEqual(
                        _multiply_pair(per_person, 20), per_replay
                    )
                    self.assertEqual(
                        _multiply_pair(per_replay, 3), all_replays
                    )

    def test_gate_role_totals_match_joint_problem_without_authority(self):
        suite = {
            row["profile"]: row
            for row in self.problem["suite_index"]["profiles"]
        }
        for profile, expected in LITERAL_GATE_ROLE_FILE_TOTALS.items():
            with self.subTest(profile=profile):
                self.assertEqual(suite[profile]["gate_role_file_counts"], expected)
                self.assertEqual(
                    sum(expected.values()),
                    {
                        "pilot": 20_300,
                        "full-minus-pilot": 182_700,
                        "full": 203_000,
                    }[profile],
                )
        for role in (
            "contract_contributor",
            "incidental_searchable",
            "raw_only",
        ):
            self.assertEqual(
                LITERAL_GATE_ROLE_FILE_TOTALS["pilot"][role]
                + LITERAL_GATE_ROLE_FILE_TOTALS["full-minus-pilot"][role],
                LITERAL_GATE_ROLE_FILE_TOTALS["full"][role],
            )
        self.assertIs(self.problem["g0_contract_frozen"], False)
        self.assertTrue(self.problem["authority"])
        self.assertTrue(all(flag is False for flag in self.problem["authority"].values()))

    def test_query_inventory_and_replay_observation_arithmetic(self):
        self.assertEqual(query_intent.POSITIVE_QUERIES_PER_STRATUM, 10)
        self.assertEqual(query_intent.NEGATIVE_QUERIES_PER_SCENARIO, 5)
        self.assertEqual(query_intent.REPLAY_COUNT, 3)
        self.assertEqual(len(query_intent.SCENARIO_STRATA), 3)
        self.assertEqual(sum(len(row[1]) for row in query_intent.SCENARIO_STRATA), 9)

        per_person_positive = 90
        per_person_negative = 15
        per_person_total = 105
        suite_positive = 1_800
        suite_negative = 300
        suite_total = 2_100
        replay_observations = 6_300

        self.assertEqual(10 * 9, per_person_positive)
        self.assertEqual(5 * 3, per_person_negative)
        self.assertEqual(per_person_positive + per_person_negative, per_person_total)
        self.assertEqual(20 * per_person_positive, suite_positive)
        self.assertEqual(20 * per_person_negative, suite_negative)
        self.assertEqual(20 * per_person_total, suite_total)
        self.assertEqual(3 * suite_total, replay_observations)

        suite = query_intent.build_query_intent_suite()
        self.assertEqual(len(suite), 20)
        self.assertEqual(
            sum(row["summary"]["positive_query_count"] for row in suite),
            suite_positive,
        )
        self.assertEqual(
            sum(row["summary"]["negative_query_count"] for row in suite),
            suite_negative,
        )
        self.assertEqual(
            sum(row["summary"]["total_query_intent_count"] for row in suite),
            suite_total,
        )
        self.assertEqual(
            sum(
                row["replay_evaluation_contract"][
                    "total_observation_rows_required"
                ]
                for row in suite
            ),
            replay_observations,
        )
        self.assertTrue(all(row["g0_contract_frozen"] is False for row in suite))
        self.assertTrue(
            all(
                row["authority"]
                and all(flag is False for flag in row["authority"].values())
                for row in suite
            )
        )

    def test_observed_checkpoint_receipt_cardinality_is_planning_only(self):
        observed_checkpoint_receipts = 420
        self.assertEqual(20 * 3 * 7, observed_checkpoint_receipts)
        self.assertEqual(
            PERSONA_COUNT * REPLAY_COUNT * len(CHECKPOINT_ORDER),
            observed_checkpoint_receipts,
        )
        with self.assertRaisesRegex(
            history_intent.PersonaV2HistoryIntentError,
            "not a compiled event plan",
        ):
            history_intent.require_compiled_history_plan()

    def test_source_intent_shard_cardinality_from_literal_persona_counts(self):
        self.assertEqual(source_intent.MAX_INTENTS_PER_SHARD, 4_096)
        self.assertEqual(source_intent.MAX_INTENT_JSONL_RECORD_BYTES, 768)
        self.assertEqual(source_intent.MAX_SHARD_BYTES, 4 * 2**20)
        self.assertLessEqual(
            4_096 * 768,
            4 * 2**20,
            "the row cap must bind before the body-byte cap at max record size",
        )

        self.assertEqual(tuple(PERSONA_W0_PHYSICAL_SOURCE_COUNTS), envelope.PERSONA_IDS)
        computed_pilot_shards = {}
        computed_residual_shards = {}
        for persona_id, (pilot_count, full_count) in (
            PERSONA_W0_PHYSICAL_SOURCE_COUNTS.items()
        ):
            with self.subTest(persona=persona_id):
                self.assertEqual(
                    envelope.profile_file_count(persona_id, "pilot"), pilot_count
                )
                self.assertEqual(
                    envelope.profile_file_count(persona_id, "full"), full_count
                )
                residual_count = full_count - pilot_count
                computed_pilot_shards[persona_id] = (
                    pilot_count + 4_096 - 1
                ) // 4_096
                computed_residual_shards[persona_id] = (
                    residual_count + 4_096 - 1
                ) // 4_096

        self.assertEqual(sum(computed_pilot_shards.values()), 20)
        self.assertEqual(
            computed_residual_shards, EXPECTED_RESIDUAL_SOURCE_INTENT_SHARDS
        )
        self.assertEqual(sum(computed_residual_shards.values()), 53)
        self.assertEqual(
            sum(computed_pilot_shards.values())
            + sum(computed_residual_shards.values()),
            73,
        )
        self.assertEqual(
            sum(pair[0] for pair in PERSONA_W0_PHYSICAL_SOURCE_COUNTS.values()),
            20_300,
        )
        self.assertEqual(
            sum(pair[1] for pair in PERSONA_W0_PHYSICAL_SOURCE_COUNTS.values()),
            203_000,
        )
        layout = source_inventory_layout.build_source_inventory_layout()
        self.assertTrue(
            source_inventory_layout.validate_source_inventory_layout(layout)
        )
        self.assertEqual(
            layout["coverage"]["pilot_source_count"],
            20_300,
        )
        self.assertEqual(
            layout["coverage"]["full_residual_source_count"],
            182_700,
        )
        self.assertEqual(layout["coverage"]["full_source_count"], 203_000)
        self.assertEqual(layout["coverage"]["pilot_shard_count"], 20)
        self.assertEqual(
            layout["coverage"]["full_residual_shard_count"],
            53,
        )
        self.assertEqual(layout["coverage"]["total_shard_count"], 73)
        self.assertIs(
            layout["completion_claims"]["source_intent_inventory_complete"],
            False,
        )
        self.assertTrue(layout["authority"])
        self.assertTrue(
            all(flag is False for flag in layout["authority"].values())
        )
        self.assertEqual(source_intent.REPRESENTATIVE_INTENTS_PER_PERSONA, 1)
        with self.assertRaisesRegex(
            source_intent.PersonaV2SourceIntentError,
            "203,000 source intents",
        ):
            source_intent.require_complete_source_intent_inventory()


if __name__ == "__main__":
    unittest.main()
