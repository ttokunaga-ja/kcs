"""Tests for the persona-PC v2 negative route-review receipt."""

import copy
import os
import subprocess
import sys
import unittest

from eval import persona_v2_route_affinity as route_affinity
from eval import persona_v2_route_review_receipt as receipt


class PersonaV2RouteReviewReceiptTests(unittest.TestCase):
    def setUp(self):
        self.route = route_affinity.build_route_affinity()
        self.value = receipt.build_negative_route_review_receipt(self.route)

    def test_identity_exact_route_binding_hash_size_and_negative_authority(self):
        self.assertEqual(set(self.value), receipt.TOP_LEVEL_FIELDS)
        self.assertEqual(
            (
                self.value["artifact_schema"],
                self.value["artifact_schema_version"],
                self.value["artifact_kind"],
            ),
            (
                "kcs.persona.pc-route-review-receipt/v2",
                2,
                "persona-pc-v2-route-review-receipt",
            ),
        )
        binding = self.value["reviewed_route_artifact"]
        route_raw = route_affinity.canonical_json_bytes(self.route)
        self.assertEqual(
            binding,
            {
                "artifact_kind": route_affinity.ARTIFACT_KIND,
                "artifact_schema": route_affinity.ARTIFACT_SCHEMA,
                "artifact_schema_version": route_affinity.ARTIFACT_SCHEMA_VERSION,
                "canonical_body_bytes": len(route_raw),
                "canonical_body_sha256": route_affinity.route_affinity_sha256(
                    self.route
                ),
            },
        )
        self.assertEqual(binding["canonical_body_bytes"], 70_626)
        self.assertEqual(
            binding["canonical_body_sha256"],
            "e8a401193fc751ed3d7b2a47e3661202835579df8700392ce9fdfd30ad07c790",
        )
        self.assertEqual(set(self.value["authority"]), receipt.AUTHORITY_FIELDS)
        self.assertTrue(
            all(flag is False for flag in self.value["authority"].values())
        )
        self.assertIs(self.value["g0_contract_frozen"], False)
        self.assertIs(
            self.value["route_affinity_matrix_review_receipt_bound"], False
        )
        raw = receipt.canonical_json_bytes(self.value)
        self.assertEqual(len(raw), 3_944)
        self.assertLess(len(raw), receipt.MAX_ROUTE_REVIEW_RECEIPT_BYTES)
        self.assertEqual(
            receipt.route_review_receipt_sha256(self.value, self.route),
            "3c236722b900a26b12a7546b3a073dd71d1c935e1d313cb1261781c75ed4fd98",
        )
        self.assertTrue(
            receipt.validate_negative_route_review_receipt(self.value, self.route)
        )

    def test_checks_violations_and_waivers_are_fully_enumerated(self):
        checks = self.value["checks"]
        self.assertEqual(
            tuple(check["check_id"] for check in checks), receipt.CHECK_ID_ORDER
        )
        self.assertEqual(len(checks), 9)
        self.assertTrue(
            all(
                set(check) == receipt.CHECK_FIELDS
                and check["result"] == "pass"
                for check in checks[:8]
            )
        )
        self.assertEqual(
            checks[-1],
            {
                "check_class": "independent-review-evidence",
                "check_id": "independent-review-evidence-bound",
                "expected": "present-distinct-reasoned-and-hash-bound",
                "observed": "absent",
                "result": "fail",
                "waiver_policy": "not-waivable-by-machine-receipt",
            },
        )
        self.assertEqual(
            self.value["violations"],
            [
                {
                    "check_id": "independent-review-evidence-bound",
                    "disposition": "unwaived",
                    "severity": "blocking",
                    "violation_id": "independent-review-evidence-absent",
                }
            ],
        )
        self.assertEqual(self.value["waivers"], [])
        self.assertEqual(
            self.value["review_summary"],
            {
                "blocking_violation_count": 1,
                "check_count": 9,
                "failed_check_count": 1,
                "independent_review_complete": False,
                "machine_check_count": 8,
                "machine_checks_passed": True,
                "passed_check_count": 8,
                "review_authoritative": False,
                "waiver_count": 0,
            },
        )
        self.assertEqual(
            self.value["authoritative_review_blockers"],
            list(receipt.AUTHORITATIVE_REVIEW_BLOCKERS),
        )

    def test_machine_check_evidence_matches_route_diagnostics(self):
        diagnostics = route_affinity.candidate_review_diagnostics()
        checks = {check["check_id"]: check for check in self.value["checks"]}
        self.assertEqual(
            checks["declared-axis-projection"]["observed"],
            "declared=566;active=541;hard-zero=25;out-of-domain=854;cells=10820",
        )
        diagnostic_to_check = {
            "row_maximum_not_four": "row-maximum-equals-four",
            "maximum_scope_count_out_of_bounds": (
                "maximum-score-scope-count-one-through-eight"
            ),
            "secondary_only_maximum_rows": "no-secondary-only-row-maximum",
            "cross_person_same_variant_vector_clones": (
                "no-cross-person-same-variant-vector-clone"
            ),
            "uncovered_persona_scopes_below_score_two": (
                "all-persona-scopes-covered-by-score-at-least-two"
            ),
        }
        for diagnostic, check_id in diagnostic_to_check.items():
            with self.subTest(check_id=check_id):
                self.assertEqual(diagnostics[diagnostic], [])
                self.assertEqual(checks[check_id]["observed"], "violation-count=0")
                self.assertEqual(checks[check_id]["result"], "pass")

    def test_route_substitution_and_binding_tampering_fail_closed(self):
        invalid_route = copy.deepcopy(self.route)
        invalid_route["rows"][0]["scores_by_scope_ordinal"][0] = 3
        with self.assertRaisesRegex(
            receipt.PersonaV2RouteReviewReceiptError,
            "reviewed route artifact is invalid",
        ):
            receipt.build_negative_route_review_receipt(invalid_route)

        wrong_binding = copy.deepcopy(self.value)
        wrong_binding["reviewed_route_artifact"]["canonical_body_sha256"] = "0" * 64
        with self.assertRaisesRegex(
            receipt.PersonaV2RouteReviewReceiptError, "exact reviewed route artifact"
        ):
            receipt.validate_negative_route_review_receipt(wrong_binding, self.route)

    def test_self_review_identity_is_explicitly_rejected(self):
        self_review = copy.deepcopy(self.value)
        self_review["review_participants"]["independent_reviewer_id"] = (
            self_review["review_participants"]["artifact_producer_id"]
        )
        with self.assertRaisesRegex(
            receipt.PersonaV2RouteReviewReceiptError, "self-review"
        ):
            receipt.validate_negative_route_review_receipt(self_review, self.route)

    def test_positive_authority_and_unverified_review_claims_are_rejected(self):
        mutations = []
        authority = copy.deepcopy(self.value)
        authority["authority"]["review_authoritative"] = True
        mutations.append((authority, "positive authority"))

        summary = copy.deepcopy(self.value)
        summary["review_summary"]["review_authoritative"] = True
        mutations.append((summary, "positive review authority"))

        bound = copy.deepcopy(self.value)
        bound["route_affinity_matrix_review_receipt_bound"] = True
        mutations.append((bound, "cannot mark review evidence bound"))

        claimed = copy.deepcopy(self.value)
        claimed["review_participants"][
            "independent_reviewer_evidence_present"
        ] = True
        mutations.append((claimed, "unvalidated independent review evidence"))

        for candidate, message in mutations:
            with self.subTest(message=message):
                with self.assertRaisesRegex(
                    receipt.PersonaV2RouteReviewReceiptError, message
                ):
                    receipt.validate_negative_route_review_receipt(
                        candidate, self.route
                    )

    def test_check_violation_waiver_and_unknown_field_tampering_fail_closed(self):
        mutations = []
        reordered = copy.deepcopy(self.value)
        reordered["checks"][0], reordered["checks"][1] = (
            reordered["checks"][1],
            reordered["checks"][0],
        )
        mutations.append(reordered)

        hidden_violation = copy.deepcopy(self.value)
        hidden_violation["violations"] = []
        mutations.append(hidden_violation)

        fabricated_waiver = copy.deepcopy(self.value)
        fabricated_waiver["waivers"] = [{"reason": "not independently supplied"}]
        mutations.append(fabricated_waiver)

        unknown = copy.deepcopy(self.value)
        unknown["reviewed_route_artifact"]["path"] = "route.json"
        mutations.append(unknown)

        for candidate in mutations:
            with self.subTest(candidate=candidate):
                with self.assertRaises(receipt.PersonaV2RouteReviewReceiptError):
                    receipt.validate_negative_route_review_receipt(
                        candidate, self.route
                    )

    def test_receipt_is_detached_and_authoritative_boundary_always_fails(self):
        first = receipt.build_negative_route_review_receipt(self.route)
        first["checks"][0]["result"] = "fail"
        second = receipt.build_negative_route_review_receipt(self.route)
        self.assertEqual(second, self.value)
        with self.assertRaisesRegex(
            receipt.PersonaV2RouteReviewReceiptError,
            "independent route review evidence is absent",
        ):
            receipt.require_authoritative_route_review(self.value, self.route)

    def test_hash_is_stable_across_python_hash_seeds(self):
        code = (
            "from eval.persona_v2_route_review_receipt import "
            "route_review_receipt_sha256; print(route_review_receipt_sha256())"
        )
        outputs = []
        for seed in ("1", "777"):
            environment = os.environ.copy()
            environment["PYTHONHASHSEED"] = seed
            outputs.append(
                subprocess.check_output(
                    [sys.executable, "-c", code],
                    cwd=os.path.dirname(os.path.dirname(__file__)),
                    env=environment,
                    text=True,
                ).strip()
            )
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[0], receipt.route_review_receipt_sha256())


if __name__ == "__main__":
    unittest.main()
