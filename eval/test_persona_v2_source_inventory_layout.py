import copy
import os
import subprocess
import sys
import unittest

from eval import persona_v2_contract as envelope
from eval import persona_v2_source_inventory_layout as layout
from eval import persona_v2_source_intent as source_intent


LITERAL_PERSONA_COUNTS = {
    "p01": (1_200, 12_000, (4_096, 4_096, 2_608)),
    "p02": (1_500, 15_000, (4_096, 4_096, 4_096, 1_212)),
    "p03": (1_000, 10_000, (4_096, 4_096, 808)),
    "p04": (1_000, 10_000, (4_096, 4_096, 808)),
    "p05": (1_200, 12_000, (4_096, 4_096, 2_608)),
    "p06": (800, 8_000, (4_096, 3_104)),
    "p07": (700, 7_000, (4_096, 2_204)),
    "p08": (800, 8_000, (4_096, 3_104)),
    "p09": (900, 9_000, (4_096, 4_004)),
    "p10": (1_100, 11_000, (4_096, 4_096, 1_708)),
    "p11": (1_000, 10_000, (4_096, 4_096, 808)),
    "p12": (1_600, 16_000, (4_096, 4_096, 4_096, 2_112)),
    "p13": (700, 7_000, (4_096, 2_204)),
    "p14": (1_300, 13_000, (4_096, 4_096, 3_508)),
    "p15": (800, 8_000, (4_096, 3_104)),
    "p16": (800, 8_000, (4_096, 3_104)),
    "p17": (800, 8_000, (4_096, 3_104)),
    "p18": (1_200, 12_000, (4_096, 4_096, 2_608)),
    "p19": (900, 9_000, (4_096, 4_004)),
    "p20": (1_000, 10_000, (4_096, 4_096, 808)),
}

LITERAL_SUITE_GATE_ROLE_COUNTS = {
    "full": {
        "contract_contributor": 69_236,
        "incidental_searchable": 60_414,
        "raw_only": 73_350,
    },
    "full-residual": {
        "contract_contributor": 62_311,
        "incidental_searchable": 54_374,
        "raw_only": 66_015,
    },
    "pilot": {
        "contract_contributor": 6_925,
        "incidental_searchable": 6_040,
        "raw_only": 7_335,
    },
}


class PersonaV2SourceInventoryLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = layout.build_source_inventory_layout()

    def test_exact_canonical_pin_and_negative_authority(self):
        raw = layout.canonical_json_bytes(self.value)
        self.assertEqual(len(raw), 274_566)
        self.assertEqual(
            layout.source_inventory_layout_sha256(self.value),
            "81fcec92df932d9357b5202a6eda3f6c11ac9bd70762a281cbc2d094d6e8579a",
        )
        self.assertTrue(layout.validate_source_inventory_layout(self.value))
        self.assertLessEqual(len(raw), layout.MAX_LAYOUT_BYTES)
        self.assertEqual(set(self.value["authority"]), layout.AUTHORITY_FIELDS)
        self.assertTrue(
            all(flag is False for flag in self.value["authority"].values())
        )
        self.assertFalse(self.value["g0_contract_frozen"])
        claims = self.value["completion_claims"]
        self.assertTrue(claims["source_inventory_layout_complete"])
        self.assertTrue(claims["exact_key_range_partition_complete"])
        self.assertFalse(claims["source_intent_inventory_complete"])
        self.assertFalse(claims["all_source_intent_rows_materialized"])
        self.assertFalse(claims["body_bytes_and_sha_bound"])

    def test_literal_persona_counts_and_exact_shard_splits(self):
        self.assertEqual(tuple(LITERAL_PERSONA_COUNTS), envelope.PERSONA_IDS)
        personas = {
            row["persona_id"]: row for row in self.value["personas"]
        }
        self.assertEqual(tuple(personas), envelope.PERSONA_IDS)
        for persona_id, (pilot, full, residual_split) in (
            LITERAL_PERSONA_COUNTS.items()
        ):
            with self.subTest(persona=persona_id):
                row = personas[persona_id]
                self.assertEqual(row["pilot_source_count"], pilot)
                self.assertEqual(row["full_source_count"], full)
                self.assertEqual(row["full_residual_source_count"], full - pilot)
                pilot_shards = [
                    shard
                    for shard in row["shards"]
                    if shard["origin"] == "pilot"
                ]
                residual_shards = [
                    shard
                    for shard in row["shards"]
                    if shard["origin"] == "full-residual"
                ]
                self.assertEqual([shard["row_count"] for shard in pilot_shards], [pilot])
                self.assertEqual(
                    tuple(shard["row_count"] for shard in residual_shards),
                    residual_split,
                )
                self.assertEqual(sum(residual_split), full - pilot)
                for origin, shards, expected_count in (
                    ("pilot", pilot_shards, pilot),
                    ("full-residual", residual_shards, full - pilot),
                ):
                    expected_next = 1
                    for shard_ordinal, shard in enumerate(shards, start=1):
                        self.assertEqual(shard["shard_ordinal"], shard_ordinal)
                        self.assertEqual(
                            shard["first_origin_ordinal"], expected_next
                        )
                        self.assertEqual(
                            shard["last_origin_ordinal"],
                            expected_next + shard["row_count"] - 1,
                        )
                        self.assertEqual(
                            shard["first_intent_key"],
                            layout.intent_key(persona_id, origin, expected_next),
                        )
                        self.assertEqual(
                            shard["last_intent_key"],
                            layout.intent_key(
                                persona_id,
                                origin,
                                shard["last_origin_ordinal"],
                            ),
                        )
                        expected_next = shard["last_origin_ordinal"] + 1
                    self.assertEqual(expected_next - 1, expected_count)

        coverage = self.value["coverage"]
        self.assertEqual(coverage["persona_count"], 20)
        self.assertEqual(coverage["pilot_source_count"], 20_300)
        self.assertEqual(coverage["full_residual_source_count"], 182_700)
        self.assertEqual(coverage["full_source_count"], 203_000)
        self.assertEqual(coverage["pilot_shard_count"], 20)
        self.assertEqual(coverage["full_residual_shard_count"], 53)
        self.assertEqual(coverage["total_shard_count"], 73)

    def test_variant_reservations_cover_every_key_without_assigning_profiles(self):
        coverage = self.value["coverage"]
        self.assertEqual(coverage["variant_identity_count"], 71)
        self.assertEqual(coverage["declared_persona_variant_row_count"], 566)
        self.assertEqual(
            coverage["declared_hard_zero_persona_variant_row_count"], 25
        )
        self.assertEqual(coverage["pilot_variant_reservation_count"], 541)
        self.assertEqual(
            coverage["full_residual_variant_reservation_count"], 541
        )
        for person in self.value["personas"]:
            for origin in layout.ORIGIN_ORDER:
                reservations = person["variant_reservations"][origin]
                self.assertTrue(reservations)
                self.assertEqual(reservations[0]["first_origin_ordinal"], 1)
                expected_next = 1
                for reservation in reservations:
                    self.assertEqual(
                        reservation["first_origin_ordinal"], expected_next
                    )
                    self.assertEqual(
                        reservation["first_intent_key"],
                        layout.intent_key(
                            person["persona_id"], origin, expected_next
                        ),
                    )
                    expected_next = reservation["last_origin_ordinal"] + 1
                    self.assertEqual(
                        reservation["last_intent_key"],
                        layout.intent_key(
                            person["persona_id"],
                            origin,
                            reservation["last_origin_ordinal"],
                        ),
                    )
                    self.assertEqual(
                        reservation["row_count"],
                        reservation["last_origin_ordinal"]
                        - reservation["first_origin_ordinal"]
                        + 1,
                    )
                    self.assertNotIn("source_profile_id", reservation)
                    self.assertNotIn("renderer_id", reservation)
                    self.assertNotIn("target_bytes", reservation)
                expected_count = (
                    person["pilot_source_count"]
                    if origin == "pilot"
                    else person["full_residual_source_count"]
                )
                self.assertEqual(expected_next - 1, expected_count)

    def test_gate_roles_and_pilot_plus_residual_are_exact(self):
        self.assertEqual(
            self.value["suite_gate_role_source_counts"],
            LITERAL_SUITE_GATE_ROLE_COUNTS,
        )
        for person in self.value["personas"]:
            counts = person["gate_role_source_counts"]
            self.assertEqual(sum(counts["pilot"].values()), person["pilot_source_count"])
            self.assertEqual(
                sum(counts["full-residual"].values()),
                person["full_residual_source_count"],
            )
            self.assertEqual(sum(counts["full"].values()), person["full_source_count"])
            for role in layout.GATE_ROLE_ORDER:
                self.assertEqual(
                    counts["pilot"][role] + counts["full-residual"][role],
                    counts["full"][role],
                )

    def test_key_grammar_bounds_and_representative_pilot_compatibility(self):
        self.assertEqual(
            layout.intent_key("p01", "pilot", 1),
            "p01-intent-pilot-syn-0001",
        )
        self.assertEqual(
            layout.intent_key("p12", "pilot", 1_600),
            "p12-intent-pilot-syn-1600",
        )
        self.assertEqual(
            layout.intent_key("p12", "full-residual", 14_400),
            "p12-intent-full-residual-syn-14400",
        )
        invalid = (
            ("p00", "pilot", 1),
            ("p01", "full-minus-pilot", 1),
            ("p01", "pilot", True),
            ("p01", "pilot", 0),
            ("p01", "pilot", 1_201),
            ("p12", "full-residual", 14_401),
        )
        for arguments in invalid:
            with self.subTest(arguments=arguments):
                with self.assertRaises(
                    layout.PersonaV2SourceInventoryLayoutError
                ):
                    layout.intent_key(*arguments)

        representatives = source_intent.build_source_intent_origin_shard_suite()
        self.assertEqual(
            [value["persona_id"] for value in representatives],
            list(envelope.PERSONA_IDS),
        )
        for value in representatives:
            self.assertEqual(
                value["intent_rows"][0]["intent_key"],
                layout.intent_key(value["persona_id"], "pilot", 1),
            )

    def test_full_manifest_reuses_pilot_reference_and_layout_has_no_body_pin(self):
        all_shard_ids = set()
        for person in self.value["personas"]:
            pilot_ids = person["expected_pilot_manifest_shard_ids"]
            full_ids = person["expected_full_manifest_shard_ids"]
            self.assertEqual(len(pilot_ids), 1)
            self.assertEqual(full_ids[: len(pilot_ids)], pilot_ids)
            self.assertEqual(full_ids, [row["shard_id"] for row in person["shards"]])
            for shard in person["shards"]:
                self.assertNotIn(shard["shard_id"], all_shard_ids)
                all_shard_ids.add(shard["shard_id"])
                self.assertNotIn("body_bytes", shard)
                self.assertNotIn("body_sha256", shard)
        self.assertEqual(len(all_shard_ids), 73)

    def test_gap_overlap_reorder_foreign_and_completion_mutations_fail_closed(self):
        mutations = (
            lambda value: value["coverage"].__setitem__("full_source_count", 202_999),
            lambda value: value["personas"].pop(),
            lambda value: value["personas"][0]["shards"][1].__setitem__(
                "first_origin_ordinal", 2
            ),
            lambda value: value["personas"][0]["shards"][1].__setitem__(
                "row_count", 4_095
            ),
            lambda value: value["personas"][0]["shards"][1].__setitem__(
                "persona_id", "p02"
            ),
            lambda value: value["personas"][0]["shards"].reverse(),
            lambda value: value["personas"][0][
                "expected_full_manifest_shard_ids"
            ].pop(0),
            lambda value: value["personas"][0]["variant_reservations"][
                "pilot"
            ][0].__setitem__("variant_id", "forged"),
            lambda value: value["personas"][0]["declared_hard_zero_variant_ids"].append(
                "forged"
            ),
            lambda value: value["authority"].__setitem__(
                "authorizes_source_inventory", True
            ),
            lambda value: value["completion_claims"].__setitem__(
                "source_intent_inventory_complete", True
            ),
            lambda value: value["personas"][0]["shards"][0].__setitem__(
                "body_sha256", "0" * 64
            ),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                candidate = copy.deepcopy(self.value)
                mutate(candidate)
                with self.assertRaises(
                    layout.PersonaV2SourceInventoryLayoutError
                ):
                    layout.validate_source_inventory_layout(candidate)

    def test_detachment_determinism_and_materialization_guard(self):
        first = layout.build_source_inventory_layout()
        second = layout.build_source_inventory_layout()
        first["personas"][0]["shards"][0]["row_count"] = 1
        self.assertNotEqual(first, second)
        self.assertEqual(second, layout.build_source_inventory_layout())

        script = (
            "from eval import persona_v2_source_inventory_layout as x; "
            "v=x.build_source_inventory_layout(); "
            "print(len(x.canonical_json_bytes(v)),x.source_inventory_layout_sha256(v))"
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

        with self.assertRaisesRegex(
            layout.PersonaV2SourceInventoryLayoutError,
            "203,000-key/73-shard layout is complete",
        ):
            layout.require_materialized_source_inventory()


if __name__ == "__main__":
    unittest.main()
