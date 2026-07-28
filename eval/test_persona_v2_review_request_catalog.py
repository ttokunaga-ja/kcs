"""Fast gates for the bounded, non-authorizing review-request prerequisite."""

from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import unittest
from unittest import mock

from eval import persona_v2_review_request_catalog as package
from eval import persona_v2_review_request_catalog_validator as independent


EXPECTED_GOLDEN = (
    42_931,
    "3e1231d76aea401931f9a15cc20438918033146d39e50e38ab4c4fd36676efe5",
)
EXPECTED_CLASS_ORDER = (
    "topology-activity",
    "realism-profile",
    "variant-profile",
    "route-human",
    "overlay-reservation",
    "chunk-accounting",
    "semantic-projection-inventory",
)
EXPECTED_SUBJECT_COUNTS = (1, 1, 1, 1, 2, 1, 1)
EXPECTED_BINDING_COUNTS = (1, 1, 1, 1, 2, 1, 1)
EXPECTED_REFERENCED_PROJECTION_COUNTS = (1, 1, 1, 1, 41, 20, 253)
EXPECTED_EXPLICIT_PROJECTION_COUNTS = (1, 1, 1, 1, 41, 20, 0)


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _walk_keys(value):
    if type(value) is dict:
        for key, child in value.items():
            yield key
            yield from _walk_keys(child)
    elif type(value) is list:
        for child in value:
            yield from _walk_keys(child)


class PersonaV2ReviewRequestCatalogContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = package.build_review_request_catalog()
        cls.raw = package.review_request_catalog_bytes()
        # Force the producer-independent expected reconstruction once; later
        # tamper tests use its immutable byte cache and stay fast.
        independent.validate_review_request_catalog(copy.deepcopy(cls.value))

    def test_frozen_golden_and_independent_import_boundary(self):
        self.assertEqual(
            (package.EXPECTED_CATALOG_BYTES, package.EXPECTED_CATALOG_SHA256),
            EXPECTED_GOLDEN,
        )
        self.assertEqual(
            (independent.EXPECTED_CATALOG_BYTES, independent.EXPECTED_CATALOG_SHA256),
            EXPECTED_GOLDEN,
        )
        self.assertEqual((len(self.raw), _sha256(self.raw)), EXPECTED_GOLDEN)
        self.assertIs(type(self.raw), bytes)
        self.assertIs(
            package.validate_review_request_catalog(copy.deepcopy(self.value)), True
        )
        self.assertEqual(package.review_request_catalog_sha256(), EXPECTED_GOLDEN[1])
        self.assertEqual(
            self.value["artifact_schema"],
            "kio.persona.pc-review-request-catalog/v1",
        )
        tree = ast.parse(inspect.getsource(independent))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
                imports.extend(alias.name for alias in node.names)
        self.assertFalse(
            any(
                name.endswith("persona_v2_review_request_catalog")
                and not name.endswith("_validator")
                for name in imports
            ),
            imports,
        )

    def test_exact_request_subject_projection_and_rubric_contract(self):
        requests = self.value["review_requests"]
        self.assertEqual(len(requests), 7)
        self.assertEqual(
            tuple(row["review_class_id"] for row in requests),
            EXPECTED_CLASS_ORDER,
        )
        self.assertEqual(
            tuple(row["request_ordinal"] for row in requests), tuple(range(1, 8))
        )
        self.assertEqual(
            tuple(len(row["subject_pins"]) for row in requests),
            EXPECTED_SUBJECT_COUNTS,
        )
        self.assertEqual(
            tuple(len(row["projection_bindings"]) for row in requests),
            EXPECTED_BINDING_COUNTS,
        )
        self.assertEqual(
            tuple(
                sum(binding["projection_count"] for binding in row["projection_bindings"])
                for row in requests
            ),
            EXPECTED_REFERENCED_PROJECTION_COUNTS,
        )
        self.assertEqual(
            tuple(
                sum(
                    len(binding["ordered_projection_pins"])
                    for binding in row["projection_bindings"]
                )
                for row in requests
            ),
            EXPECTED_EXPLICIT_PROJECTION_COUNTS,
        )
        self.assertEqual(
            sum(EXPECTED_EXPLICIT_PROJECTION_COUNTS),
            self.value["summary"]["explicit_projection_pin_count"],
        )
        for request in requests:
            contract = request["review_contract"]
            self.assertGreaterEqual(len(contract["ordered_check_ids"]), 5)
            self.assertEqual(
                len(contract["ordered_check_ids"]),
                len(set(contract["ordered_check_ids"])),
            )
            self.assertEqual(contract["rubric_version"], 1)
        route = requests[3]
        self.assertEqual(route["required_reviewer_kind"], "independent-human")
        self.assertEqual(
            route["projection_bindings"][0]["mapping_relation"],
            "direct-owner-chain",
        )
        overlay = requests[4]
        self.assertEqual(
            [row["mapping_relation"] for row in overlay["projection_bindings"]],
            ["transitive-consumer-chain", "direct-owner-chain"],
        )
        chunk = requests[5]
        self.assertEqual(
            chunk["projection_bindings"][0]["mapping_relation"],
            "transitive-consumer-chain",
        )
        semantic = requests[6]["projection_bindings"][0]
        self.assertEqual(semantic["projection_count"], 253)
        self.assertEqual(semantic["ordered_projection_pins"], [])
        self.assertEqual(
            semantic["aggregate"]["ordered_projection_pins_sha256"],
            "f524ddcccdd89a216b87d2ad8f98076c8eacabbc258e7b68d514162764a3a97c",
        )

    def test_catalog_is_request_only_and_grants_no_authority(self):
        self.assertTrue(all(value is False for value in self.value["authority"].values()))
        self.assertIs(self.value["g0_contract_frozen"], False)
        completion = self.value["completion_claims"]
        self.assertIs(completion["positive_receipt_bound"], False)
        self.assertIs(completion["reviewer_identity_bound"], False)
        for request in self.value["review_requests"]:
            self.assertIs(request["positive_receipt_bound"], False)
            self.assertEqual(
                request["request_status"], "awaiting-independent-positive-receipt"
            )
            contract = request["review_contract"]
            for field in (
                "approval_bound",
                "review_decision_bound",
                "reviewer_identity_bound",
                "waiver_bound",
            ):
                self.assertIs(contract[field], False)
        public = set(package.__all__)
        self.assertFalse(
            any(token in name.lower() for name in public for token in ("mint", "approve", "waive"))
        )
        all_keys = set(_walk_keys(self.value))
        self.assertNotIn("reviewer_id", all_keys)
        self.assertNotIn("reviewer_principal", all_keys)
        self.assertNotIn("approval_decision", all_keys)

    def test_canonical_bytes_are_immutable_and_builders_are_detached(self):
        first = package.build_review_request_catalog()
        first["authority"]["authorizes_solver"] = True
        first["review_requests"][0]["subject_pins"][0]["sha256"] = "0" * 64
        rebuilt = package.build_review_request_catalog()
        self.assertTrue(all(value is False for value in rebuilt["authority"].values()))
        self.assertNotEqual(
            rebuilt["review_requests"][0]["subject_pins"][0]["sha256"], "0" * 64
        )
        immutable = package.review_request_catalog_bytes()
        with self.assertRaises(TypeError):
            immutable[0] = 0
        self.assertEqual(immutable, self.raw)

    def test_independent_validator_rejects_identity_order_and_authority_tampering(self):
        mutations = []
        value = copy.deepcopy(self.value)
        value["review_requests"][0]["subject_pins"][0]["sha256"] = "0" * 64
        mutations.append(value)
        value = copy.deepcopy(self.value)
        value["review_requests"][4]["projection_bindings"][0][
            "ordered_projection_pins"
        ][0]["canonical_bytes"] += 1
        mutations.append(value)
        value = copy.deepcopy(self.value)
        value["review_requests"][0], value["review_requests"][1] = (
            value["review_requests"][1], value["review_requests"][0]
        )
        mutations.append(value)
        value = copy.deepcopy(self.value)
        value["review_requests"][3]["required_reviewer_kind"] = "machine"
        mutations.append(value)
        value = copy.deepcopy(self.value)
        value["review_requests"][0]["positive_receipt_bound"] = True
        mutations.append(value)
        value = copy.deepcopy(self.value)
        value["authority"]["authorizes_solver"] = True
        mutations.append(value)
        value = copy.deepcopy(self.value)
        del value["review_requests"][6]
        mutations.append(value)
        value = copy.deepcopy(self.value)
        value["review_requests"][0]["review_contract"]["ordered_check_ids"].reverse()
        mutations.append(value)
        for candidate in mutations:
            with self.subTest(candidate=_sha256(package.canonical_json_bytes(candidate))):
                with self.assertRaises(
                    independent.PersonaV2ReviewRequestCatalogValidationError
                ):
                    independent.validate_review_request_catalog(candidate)

    def test_preflight_caps_fail_before_expected_reconstruction(self):
        value = copy.deepcopy(self.value)
        value["review_requests"][0]["request_id"] = "x" * (
            package.MAX_STRING_BYTES + 1
        )
        with self.assertRaises(independent.PersonaV2ReviewRequestCatalogValidationError):
            independent.validate_review_request_catalog(value)
        value = copy.deepcopy(self.value)
        value["review_requests"][4]["projection_bindings"][0][
            "ordered_projection_pins"
        ] = [copy.deepcopy(value["review_requests"][4]["projection_bindings"][0]["ordered_projection_pins"][0])] * 65
        with self.assertRaises(independent.PersonaV2ReviewRequestCatalogValidationError):
            independent.validate_review_request_catalog(value)
        value = copy.deepcopy(self.value)
        value["review_requests"][0]["request_ordinal"] = 2**64
        with self.assertRaises(independent.PersonaV2ReviewRequestCatalogValidationError):
            independent.validate_review_request_catalog(value)

    def test_all_253_registry_rejects_mirrored_valid_total_pin_substitution(self):
        producer_rows = list(package.RELATION_PROJECTION_PINS)
        validator_rows = list(independent.RELATION_PROJECTION_PINS)
        producer_row = producer_rows[0]
        validator_row = validator_rows[0]
        substituted_sha = "f" * 64
        producer_rows[0] = (*producer_row[:3], substituted_sha)
        validator_rows[0] = (*validator_row[:3], substituted_sha)
        package._canonical_catalog_raw.cache_clear()
        independent._expected_catalog_raw.cache_clear()
        with mock.patch.object(
            package, "RELATION_PROJECTION_PINS", tuple(producer_rows)
        ):
            with mock.patch.object(
                independent, "RELATION_PROJECTION_PINS", tuple(validator_rows)
            ):
                # Deliberately remove the catalog golden during this adversarial
                # test: the independent all-253 registry must still reject a
                # mirrored, valid-hex, same-byte-total substitution.
                with mock.patch.object(package, "EXPECTED_CATALOG_BYTES", None):
                    with mock.patch.object(package, "EXPECTED_CATALOG_SHA256", None):
                        candidate = package.build_review_request_catalog()
                with mock.patch.object(independent, "EXPECTED_CATALOG_BYTES", None):
                    with mock.patch.object(
                        independent, "EXPECTED_CATALOG_SHA256", None
                    ):
                        with self.assertRaises(
                            independent.PersonaV2ReviewRequestCatalogValidationError
                        ):
                            independent.validate_review_request_catalog(candidate)
        package._canonical_catalog_raw.cache_clear()
        independent._expected_catalog_raw.cache_clear()

    def test_z_warm_cache_cannot_hide_current_pin_drift(self):
        original_canonical = package.topology.canonical_json_bytes
        package._canonical_catalog_raw.cache_clear()
        package.build_review_request_catalog()
        self.assertEqual(package._canonical_catalog_raw.cache_info().currsize, 1)
        with mock.patch.object(
            package.topology,
            "canonical_json_bytes",
            side_effect=lambda value: original_canonical(value) + b" ",
        ):
            with self.assertRaises(package.PersonaV2ReviewRequestCatalogError):
                package.build_review_request_catalog()
        original_projection_pins = package.global_projection.EXPECTED_PROJECTION_PINS
        drifted_projection_pins = list(original_projection_pins)
        row = drifted_projection_pins[0]
        drifted_projection_pins[0] = (row[0], row[1] + 1, row[2])
        subject_map = {
            pin["subject_id"]: copy.deepcopy(pin)
            for request in self.value["review_requests"]
            for pin in request["subject_pins"]
        }
        with mock.patch.object(package, "_subject_pins", return_value=subject_map):
            with mock.patch.object(
                package.global_projection,
                "EXPECTED_PROJECTION_PINS",
                tuple(drifted_projection_pins),
            ):
                with self.assertRaises(package.PersonaV2ReviewRequestCatalogError):
                    package.build_review_request_catalog()

        self.assertEqual(independent._expected_catalog_raw.cache_info().currsize, 1)
        independent_canonical = independent.topology.canonical_json_bytes
        with mock.patch.object(
            independent.topology,
            "canonical_json_bytes",
            side_effect=lambda value: independent_canonical(value) + b" ",
        ):
            with self.assertRaises(
                independent.PersonaV2ReviewRequestCatalogValidationError
            ):
                independent.validate_review_request_catalog(self.value)

        validator_projection_pins = independent.global_validator.EXPECTED_PROJECTION_PINS
        validator_drift = list(validator_projection_pins)
        row = validator_drift[0]
        validator_drift[0] = (row[0], row[1] + 1, row[2])
        with mock.patch.object(
            independent.global_validator,
            "EXPECTED_PROJECTION_PINS",
            tuple(validator_drift),
        ):
            with self.assertRaises(
                independent.PersonaV2ReviewRequestCatalogValidationError
            ):
                independent.validate_review_request_catalog(self.value)
        package._canonical_catalog_raw.cache_clear()


if __name__ == "__main__":
    unittest.main()
