import copy
import unittest

from eval import persona_v2_artifact_common as artifact_common
from eval import persona_v2_contract as envelope
from eval import persona_v2_overlay_reservation_layout as reservation
from eval import persona_v2_overlay_reservation_validator as independent_validator


EXPECTED_SUITE_BYTES = 21_680
EXPECTED_SUITE_SHA256 = (
    "0423ed61ea7b39dd5229e2ad6f972fc12055717ad401ee9b74911dd5696f15a4"
)
EXPECTED_P01_PILOT = (
    206_597,
    "e6eca603623c57fc527f6b6b24d689683e0a099dece907844c42c8805ed28618",
)
EXPECTED_P01_RESIDUAL = (
    1_742_353,
    "d2a38cf02dfe4004da4aed457e2e85f17fd3cadd31efde0d3092a4d0bf256001",
)
EXPECTED_MAXIMUM_ORIGIN = (
    "p12",
    "full-residual",
    2_639_467,
    "82a8ca231a7202f20076da7c57df8dcc2ba495815f9710658758ca088306a557",
)
EXPECTED_HOST_HISTOGRAMS = {
    "pilot": {"0": 636, "1": 137, "2": 59, "3": 40, "4": 26, "5": 18},
    "full-minus-pilot": {
        "0": 5_717,
        "1": 1_233,
        "2": 531,
        "3": 360,
        "4": 234,
        "5": 162,
    },
    "full": {
        "0": 6_353,
        "1": 1_370,
        "2": 590,
        "3": 400,
        "4": 260,
        "5": 180,
    },
}
EXPECTED_RELATION_PLACEMENT = {
    "pilot": {
        "exact-duplicate": {
            "primary-to-primary": 221,
            "primary-to-secondary": 162,
            "secondary-to-primary": 80,
            "secondary-to-secondary": 45,
        },
        "near-revision": {
            "primary-to-primary": 582,
            "primary-to-secondary": 416,
            "secondary-to-primary": 204,
            "secondary-to-secondary": 121,
        },
        "conflict-copy": {
            "primary-to-primary": 65,
            "primary-to-secondary": 50,
            "secondary-to-primary": 25,
            "secondary-to-secondary": 16,
        },
    },
    "full-minus-pilot": {
        "exact-duplicate": {
            "primary-to-primary": 1_963,
            "primary-to-secondary": 1_463,
            "secondary-to-primary": 716,
            "secondary-to-secondary": 430,
        },
        "near-revision": {
            "primary-to-primary": 5_243,
            "primary-to-secondary": 3_747,
            "secondary-to-primary": 1_843,
            "secondary-to-secondary": 1_074,
        },
        "conflict-copy": {
            "primary-to-primary": 594,
            "primary-to-secondary": 450,
            "secondary-to-primary": 227,
            "secondary-to-secondary": 133,
        },
    },
}


def _relation_rows(value, relation_kind=None):
    rows = [
        row
        for row in value["reservation_rows"]
        if row["row_kind"] == "content-relation-reservation"
    ]
    if relation_kind is not None:
        rows = [row for row in rows if row["relation_kind"] == relation_kind]
    return rows


def _attachment_rows(value):
    return [
        row
        for row in value["reservation_rows"]
        if row["row_kind"] == "attachment-membership-reservation"
    ]


class PersonaV2OverlayReservationLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.origins = reservation.build_overlay_reservation_origin_suite()
        cls.by_key = {
            (value["persona_id"], value["origin"]): value
            for value in cls.origins
        }
        cls.suite = reservation.build_overlay_reservation_suite()

    def test_exact_pins_order_caps_and_negative_authority(self):
        self.assertEqual(len(self.origins), 40)
        self.assertEqual(
            [(value["persona_id"], value["origin"]) for value in self.origins],
            [
                (persona_id, origin)
                for persona_id in envelope.PERSONA_IDS
                for origin in reservation.ORIGIN_ORDER
            ],
        )
        suite_raw = reservation.overlay_reservation_suite_bytes(self.suite)
        self.assertEqual(len(suite_raw), EXPECTED_SUITE_BYTES)
        self.assertEqual(
            reservation.overlay_reservation_suite_sha256(self.suite),
            EXPECTED_SUITE_SHA256,
        )
        self.assertTrue(reservation.validate_overlay_reservation_suite(self.suite))
        self.assertLessEqual(len(suite_raw), reservation.MAX_SUITE_ARTIFACT_BYTES)

        expected_pins = {
            ("p01", "pilot"): EXPECTED_P01_PILOT,
            ("p01", "full-residual"): EXPECTED_P01_RESIDUAL,
            EXPECTED_MAXIMUM_ORIGIN[:2]: EXPECTED_MAXIMUM_ORIGIN[2:],
        }
        for value in self.origins:
            key = (value["persona_id"], value["origin"])
            raw = reservation.canonical_json_bytes(value)
            self.assertLessEqual(len(raw), reservation.MAX_ORIGIN_ARTIFACT_BYTES)
            self.assertLessEqual(
                value["summary"]["reservation_row_count"],
                reservation.MAX_ROWS_PER_ORIGIN,
            )
            self.assertLessEqual(
                value["summary"]["maximum_row_bytes_including_lf"],
                reservation.MAX_RESERVATION_ROW_BYTES,
            )
            self.assertEqual(set(value["authority"]), reservation.AUTHORITY_FIELDS)
            self.assertTrue(all(flag is False for flag in value["authority"].values()))
            self.assertFalse(value["g0_contract_frozen"])
            if key in expected_pins:
                expected_bytes, expected_sha = expected_pins[key]
                self.assertEqual(len(raw), expected_bytes)
                self.assertEqual(
                    reservation.overlay_reservation_origin_sha256(*key, value),
                    expected_sha,
                )

        self.assertEqual(
            self.suite["suite_summary"]["maximum_origin_canonical_bytes"],
            EXPECTED_MAXIMUM_ORIGIN[2],
        )
        self.assertEqual(
            self.suite["suite_summary"]["maximum_row_bytes_including_lf"], 1_960
        )

    def test_exact_suite_rows_host_histograms_and_joint_marginals(self):
        summary = self.suite["suite_summary"]
        self.assertEqual(
            summary["eml_attachment_fanout_histograms"],
            EXPECTED_HOST_HISTOGRAMS,
        )
        totals = summary["origin_totals"]
        self.assertEqual(totals["pilot"]["reservation_row_count"], 2_556)
        self.assertEqual(
            totals["full-minus-pilot"]["reservation_row_count"], 23_004
        )
        self.assertEqual(totals["full"]["reservation_row_count"], 25_560)
        self.assertEqual(totals["pilot"]["semantic_anchor_slot_count"], 2_100)
        self.assertEqual(
            totals["full-minus-pilot"]["semantic_anchor_slot_count"], 0
        )
        self.assertEqual(totals["full"]["source_origin_intent_count"], 203_000)
        self.assertEqual(
            totals["full"]["overlay_referenced_unique_source_intent_count"],
            46_840,
        )
        actual_joint = summary["relation_placement_joint_marginals"]
        for profile in ("pilot", "full-minus-pilot"):
            self.assertEqual(actual_joint[profile], EXPECTED_RELATION_PLACEMENT[profile])
        for relation in reservation.RELATION_ORDER:
            for placement in reservation.PLACEMENT_ORDER:
                self.assertEqual(
                    actual_joint["full"][relation][placement],
                    actual_joint["pilot"][relation][placement]
                    + actual_joint["full-minus-pilot"][relation][placement],
                )

    def test_semantic_anchor_and_variant_usage_reservations_are_exact(self):
        for value in self.origins:
            with self.subTest(persona=value["persona_id"], origin=value["origin"]):
                expected_anchor_count = 105 if value["origin"] == "pilot" else 0
                anchors = value["semantic_anchor_slots"]
                self.assertEqual(len(anchors), expected_anchor_count)
                self.assertTrue(
                    all(row["gate_role"] == "contract_contributor" for row in anchors)
                )
                overlay_keys = set()
                for row in _relation_rows(value):
                    overlay_keys.update(
                        (row["anchor_intent_key"], row["derivative_intent_key"])
                    )
                for row in _attachment_rows(value):
                    overlay_keys.update(
                        (row["host_intent_key"], row["standalone_member_intent_key"])
                    )
                anchor_keys = {row["intent_key"] for row in anchors}
                self.assertEqual(len(anchor_keys), expected_anchor_count)
                self.assertTrue(anchor_keys.isdisjoint(overlay_keys))

                usage = value["variant_usage_marginals"]
                self.assertEqual(
                    sum(row["source_intent_count"] for row in usage),
                    value["summary"]["source_origin_intent_count"],
                )
                for row in usage:
                    self.assertEqual(
                        row["unique_reserved_source_intent_count"]
                        + row["unreserved_source_intent_count"],
                        row["source_intent_count"],
                    )
                eml = next(row for row in usage if row["variant_id"] == "eml")
                histogram = value["summary"]["eml_attachment_fanout_histogram"]
                self.assertEqual(histogram["0"], eml["unreserved_source_intent_count"])
                self.assertEqual(
                    sum(histogram[str(cardinality)] for cardinality in range(1, 6)),
                    value["summary"]["attachment_host_intent_count"],
                )
                self.assertEqual(
                    sum(
                        cardinality * histogram[str(cardinality)]
                        for cardinality in range(1, 6)
                    ),
                    value["summary"]["attachment_membership_row_count"],
                )

    def test_relation_attachment_identity_and_conflict_reuse_are_exact(self):
        for value in self.origins:
            relation_rows = _relation_rows(value)
            attachment_rows = _attachment_rows(value)
            relation_by_cluster = {row["cluster_key"]: row for row in relation_rows}
            endpoint_keys = {
                key
                for row in relation_rows
                for key in (row["anchor_intent_key"], row["derivative_intent_key"])
            }
            self.assertEqual(len(endpoint_keys), 2 * len(relation_rows))
            for row in relation_rows:
                self.assertEqual(
                    row["endpoint_gate_role"] in {
                        "contract_contributor",
                        "incidental_searchable",
                    },
                    True,
                )
                self.assertNotEqual(row["endpoint_variant_id"], "eml")
                anchor = row["anchor_identity"]
                derivative = row["derivative_identity"]
                self.assertEqual(
                    anchor["logical_document_key"],
                    derivative["logical_document_key"],
                )
                self.assertEqual(
                    anchor["semantic_section_key"], derivative["semantic_section_key"]
                )
                if row["relation_kind"] == "exact-duplicate":
                    self.assertEqual(anchor, derivative)
                elif row["relation_kind"] == "near-revision":
                    self.assertEqual(
                        anchor["logical_branch_key"], derivative["logical_branch_key"]
                    )
                    self.assertNotEqual(
                        anchor["logical_revision_key"],
                        derivative["logical_revision_key"],
                    )
                else:
                    self.assertNotEqual(
                        anchor["logical_branch_key"], derivative["logical_branch_key"]
                    )
                    binding = row["conflict_fact_binding"]
                    branch_a = set(binding["branch_a_present_fact_ids"])
                    branch_b = set(binding["branch_b_present_fact_ids"])
                    pair = set(binding["unordered_member_fact_ids"])
                    self.assertEqual(len(branch_a), 7)
                    self.assertEqual(len(branch_b), 7)
                    self.assertEqual(len(branch_a | branch_b), 8)
                    self.assertEqual(len(branch_a & branch_b), 6)
                    self.assertEqual(branch_a ^ branch_b, pair)

            overlap_rows = [
                row
                for row in attachment_rows
                if row["content_relation_membership"] != "none"
            ]
            self.assertEqual(
                len(overlap_rows),
                value["target_marginals"][
                    "attachment_exact_duplicate_overlap_count"
                ],
            )
            host_ordinals = {}
            member_keys = set()
            for row in attachment_rows:
                self.assertEqual(row["host_variant_id"], "eml")
                self.assertEqual(row["host_gate_role"], "incidental_searchable")
                self.assertNotEqual(row["standalone_member_variant_id"], "eml")
                self.assertNotIn(row["standalone_member_intent_key"], member_keys)
                member_keys.add(row["standalone_member_intent_key"])
                host_ordinals.setdefault(row["host_intent_key"], []).append(
                    row["member_ordinal"]
                )
                self.assertEqual(
                    row["decoded_payload_equivalence_key"],
                    row["standalone_member_identity"]["payload_equivalence_key"],
                )
                self.assertNotEqual(
                    row["host_identity"]["logical_document_key"],
                    row["standalone_member_identity"]["logical_document_key"],
                )
                cluster_key = row["content_relation_membership"]
                if cluster_key != "none":
                    cluster = relation_by_cluster[cluster_key]
                    self.assertEqual(cluster["relation_kind"], "exact-duplicate")
                    self.assertEqual(
                        row["standalone_member_intent_key"],
                        cluster["derivative_intent_key"],
                    )
                    self.assertEqual(
                        row["standalone_member_identity"],
                        cluster["derivative_identity"],
                    )
                else:
                    self.assertNotIn(row["standalone_member_intent_key"], endpoint_keys)
            for ordinals in host_ordinals.values():
                self.assertEqual(ordinals, list(range(1, len(ordinals) + 1)))
                self.assertLessEqual(len(ordinals), 5)

            conflicts = _relation_rows(value, "conflict-copy")
            pilot_conflicts = self.by_key[(value["persona_id"], "pilot")][
                "target_marginals"
            ]["conflict_copy_cluster_count"]
            for ordinal, row in enumerate(conflicts, start=1):
                global_ordinal = (
                    ordinal
                    if value["origin"] == "pilot"
                    else pilot_conflicts + ordinal
                )
                binding = row["conflict_fact_binding"]
                self.assertEqual(
                    binding["template_key"],
                    value["conflict_fact_templates"][(global_ordinal - 1) % 4][
                        "template_key"
                    ],
                )
                self.assertEqual(
                    binding["fact_template_reuse_ordinal"],
                    (global_ordinal - 1) // 4 + 1,
                )

    def test_independent_validator_covers_all_origins_and_suite(self):
        for key in (("p01", "pilot"), ("p12", "full-residual")):
            self.assertTrue(
                independent_validator.validate_overlay_reservation_origin(
                    self.by_key[key]
                )
            )
        self.assertTrue(
            independent_validator.validate_overlay_reservation_suite(
                self.suite, self.origins
            )
        )

    def test_tamper_injection_and_detachment_fail_closed(self):
        base = self.by_key[("p01", "pilot")]
        mutations = []

        tampered = copy.deepcopy(base)
        tampered["semantic_anchor_slots"][0]["gate_role"] = "raw_only"
        mutations.append(tampered)

        tampered = copy.deepcopy(base)
        tampered["reservation_rows"][0]["derivative_intent_key"] = tampered[
            "reservation_rows"
        ][0]["anchor_intent_key"]
        mutations.append(tampered)

        tampered = copy.deepcopy(base)
        attachment = _attachment_rows(tampered)[0]
        attachment["member_ordinal"] = 2
        mutations.append(tampered)

        tampered = copy.deepcopy(base)
        conflict = _relation_rows(tampered, "conflict-copy")[0]
        conflict["conflict_fact_binding"]["branch_a_present_fact_ids"] = list(
            conflict["conflict_fact_binding"]["branch_b_present_fact_ids"]
        )
        mutations.append(tampered)

        tampered = copy.deepcopy(base)
        tampered["reservation_rows"][0]["solved_scope_key"] = "scope-forbidden"
        mutations.append(tampered)

        tampered = copy.deepcopy(base)
        matrix = tampered["relation_placement_joint_marginals"]
        matrix["exact-duplicate"]["primary-to-primary"] -= 1
        matrix["exact-duplicate"]["primary-to-secondary"] += 1
        matrix["near-revision"]["primary-to-primary"] += 1
        matrix["near-revision"]["primary-to-secondary"] -= 1
        mutations.append(tampered)

        for index, value in enumerate(mutations):
            with self.subTest(mutation=index):
                with self.assertRaises(
                    reservation.PersonaV2OverlayReservationError
                ):
                    reservation.validate_overlay_reservation_origin(
                        "p01", "pilot", value
                    )
                with self.assertRaises(
                    independent_validator.PersonaV2OverlayReservationValidationError
                ):
                    independent_validator.validate_overlay_reservation_origin(value)

        first = reservation.build_overlay_reservation_origin("p01", "pilot")
        first["reservation_rows"][0]["cluster_key"] = "poisoned"
        self.assertNotEqual(
            reservation.build_overlay_reservation_origin("p01", "pilot")[
                "reservation_rows"
            ][0]["cluster_key"],
            "poisoned",
        )
        with self.assertRaises(reservation.PersonaV2OverlayReservationError):
            reservation.require_concrete_overlay_membership()

    def test_every_row_is_bounded_canonical_json_plus_lf(self):
        for value in self.origins:
            for row in value["reservation_rows"]:
                raw = artifact_common.canonical_json_bytes(
                    row,
                    label="reservation test row",
                    max_bytes=reservation.MAX_RESERVATION_ROW_BYTES - 1,
                )
                self.assertLessEqual(
                    len(raw) + 1, reservation.MAX_RESERVATION_ROW_BYTES
                )


if __name__ == "__main__":
    unittest.main()
