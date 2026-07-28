from __future__ import annotations

import ast
import collections
import copy
import hashlib
import inspect
import json
import os
import pathlib
import resource
import subprocess
import sys
import time
import unittest
from unittest import mock

from eval import persona_v2_artifact_common as artifact_common
from eval import persona_v2_corpus_semantic_namespace_v3 as package
from eval import persona_v2_corpus_semantic_namespace_v3_validator as independent
from eval import persona_v2_semantic_projection_complete_inventory as complete


def _coordinates(class_id, local_ordinal):
    if class_id in {
        "topology-path-load",
        "realism-locale-security",
        "route-scores",
        "payload-equivalence-rules",
    }:
        return {}
    if class_id in {
        "primary-use-case-corpus-half",
        "recipe-content-filename-policy",
    }:
        return {"scope": "suite"}
    if class_id in {
        "fact-graph",
        "effective-source-membership",
        "query-independent-lifecycle-fact-rendition-rules",
    }:
        return {"persona_id": package.PERSONA_IDS[local_ordinal - 1]}
    if class_id == "concrete-overlay-relations":
        index = local_ordinal - 1
        return {
            "origin": package.ORIGIN_ORDER[index % 2],
            "persona_id": package.PERSONA_IDS[index // 2],
        }
    if class_id == "source-instance-parameters" and local_ordinal == 1:
        return {"parameter_catalog_id": "global-source-parameter-cells-v1"}
    index = local_ordinal - (2 if class_id == "source-instance-parameters" else 1)
    persona_id = package.PERSONA_IDS[index % 20]
    origin = package.ORIGIN_ORDER[(index // 20) % 2]
    shard_ordinal = index // 40 + 1
    return {
        "origin": origin,
        "persona_id": persona_id,
        "source_shard_id": f"{persona_id}-{origin}-shard-{shard_ordinal:03d}",
        "source_shard_ordinal": shard_ordinal,
    }


def _synthetic_receipts(*, complete_shape=False):
    classes = [
        class_id
        for class_id in package.PROJECTION_CLASS_ORDER
        for _ in range(package.EXPECTED_ENTRY_COUNTS[class_id])
    ]
    class_seen = {class_id: 0 for class_id in package.PROJECTION_CLASS_ORDER}
    framings = []
    coordinates = []
    for class_id in classes:
        class_seen[class_id] += 1
        coordinate = _coordinates(class_id, class_seen[class_id])
        coordinates.append(coordinate)
        framings.append(package._expected_framing(class_id, coordinate))
    assert framings.count("canonical-json") == 67
    assert framings.count("canonical-jsonl-lf") == 186

    sizes = []
    jsonl_seen = 0
    for framing in framings:
        if framing == "canonical-json":
            sizes.append(300_000)
        else:
            jsonl_seen += 1
            sizes.append(729_000 if jsonl_seen < 186 else 776_469)
    assert sum(sizes) == package.EXPECTED_CUMULATIVE_EXTERNAL_PROJECTION_BYTES

    receipts = []
    for ordinal, (class_id, coordinate, framing, size) in enumerate(
        zip(classes, coordinates, framings, sizes, strict=True), start=1
    ):
        kind, schema = package._expected_projection_identity(class_id, coordinate)
        pin = {
            "artifact_kind": kind,
            "artifact_schema": schema,
            "artifact_schema_version": 1,
            "body_framing": framing,
            "canonical_bytes": size,
            "sha256": hashlib.sha256(f"synthetic-body-{ordinal}".encode()).hexdigest(),
        }
        receipt = {
            "coordinates": coordinate,
            "projection_class_id": class_id,
            "projection_pin": pin,
        }
        if complete_shape:
            owner_digest = hashlib.sha256(
                f"synthetic-owner-{ordinal}".encode()
            ).hexdigest()
            direct_digest = hashlib.sha256(
                f"synthetic-direct-{ordinal}".encode()
            ).hexdigest()
            receipt.update(
                {
                    "direct_body_pins": [
                        {
                            "body_framing": "canonical-json",
                            "canonical_bytes": 1,
                            "direct_pin_id": f"direct-{ordinal}",
                            "direct_pin_role": "synthetic-direct",
                            "sha256": direct_digest,
                        }
                    ],
                    "full_owner_pins": [
                        {
                            "artifact_kind": "synthetic-owner",
                            "artifact_schema": "kio.synthetic.owner/v1",
                            "artifact_schema_version": 1,
                            "body_framing": "canonical-json",
                            "canonical_bytes": 1,
                            "coordinates": {},
                            "owner_id": f"owner-{ordinal}",
                            "owner_role": "synthetic-owner",
                            "sha256": owner_digest,
                        }
                    ],
                    "projector": {
                        "projector_id": f"projector-{ordinal}",
                        "projector_version": 1,
                    },
                    "receipt_id": f"receipt-{ordinal}",
                    "row_kind": "semantic-projection-derivation-receipt",
                    "row_schema": (
                        "kio.persona.pc-semantic-projection-derivation-receipt/v2"
                    ),
                    "validation": {
                        "independent_derivation_validation_required": True,
                        "projection_pin_matches_external_body": True,
                        "upstream_owner_validation_result": True,
                        "upstream_projection_validation_result": True,
                    },
                }
            )
        receipts.append(receipt)
    return receipts


def _synthetic_complete_inventory():
    return {
        "artifact_kind": independent.COMPLETE_INVENTORY_KIND,
        "artifact_schema": independent.COMPLETE_INVENTORY_SCHEMA,
        "artifact_schema_version": 2,
        "authority": {
            field: False for field in sorted(independent.AUTHORITY_FIELDS)
        },
        "canonical_limits": {},
        "completion_claims": {},
        "derivation_receipts": _synthetic_receipts(complete_shape=True),
        "fixture_id": package.FIXTURE_ID,
        "fixture_schema_version": 2,
        "g0_contract_frozen": False,
        "hypothesis_status": "synthetic-complete-inventory",
        "missing_projection_class_ledger": [],
        "orders": {
            "derivation_receipts": "synthetic-complete-receipt-order",
            "minimum_projection_classes": list(package.PROJECTION_CLASS_ORDER),
            "persona": list(package.PERSONA_IDS),
        },
        "predecessor_inventory_binding": {
            "artifact_kind": "synthetic-predecessor",
            "artifact_schema": (
                "kio.persona.pc-semantic-projection-derivation-inventory/v1"
            ),
            "artifact_schema_version": 1,
            "body_framing": "canonical-json",
            "canonical_bytes": 1,
            "sha256": "0" * 64,
        },
        "projection_class_registry": [],
        "remaining_blockers": [],
        "summary": {},
    }


def _complete_raw(value):
    return artifact_common.canonical_json_bytes(
        value,
        label="synthetic complete inventory",
        max_bytes=independent.MAX_COMPLETE_INVENTORY_BYTES,
    )


class CorpusSemanticNamespaceV3FastContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipts = _synthetic_receipts()
        cls.value = package._build_namespace_value_from_receipts(cls.receipts)
        cls.raw = package.corpus_semantic_namespace_v3_candidate_bytes(cls.value)

    def _reject(self, value):
        with self.assertRaises(
            independent.PersonaV2CorpusSemanticNamespaceV3ValidationError
        ):
            independent._preflight_namespace(value)
            independent._prevalidate_namespace(value)

    def test_exact_pin_only_contract_and_frozen_golden(self):
        self.assertEqual(set(self.value), package.TOP_LEVEL_FIELDS)
        self.assertEqual(len(self.value), 16)
        self.assertEqual(self.value["artifact_schema"], package.NAMESPACE_SCHEMA)
        self.assertEqual(self.value["artifact_kind"], package.NAMESPACE_KIND)
        self.assertEqual(self.value["artifact_schema_version"], 3)
        self.assertEqual(len(self.value["projection_entries"]), 253)
        self.assertEqual(len(self.value["projection_class_registry"]), 12)
        self.assertLessEqual(len(self.raw), package.TARGET_MANIFEST_BYTES)
        self.assertLessEqual(len(self.raw), package.MAX_MANIFEST_BYTES)
        expected_golden = (
            161_665,
            "a8bc67e182ff57b64ae6df0f97bd5be31faf6e5f7b7cfbd0bc3f1ba7bc5cc509",
        )
        self.assertEqual(
            (
                package.EXPECTED_NAMESPACE_CANONICAL_BYTES,
                package.EXPECTED_NAMESPACE_SHA256,
            ),
            expected_golden,
        )
        self.assertEqual(
            (
                independent.EXPECTED_NAMESPACE_CANONICAL_BYTES,
                independent.EXPECTED_NAMESPACE_SHA256,
            ),
            expected_golden,
        )
        # The fast fixture uses synthetic projection pins so that shape and
        # boundary tests stay sub-second.  The frozen golden is exercised by
        # the opt-in all-253 full/cold gates, not by this synthetic body.
        self.assertNotEqual(
            (len(self.raw), hashlib.sha256(self.raw).hexdigest()),
            expected_golden,
        )
        self.assertIs(
            self.value["completion_claims"]["namespace_golden_frozen"], True
        )
        self.assertTrue(all(value is False for value in self.value["authority"].values()))
        self.assertIs(
            self.value["namespace_contract"]["namespace_issuance_authorized"],
            False,
        )
        self.assertIs(
            self.value["namespace_contract"]["source_identity_derivation_authorized"],
            False,
        )
        self.assertIs(
            self.value["namespace_contract"][
                "source_identity_namespace_authoritative"
            ],
            False,
        )
        forbidden_entry_fields = {
            "receipt_id",
            "projector",
            "full_owner_pins",
            "direct_body_pins",
            "validation",
            "inventory_sha256",
            "query",
            "oracle",
            "review",
            "evidence",
        }
        for ordinal, entry in enumerate(self.value["projection_entries"], start=1):
            self.assertEqual(set(entry), package.ENTRY_FIELDS)
            self.assertEqual(set(entry["projection_pin"]), package.PIN_FIELDS)
            self.assertEqual(entry["projection_pin"]["artifact_schema_version"], 1)
            self.assertEqual(entry["namespace_ordinal"], ordinal)
            self.assertFalse(set(entry) & forbidden_entry_fields)
        self.assertEqual(
            self.value["summary"]["cumulative_external_projection_bytes"],
            155_741_475,
        )
        self.assertEqual(self.value["summary"]["json_projection_body_count"], 67)
        self.assertEqual(self.value["summary"]["jsonl_projection_body_count"], 186)
        self.assertNotIn("predecessor_inventory_binding", self.value)
        self.assertNotIn("derivation_receipts", self.value)
        self.assertNotIn(package.COMPLETE_INVENTORY_SHA256.encode(), self.raw)
        independent._preflight_namespace(self.value)
        independent._prevalidate_namespace(self.value)

    def test_exact_star_graph_and_class_ranges(self):
        graph = self.value["dependency_graph"]
        self.assertEqual(graph["namespace_root_id"], package.NAMESPACE_ROOT_ID)
        self.assertEqual(graph["edge_count"], 253)
        self.assertEqual(graph["max_depth"], 1)
        self.assertEqual(graph["unused_projection_leaf_count"], 0)
        self.assertEqual(
            graph["edges"],
            [
                {
                    "from_node_id": package.NAMESPACE_ROOT_ID,
                    "to_namespace_ordinal": ordinal,
                }
                for ordinal in range(1, 254)
            ],
        )
        self.assertEqual(
            self.value["projection_class_registry"],
            package._projection_class_registry(),
        )

    def test_validator_is_producer_independent_and_api_excludes_downstream_inputs(self):
        source = pathlib.Path(independent.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            module = node.module or ""
            imported.add(module)
            imported.update(
                f"{module}.{alias.name}".strip(".") for alias in node.names
            )
        self.assertFalse(
            any("corpus_semantic_namespace_v3" in name for name in imported)
        )
        parameters = inspect.signature(
            package.build_corpus_semantic_namespace_v3
        ).parameters
        self.assertEqual(set(parameters), {"complete_inventory"})
        for forbidden in ("query", "oracle", "review", "evidence", "ledger"):
            self.assertNotIn(forbidden, parameters)

    def test_missing_extra_duplicate_reorder_and_ordinal_fail_closed(self):
        cases = {}
        missing = copy.deepcopy(self.value)
        missing["projection_entries"].pop()
        cases["missing"] = missing
        extra = copy.deepcopy(self.value)
        extra["projection_entries"].append(copy.deepcopy(extra["projection_entries"][-1]))
        cases["extra"] = extra
        reordered = copy.deepcopy(self.value)
        reordered["projection_entries"][5], reordered["projection_entries"][6] = (
            reordered["projection_entries"][6],
            reordered["projection_entries"][5],
        )
        cases["reordered"] = reordered
        ordinal = copy.deepcopy(self.value)
        ordinal["projection_entries"][0]["namespace_ordinal"] = 2
        cases["ordinal"] = ordinal
        duplicate_pin = copy.deepcopy(self.value)
        duplicate_pin["projection_entries"][1]["projection_pin"]["sha256"] = (
            duplicate_pin["projection_entries"][0]["projection_pin"]["sha256"]
        )
        cases["duplicate-pin"] = duplicate_pin
        duplicate_coordinate = copy.deepcopy(self.value)
        duplicate_coordinate["projection_entries"][6]["coordinates"] = copy.deepcopy(
            duplicate_coordinate["projection_entries"][5]["coordinates"]
        )
        cases["duplicate-coordinate"] = duplicate_coordinate
        for label, value in cases.items():
            with self.subTest(label=label):
                self._reject(value)

    def test_wrong_pin_identity_version_framing_and_caps_fail_closed(self):
        mutations = {
            "kind": ("artifact_kind", "foreign-kind"),
            "schema": ("artifact_schema", "kio.foreign/v1"),
            "version": ("artifact_schema_version", 2),
            "framing": ("body_framing", "canonical-jsonl-lf"),
            "size-bool": ("canonical_bytes", True),
            "size-cap": ("canonical_bytes", package.MAX_JSON_PROJECTION_BYTES + 1),
            "digest-case": ("sha256", "A" * 64),
        }
        for label, (field, replacement) in mutations.items():
            value = copy.deepcopy(self.value)
            value["projection_entries"][0]["projection_pin"][field] = replacement
            with self.subTest(label=label):
                self._reject(value)

    def test_foreign_coordinate_evidence_and_graph_injection_fail_closed(self):
        cases = {}
        foreign_persona = copy.deepcopy(self.value)
        foreign_persona["projection_entries"][5]["coordinates"]["persona_id"] = "p21"
        cases["foreign-persona"] = foreign_persona
        foreign_origin = copy.deepcopy(self.value)
        foreign_origin["projection_entries"][118]["coordinates"]["origin"] = "foreign"
        cases["foreign-origin"] = foreign_origin
        overwide_coordinate = copy.deepcopy(self.value)
        overwide_coordinate["projection_entries"][5]["coordinates"].update(
            {"a": 1, "b": 2, "c": 3, "d": 4}
        )
        cases["coordinate-width"] = overwide_coordinate
        evidence = copy.deepcopy(self.value)
        evidence["projection_entries"][0]["receipt_id"] = "forbidden"
        cases["receipt-evidence"] = evidence
        query = copy.deepcopy(self.value)
        query["query_oracle_bundle"] = {}
        cases["query-top-level"] = query
        old_v2 = copy.deepcopy(self.value)
        old_v2["artifact_schema"] = "kio.persona.pc-corpus-semantic-namespace/v2"
        cases["old-v2-candidate"] = old_v2
        embedded_body = copy.deepcopy(self.value)
        embedded_body["projection_entries"][0]["body"] = {"forbidden": True}
        cases["embedded-body"] = embedded_body
        cycle = copy.deepcopy(self.value)
        cycle["dependency_graph"]["edges"][0]["from_node_id"] = "projection-leaf-2"
        cases["cycle/back-reference"] = cycle
        unused = copy.deepcopy(self.value)
        unused["dependency_graph"]["edges"][0]["to_namespace_ordinal"] = 2
        cases["unused/duplicate-target"] = unused
        for label, value in cases.items():
            with self.subTest(label=label):
                self._reject(value)

    def test_all_false_authority_and_strict_scalar_preflight(self):
        cases = {}
        authority = copy.deepcopy(self.value)
        authority["authority"]["authorizes_corpus_semantic_namespace"] = True
        cases["authority"] = authority
        issuance = copy.deepcopy(self.value)
        issuance["namespace_contract"]["namespace_issuance_authorized"] = True
        cases["issuance"] = issuance
        source_authority = copy.deepcopy(self.value)
        source_authority["completion_claims"][
            "source_identity_namespace_authoritative"
        ] = True
        cases["source-authority"] = source_authority
        null_value = copy.deepcopy(self.value)
        null_value["hypothesis_status"] = None
        cases["null"] = null_value
        float_value = copy.deepcopy(self.value)
        float_value["projection_entries"][0]["namespace_ordinal"] = 1.0
        cases["float"] = float_value
        huge_int = copy.deepcopy(self.value)
        huge_int["projection_entries"][0]["namespace_ordinal"] = 2**127
        cases["huge-int"] = huge_int
        non_nfc = copy.deepcopy(self.value)
        non_nfc["hypothesis_status"] = "e\u0301"
        cases["non-nfc"] = non_nfc
        overwide = copy.deepcopy(self.value)
        overwide["hypothesis_status"] = "x" * (package.MAX_IDENTITY_STRING_BYTES + 1)
        cases["overwide-string"] = overwide
        for label, value in cases.items():
            with self.subTest(label=label):
                self._reject(value)

    def test_projection_pin_mutation_changes_candidate_sha_but_unrelated_inputs_do_not_exist(self):
        changed_receipts = copy.deepcopy(self.receipts)
        changed_receipts[0]["projection_pin"]["sha256"] = hashlib.sha256(
            b"changed-content-projection"
        ).hexdigest()
        changed = package._build_namespace_value_from_receipts(changed_receipts)
        changed_raw = package.corpus_semantic_namespace_v3_candidate_bytes(changed)
        self.assertNotEqual(hashlib.sha256(self.raw).digest(), hashlib.sha256(changed_raw).digest())
        # There is no query/review/ledger parameter whose mutation can enter the preimage.
        unrelated = {
            "query": "SECRET-QUERY-CANARY",
            "review": "SECRET-REVIEW-CANARY",
            "ledger": "SECRET-LEDGER-CANARY",
        }
        unrelated["query"] = "mutated"
        self.assertEqual(
            self.raw,
            package.corpus_semantic_namespace_v3_candidate_bytes(
                package._build_namespace_value_from_receipts(copy.deepcopy(self.receipts))
            ),
        )

    def test_source_receipt_count_order_alias_and_wrong_version_rejected(self):
        cases = {}
        missing = copy.deepcopy(self.receipts)
        missing.pop()
        cases["missing"] = missing
        reordered = copy.deepcopy(self.receipts)
        reordered[0], reordered[1] = reordered[1], reordered[0]
        cases["reorder"] = reordered
        alias = copy.deepcopy(self.receipts)
        alias[1]["projection_pin"]["sha256"] = alias[0]["projection_pin"]["sha256"]
        cases["alias"] = alias
        wrong_version = copy.deepcopy(self.receipts)
        wrong_version[0]["projection_pin"]["artifact_schema_version"] = 2
        cases["version"] = wrong_version
        for label, receipts in cases.items():
            with self.subTest(label=label), self.assertRaises(
                package.PersonaV2CorpusSemanticNamespaceV3Error
            ):
                package._build_namespace_value_from_receipts(receipts)

    def test_immutable_byte_caches_return_no_mutable_authority_state(self):
        inventory = _synthetic_complete_inventory()
        inventory_raw = _complete_raw(inventory)
        producer_cache = package._namespace_raw_from_complete_inventory_raw
        validator_cache = independent._expected_namespace_raw_from_complete_raw
        try:
            with (
                mock.patch.multiple(
                    package,
                    EXPECTED_NAMESPACE_CANONICAL_BYTES=None,
                    EXPECTED_NAMESPACE_SHA256=None,
                ),
                mock.patch.multiple(
                    independent,
                    EXPECTED_NAMESPACE_CANONICAL_BYTES=None,
                    EXPECTED_NAMESPACE_SHA256=None,
                ),
            ):
                producer_cache.cache_clear()
                validator_cache.cache_clear()
                producer_raw = producer_cache(inventory_raw)
                validator_raw = validator_cache(inventory_raw)
                self.assertIs(type(producer_raw), bytes)
                self.assertIs(type(validator_raw), bytes)
                self.assertEqual(producer_raw, validator_raw)
                detached = json.loads(producer_raw)
                detached["authority"]["authorizes_g0_freeze"] = True
                self.assertEqual(producer_cache(inventory_raw), producer_raw)
                self.assertEqual(validator_cache(inventory_raw), validator_raw)
        finally:
            # Never leave a synthetic value cached after restoring the frozen
            # constants: the cache key intentionally contains only raw bytes.
            producer_cache.cache_clear()
            validator_cache.cache_clear()


class CorpusSemanticNamespaceV3FastBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.inventory = _synthetic_complete_inventory()
        self.inventory_raw = _complete_raw(self.inventory)
        self.namespace = package._build_namespace_value_from_receipts(
            self.inventory["derivation_receipts"]
        )
        independent._expected_namespace_raw_from_complete_raw.cache_clear()

    def _pin_context(self):
        return mock.patch.multiple(
            independent,
            COMPLETE_INVENTORY_CANONICAL_BYTES=len(self.inventory_raw),
            COMPLETE_INVENTORY_SHA256=hashlib.sha256(self.inventory_raw).hexdigest(),
            EXPECTED_NAMESPACE_CANONICAL_BYTES=None,
            EXPECTED_NAMESPACE_SHA256=None,
        )

    def test_mocked_trust_source_boundary_accepts_exact_metadata_without_building_bodies(self):
        with self._pin_context(), mock.patch.object(
            independent.complete_validator,
            "validate_semantic_projection_complete_inventory",
            return_value=True,
        ) as validator:
            self.assertTrue(
                independent.validate_corpus_semantic_namespace_v3(
                    self.namespace,
                    complete_inventory=self.inventory,
                    projection_body_provider=lambda _receipt: b"unused",
                )
            )
        validator.assert_called_once()

    def test_invalid_namespace_preflight_makes_zero_trust_source_calls(self):
        invalid = copy.deepcopy(self.namespace)
        invalid["projection_entries"].pop()
        with self._pin_context(), mock.patch.object(
            independent.complete_validator,
            "validate_semantic_projection_complete_inventory",
            return_value=True,
        ) as validator, self.assertRaises(
            independent.PersonaV2CorpusSemanticNamespaceV3ValidationError
        ):
            independent.validate_corpus_semantic_namespace_v3(
                invalid,
                complete_inventory=self.inventory,
                projection_body_provider=lambda _receipt: b"unused",
            )
        validator.assert_not_called()

    def test_independent_reconstruction_rejects_valid_looking_pin_and_shard_tamper(self):
        cases = {}
        pin = copy.deepcopy(self.namespace)
        pin["projection_entries"][0]["projection_pin"]["sha256"] = hashlib.sha256(
            b"valid-looking-but-foreign-pin"
        ).hexdigest()
        cases["pin"] = pin
        shard = copy.deepcopy(self.namespace)
        shard["projection_entries"][25]["coordinates"]["source_shard_id"] = (
            "bounded-but-foreign-shard"
        )
        cases["shard"] = shard
        for label, value in cases.items():
            with self.subTest(label=label), self._pin_context(), mock.patch.object(
                independent.complete_validator,
                "validate_semantic_projection_complete_inventory",
                return_value=True,
            ) as validator, self.assertRaises(
                independent.PersonaV2CorpusSemanticNamespaceV3ValidationError
            ):
                independent.validate_corpus_semantic_namespace_v3(
                    value,
                    complete_inventory=self.inventory,
                    projection_body_provider=lambda _receipt: b"unused",
                )
            validator.assert_called_once()

    def test_provider_callback_namespace_and_inventory_toctou_fail_closed(self):
        for target in ("namespace", "inventory"):
            namespace = copy.deepcopy(self.namespace)
            inventory = copy.deepcopy(self.inventory)
            inventory_raw = _complete_raw(inventory)

            def fake_complete_validator(_value, *, projection_body_provider):
                projection_body_provider({"receipt": "detached"})
                return True

            def mutating_provider(_receipt):
                if target == "namespace":
                    namespace["hypothesis_status"] = "mutated-during-provider"
                else:
                    inventory["hypothesis_status"] = "mutated-during-provider"
                return b"body"

            with self.subTest(target=target), mock.patch.multiple(
                independent,
                COMPLETE_INVENTORY_CANONICAL_BYTES=len(inventory_raw),
                COMPLETE_INVENTORY_SHA256=hashlib.sha256(inventory_raw).hexdigest(),
                EXPECTED_NAMESPACE_CANONICAL_BYTES=None,
                EXPECTED_NAMESPACE_SHA256=None,
            ), mock.patch.object(
                independent.complete_validator,
                "validate_semantic_projection_complete_inventory",
                side_effect=fake_complete_validator,
            ), self.assertRaises(
                independent.PersonaV2CorpusSemanticNamespaceV3ValidationError
            ):
                independent.validate_corpus_semantic_namespace_v3(
                    namespace,
                    complete_inventory=inventory,
                    projection_body_provider=mutating_provider,
                )

    def test_provider_exception_message_is_suppressed(self):
        secret = "SECRET-QUERY-CANARY"

        def fake_complete_validator(_value, *, projection_body_provider):
            projection_body_provider({"receipt": "detached"})

        def failing_provider(_receipt):
            raise RuntimeError(secret)

        with self._pin_context(), mock.patch.object(
            independent.complete_validator,
            "validate_semantic_projection_complete_inventory",
            side_effect=fake_complete_validator,
        ), self.assertRaises(
            independent.PersonaV2CorpusSemanticNamespaceV3ValidationError
        ) as raised:
            independent.validate_corpus_semantic_namespace_v3(
                self.namespace,
                complete_inventory=self.inventory,
                projection_body_provider=failing_provider,
            )
        self.assertNotIn(secret, str(raised.exception))
        self.assertIsNone(raised.exception.__cause__)

    def test_duplicate_key_and_oversize_raw_rejected_before_trust_source(self):
        raw_values = (
            b'{"x":1,"x":2}',
            b"{" + b" " * independent.MAX_MANIFEST_BYTES + b"}",
            b'{"x":1.5}',
            b'{"x":NaN}',
            b'{"x":null}',
        )
        for raw in raw_values:
            with self.subTest(raw=raw[:20]), mock.patch.object(
                independent.complete_validator,
                "validate_semantic_projection_complete_inventory",
                return_value=True,
            ) as validator, self.assertRaises(
                independent.PersonaV2CorpusSemanticNamespaceV3ValidationError
            ):
                independent.validate_corpus_semantic_namespace_v3_bytes(
                    raw,
                    complete_inventory=self.inventory,
                    projection_body_provider=lambda _receipt: b"unused",
                )
            validator.assert_not_called()

    def test_shared_container_bombs_fail_before_canonicalization_or_trust_source(self):
        big = ["x" * independent.MAX_IDENTITY_STRING_BYTES for _ in range(512)]
        namespace_bomb = copy.deepcopy(self.namespace)
        for edge in namespace_bomb["dependency_graph"]["edges"]:
            edge["from_node_id"] = big
        with mock.patch.object(
            independent,
            "_canonical_namespace",
            side_effect=AssertionError("namespace canonicalizer must not run"),
        ) as canonicalizer, mock.patch.object(
            independent.complete_validator,
            "validate_semantic_projection_complete_inventory",
            side_effect=AssertionError("trust source must not run"),
        ) as trust_source, self.assertRaises(
            independent.PersonaV2CorpusSemanticNamespaceV3ValidationError
        ):
            independent.validate_corpus_semantic_namespace_v3(
                namespace_bomb,
                complete_inventory=self.inventory,
                projection_body_provider=lambda _receipt: b"unused",
            )
        canonicalizer.assert_not_called()
        trust_source.assert_not_called()
        with mock.patch.object(
            package,
            "_canonical",
            side_effect=AssertionError("producer canonicalizer must not run"),
        ) as producer_canonicalizer, self.assertRaises(
            package.PersonaV2CorpusSemanticNamespaceV3Error
        ):
            package.corpus_semantic_namespace_v3_candidate_bytes(namespace_bomb)
        producer_canonicalizer.assert_not_called()

        inventory_bomb = copy.deepcopy(self.inventory)
        for receipt in inventory_bomb["derivation_receipts"]:
            receipt["direct_body_pins"][0]["direct_pin_id"] = big
        with mock.patch.object(
            independent,
            "_canonical_complete",
            side_effect=AssertionError("complete canonicalizer must not run"),
        ) as canonicalizer, mock.patch.object(
            independent.complete_validator,
            "validate_semantic_projection_complete_inventory",
            side_effect=AssertionError("trust source must not run"),
        ) as trust_source, self.assertRaises(
            independent.PersonaV2CorpusSemanticNamespaceV3ValidationError
        ):
            independent.validate_corpus_semantic_namespace_v3(
                self.namespace,
                complete_inventory=inventory_bomb,
                projection_body_provider=lambda _receipt: b"unused",
            )
        canonicalizer.assert_not_called()
        trust_source.assert_not_called()
        with mock.patch.object(
            package.complete,
            "canonical_json_bytes",
            side_effect=AssertionError("producer complete canonicalizer must not run"),
        ) as producer_complete_canonicalizer, self.assertRaises(
            package.PersonaV2CorpusSemanticNamespaceV3Error
        ):
            package.build_corpus_semantic_namespace_v3(inventory_bomb)
        producer_complete_canonicalizer.assert_not_called()

    def test_deep_raw_json_recursion_is_normalized_before_trust_source(self):
        raw = b"[" * 100_000 + b"]" * 100_000
        self.assertLess(len(raw), independent.MAX_MANIFEST_BYTES)
        with mock.patch.object(
            independent.complete_validator,
            "validate_semantic_projection_complete_inventory",
            side_effect=AssertionError("trust source must not run"),
        ) as trust_source, self.assertRaises(
            independent.PersonaV2CorpusSemanticNamespaceV3ValidationError
        ):
            independent.validate_corpus_semantic_namespace_v3_bytes(
                raw,
                complete_inventory=self.inventory,
                projection_body_provider=lambda _receipt: b"unused",
            )
        trust_source.assert_not_called()

    def test_final_postflight_detects_mutation_after_source_validator(self):
        original = self.namespace["hypothesis_status"]

        def mutate_after_validation(_value, *, projection_body_provider):
            self.namespace["hypothesis_status"] = "mutated-at-final-postflight"
            return True

        try:
            with self._pin_context(), mock.patch.object(
                independent.complete_validator,
                "validate_semantic_projection_complete_inventory",
                side_effect=mutate_after_validation,
            ), self.assertRaises(
                independent.PersonaV2CorpusSemanticNamespaceV3ValidationError
            ):
                independent.validate_corpus_semantic_namespace_v3(
                    self.namespace,
                    complete_inventory=self.inventory,
                    projection_body_provider=lambda _receipt: b"unused",
                )
        finally:
            self.namespace["hypothesis_status"] = original


@unittest.skipUnless(
    os.environ.get("KIO_RUN_NAMESPACE_V3_FULL") == "1",
    "set KIO_RUN_NAMESPACE_V3_FULL=1 for the all-253 trust-source gate",
)
class CorpusSemanticNamespaceV3LongAll253Test(unittest.TestCase):
    def test_full_complete_inventory_and_two_body_replays(self):
        started = time.monotonic()
        inventory = complete.build_semantic_projection_complete_inventory()
        namespace = package.build_corpus_semantic_namespace_v3(inventory)
        calls = collections.Counter()

        def counted_provider(receipt):
            calls[receipt["receipt_id"]] += 1
            return complete.projection_body_provider(receipt)

        self.assertTrue(
            independent.validate_corpus_semantic_namespace_v3(
                namespace,
                complete_inventory=inventory,
                projection_body_provider=counted_provider,
            )
        )
        self.assertEqual(sum(calls.values()), 506)
        self.assertEqual(len(calls), 253)
        self.assertTrue(all(count == 2 for count in calls.values()))
        raw = package.corpus_semantic_namespace_v3_candidate_bytes(namespace)
        self.assertLessEqual(len(raw), package.TARGET_MANIFEST_BYTES)
        measurement = {
            "elapsed_seconds": time.monotonic() - started,
            "namespace_bytes": len(raw),
            "namespace_sha256": hashlib.sha256(raw).hexdigest(),
        }
        print(json.dumps(measurement, sort_keys=True))
        if package.EXPECTED_NAMESPACE_CANONICAL_BYTES is not None:
            self.assertEqual(
                measurement["namespace_bytes"],
                package.EXPECTED_NAMESPACE_CANONICAL_BYTES,
            )
        if package.EXPECTED_NAMESPACE_SHA256 is not None:
            self.assertEqual(
                measurement["namespace_sha256"], package.EXPECTED_NAMESPACE_SHA256
            )


@unittest.skipUnless(
    os.environ.get("KIO_RUN_NAMESPACE_V3_COLD") == "1",
    "set KIO_RUN_NAMESPACE_V3_COLD=1 for the two-hash-seed all-253 gate",
)
class CorpusSemanticNamespaceV3LongColdHashSeedTest(unittest.TestCase):
    def test_two_hashseeds_are_stable_and_resource_bounded(self):
        script = r'''
import collections
import hashlib
import json
import os
import resource
import sys
import time
from eval import persona_v2_corpus_semantic_namespace_v3 as package
from eval import persona_v2_corpus_semantic_namespace_v3_validator as independent
from eval import persona_v2_semantic_projection_complete_inventory as complete

started = time.monotonic()
inventory = complete.build_semantic_projection_complete_inventory()
namespace = package.build_corpus_semantic_namespace_v3(inventory)
calls = collections.Counter()

def counted_provider(receipt):
    calls[receipt["receipt_id"]] += 1
    return complete.projection_body_provider(receipt)

result = independent.validate_corpus_semantic_namespace_v3(
    namespace,
    complete_inventory=inventory,
    projection_body_provider=counted_provider,
)
if result is not True:
    raise RuntimeError("namespace validator did not return exact true")
if len(calls) != 253 or sum(calls.values()) != 506:
    raise RuntimeError("all-253 two-replay call cardinality drifted")
if any(count != 2 for count in calls.values()):
    raise RuntimeError("one or more projection bodies were not replayed twice")
raw = package.corpus_semantic_namespace_v3_candidate_bytes(namespace)
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
if sys.platform != "darwin":
    rss *= 1024
print(json.dumps({
    "elapsed_seconds": time.monotonic() - started,
    "maximum_rss_bytes": rss,
    "namespace_bytes": len(raw),
    "namespace_sha256": hashlib.sha256(raw).hexdigest(),
    "projection_body_call_count": sum(calls.values()),
    "python_hash_seed": os.environ.get("PYTHONHASHSEED"),
    "unique_projection_receipt_count": len(calls),
}, sort_keys=True))
'''
        measurements = []
        for seed in ("0", "1"):
            environment = os.environ.copy()
            environment.update(
                {
                    "LANG": "C",
                    "LC_ALL": "C",
                    "PYTHONHASHSEED": seed,
                    "TZ": "UTC",
                }
            )
            completed = subprocess.run(
                [sys.executable, "-c", script],
                cwd=os.path.dirname(os.path.dirname(__file__)),
                env=environment,
                capture_output=True,
                check=True,
                text=True,
                timeout=7_200,
            )
            measurement = json.loads(completed.stdout.splitlines()[-1])
            self.assertEqual(measurement["python_hash_seed"], seed)
            self.assertEqual(measurement["projection_body_call_count"], 506)
            self.assertEqual(measurement["unique_projection_receipt_count"], 253)
            self.assertLessEqual(measurement["elapsed_seconds"], 7_200)
            self.assertLessEqual(measurement["maximum_rss_bytes"], 1 * 2**30)
            self.assertLessEqual(
                measurement["namespace_bytes"], package.TARGET_MANIFEST_BYTES
            )
            measurements.append(measurement)
        print(
            json.dumps(
                {"namespace_v3_cold_measurements": measurements}, sort_keys=True
            )
        )
        self.assertEqual(
            {measurement["python_hash_seed"] for measurement in measurements},
            {"0", "1"},
        )
        stable_fields = ("namespace_bytes", "namespace_sha256")
        self.assertEqual(
            {field: measurements[0][field] for field in stable_fields},
            {field: measurements[1][field] for field in stable_fields},
        )
        producer_golden = (
            package.EXPECTED_NAMESPACE_CANONICAL_BYTES,
            package.EXPECTED_NAMESPACE_SHA256,
        )
        validator_golden = (
            independent.EXPECTED_NAMESPACE_CANONICAL_BYTES,
            independent.EXPECTED_NAMESPACE_SHA256,
        )
        self.assertEqual(producer_golden, validator_golden)
        self.assertEqual(producer_golden[0] is None, producer_golden[1] is None)
        if producer_golden[0] is not None:
            for measurement in measurements:
                self.assertEqual(measurement["namespace_bytes"], producer_golden[0])
                self.assertEqual(measurement["namespace_sha256"], producer_golden[1])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
