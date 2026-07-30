import copy
import hashlib
import json
import os
import subprocess
import sys
import unittest

from eval import persona_v2_artifact_common as common
from eval import persona_v2_input_closure as closure


FIXTURE_ID = "kio-persona-pc-v2-test"
EXPECTED_SYNTHETIC_ROOT_IDENTITIES = {
    "corpus": (
        3_245,
        "845c78909d0fa9d38ef580b75ac3ff7d675d782ab53963c56e3fb9aeeba7d3fe",
    ),
    "evaluation": (
        4_014,
        "83e5e5da0880596facdcd299c52eabfe1855fef99ce4794dd34c753cc9409cfd",
    ),
    "semantic": (
        3_723,
        "53d4c8e5663be43579a994422f1dff4053adfc5a628801d711dcc5a5327c2d9b",
    ),
    "suite": (
        2_624,
        "c98bac72e2597b5f90944fe8c1d47888ed5e607555768a1dd4e1ea5642e4b58d",
    ),
}


def _canonicalize(value):
    return common.canonical_json_bytes(
        value, label="synthetic closure input", max_bytes=closure.MAX_UPSTREAM_BODY_BYTES
    )


def _validate(value):
    if type(value) is not dict:
        raise ValueError("body must be an object")
    return True


def _body(*, schema, kind, payload, dependencies=(), complete=False):
    authority_fields = closure._EXACT_TOP_LEVEL_AUTHORITY_FIELDS_BY_SCHEMA.get(
        schema, closure._STANDARD_NEGATIVE_AUTHORITY_FIELDS
    )
    return {
        "artifact_kind": kind,
        "artifact_schema": schema,
        "artifact_schema_version": 2,
        "authority": {field: False for field in authority_fields},
        "catalog_complete": complete,
        "fixture_id": FIXTURE_ID,
        "fixture_schema_version": 2,
        "g0_contract_frozen": False,
        "input_bindings": [
            {"entry_id": entry_id, "sha256": digest}
            for entry_id, digest in dependencies
        ],
        "payload": payload,
    }


def _pin(
    entry_id,
    input_class,
    body,
    dependency_ids=(),
    binding_aliases=None,
):
    raw = _canonicalize(body)
    if binding_aliases is None:
        binding_aliases = (entry_id,)
    return {
        "artifact_kind": body["artifact_kind"],
        "artifact_schema": body["artifact_schema"],
        "artifact_schema_version": body["artifact_schema_version"],
        "binding_aliases": list(binding_aliases),
        "canonical_bytes": len(raw),
        "dependency_ids": list(dependency_ids),
        "entry_id": entry_id,
        "fixture_id": body["fixture_id"],
        "fixture_schema_version": body["fixture_schema_version"],
        "input_class": input_class,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _anchor_pin(value, *, entry_id, canonicalize):
    raw = canonicalize(value)
    return {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "entry_id": entry_id,
        "fixture_id": value["fixture_id"],
        "fixture_schema_version": value["fixture_schema_version"],
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _provider(entry_id, body):
    return {
        "body": body,
        "canonicalize": _canonicalize,
        "entry_id": entry_id,
        "validate": _validate,
    }


def _world(
    *,
    route_value="r1",
    review_value="review-1",
    query_spec_value="query-spec-1",
    formal_compiled=False,
    oracle_final_id=False,
):
    route = _body(
        schema="kio.persona.pc-route-affinity/v2",
        kind="persona-pc-v2-route-affinity-matrix",
        payload={"route_value": route_value},
    )
    route_pin = _pin("route-body", "corpus-semantic", route)
    source = _body(
        schema="kio.persona.pc-source-intent-origin-shard/v2",
        kind="persona-pc-v2-source-intent-origin-shard",
        payload={"intent_key": "p01-intent-pilot-syn-0001"},
        dependencies=(("route-body", route_pin["sha256"]),),
    )
    source_pin = _pin(
        "source-shard-p01", "corpus-semantic", source, ("route-body",)
    )
    semantic_pins = [route_pin, source_pin]
    semantic_providers = [
        _provider("route-body", route),
        _provider("source-shard-p01", source),
    ]
    semantic_roots = ["source-shard-p01"]
    semantic = closure.build_corpus_semantic_namespace(
        pins=semantic_pins,
        providers=semantic_providers,
        root_entry_ids=semantic_roots,
    )

    receipt = _body(
        schema="kio.persona.pc-review-evidence/v2",
        kind="persona-pc-v2-review-evidence",
        payload={"review_evidence": review_value},
        dependencies=(("route-body", route_pin["sha256"]),),
    )
    receipt_pin = _pin(
        "route-review-receipt", "evidence", receipt, ("route-body",)
    )
    evidence_pins = [receipt_pin]
    evidence_providers = [_provider("route-review-receipt", receipt)]
    evidence_roots = ["route-review-receipt"]
    corpus = closure.build_corpus_input_closure(
        semantic_namespace=semantic,
        semantic_pins=semantic_pins,
        semantic_providers=semantic_providers,
        semantic_root_entry_ids=semantic_roots,
        evidence_pins=evidence_pins,
        evidence_providers=evidence_providers,
        evidence_root_entry_ids=evidence_roots,
    )
    corpus_pin = _anchor_pin(
        corpus,
        entry_id="corpus-input-closure",
        canonicalize=closure.corpus_input_closure_bytes,
    )

    query = _body(
        schema="kio.persona.pc-query-intent/v2",
        kind="persona-pc-v2-query-intent",
        payload={
            "formal_relevance_compiled": formal_compiled,
            "query_spec_value": query_spec_value,
        },
        dependencies=(("source-shard-p01", source_pin["sha256"]),),
    )
    query["formal_relevance_compiled"] = formal_compiled
    query_pin = _pin(
        "query-p01", "evaluation", query, ("source-shard-p01",)
    )
    oracle_payload = {"answer": "logical-document-syn-001"}
    if oracle_final_id:
        oracle_payload["final_source_id"] = "forbidden-final-source"
    oracle = _body(
        schema="kio.persona.pc-semantic-oracle/v2",
        kind="persona-pc-v2-semantic-oracle",
        payload=oracle_payload,
        dependencies=(
            ("query-p01", query_pin["sha256"]),
            ("source-shard-p01", source_pin["sha256"]),
        ),
    )
    oracle_pin = _pin(
        "oracle-p01",
        "evaluation",
        oracle,
        ("query-p01", "source-shard-p01"),
    )
    evaluation_pins = [query_pin, oracle_pin]
    evaluation_providers = [
        _provider("query-p01", query),
        _provider("oracle-p01", oracle),
    ]
    evaluation_roots = ["oracle-p01"]
    evaluation = closure.build_evaluation_input_closure(
        corpus_input_closure=corpus,
        corpus_input_closure_pin=corpus_pin,
        evaluation_pins=evaluation_pins,
        evaluation_providers=evaluation_providers,
        evaluation_root_entry_ids=evaluation_roots,
        semantic_namespace=semantic,
    )
    evaluation_pin = _anchor_pin(
        evaluation,
        entry_id="evaluation-input-closure",
        canonicalize=closure.evaluation_input_closure_bytes,
    )
    suite = closure.build_suite_input_descriptor(
        corpus_input_closure=corpus,
        corpus_input_closure_pin=corpus_pin,
        evaluation_input_closure=evaluation,
        evaluation_input_closure_pin=evaluation_pin,
    )
    return {
        "corpus": corpus,
        "corpus_pin": corpus_pin,
        "evaluation": evaluation,
        "evaluation_pin": evaluation_pin,
        "evaluation_pins": evaluation_pins,
        "evaluation_providers": evaluation_providers,
        "evaluation_roots": evaluation_roots,
        "evidence_pins": evidence_pins,
        "evidence_providers": evidence_providers,
        "evidence_roots": evidence_roots,
        "semantic": semantic,
        "semantic_pins": semantic_pins,
        "semantic_providers": semantic_providers,
        "semantic_roots": semantic_roots,
        "suite": suite,
    }


def _non_authorizing_identity_stability_probe(semantic):
    # This is an isolation probe only; the candidate explicitly cannot drive
    # the production source/materialization identity algorithm.
    digest = closure.corpus_semantic_namespace_sha256(semantic)
    return hashlib.sha256(f"identity-probe\0{digest}\0p01\0ordinal-1".encode()).hexdigest()


class PersonaV2InputClosureTests(unittest.TestCase):
    def test_four_roots_are_exact_negative_authority_and_separated(self):
        world = _world()
        semantic = world["semantic"]
        corpus = world["corpus"]
        evaluation = world["evaluation"]
        suite = world["suite"]

        self.assertEqual(semantic["artifact_schema"], closure.CORPUS_SEMANTIC_SCHEMA)
        self.assertEqual(corpus["artifact_schema"], closure.CORPUS_INPUT_CLOSURE_SCHEMA)
        self.assertEqual(
            evaluation["artifact_schema"], closure.EVALUATION_INPUT_CLOSURE_SCHEMA
        )
        self.assertEqual(suite["artifact_schema"], closure.SUITE_INPUT_DESCRIPTOR_SCHEMA)
        for value in (semantic, corpus, evaluation, suite):
            self.assertIs(value["g0_contract_frozen"], False)
            self.assertEqual(set(value["authority"]), set(closure.AUTHORITY_FIELDS))
            for flag in value["authority"].values():
                self.assertIs(type(flag), bool)
                self.assertIs(flag, False)
            self.assertIs(
                value["completion_claims"]["canonical_g0_input_inventory_complete"],
                False,
            )
            self.assertIs(
                value["completion_claims"]["semantic_payload_projection_bound"],
                False,
            )

        self.assertEqual(
            [row["entry_id"] for row in semantic["input_entries"]],
            ["route-body", "source-shard-p01"],
        )
        self.assertEqual(
            [row["entry_id"] for row in corpus["evidence_entries"]],
            ["route-review-receipt"],
        )
        self.assertEqual(
            [row["entry_id"] for row in evaluation["evaluation_entries"]],
            ["query-p01", "oracle-p01"],
        )
        semantic_json = closure.corpus_semantic_namespace_bytes(semantic)
        self.assertNotIn(b"query-p01", semantic_json)
        self.assertNotIn(b"route-review-receipt", semantic_json)
        self.assertNotIn(b"oracle-p01", closure.corpus_input_closure_bytes(corpus))
        self.assertIs(evaluation["formal_relevance_compiled"], False)
        self.assertIs(
            semantic["namespace_contract"]["future_source_id_namespace_eligible"],
            False,
        )
        self.assertIs(
            semantic["namespace_contract"]["semantic_payload_projection_bound"],
            False,
        )
        self.assertIs(
            semantic["namespace_contract"]["query_semantics_absence_proved"],
            False,
        )
        self.assertIn(
            ["catalog_complete"],
            semantic["input_entries"][0]["propagated_false_status_paths"],
        )

    def test_query_and_receipt_mutations_do_not_perturb_semantic_namespace(self):
        base = _world()
        query_changed = _world(query_spec_value="different-query-spec")
        receipt_changed = _world(review_value="review-2")
        route_changed = _world(route_value="r2")

        semantic_sha = closure.corpus_semantic_namespace_sha256(base["semantic"])
        corpus_sha = closure.corpus_input_closure_sha256(base["corpus"])
        eval_sha = closure.evaluation_input_closure_sha256(base["evaluation"])
        suite_sha = closure.suite_input_descriptor_sha256(base["suite"])

        self.assertEqual(
            semantic_sha,
            closure.corpus_semantic_namespace_sha256(query_changed["semantic"]),
        )
        self.assertEqual(
            corpus_sha,
            closure.corpus_input_closure_sha256(query_changed["corpus"]),
        )
        self.assertNotEqual(
            eval_sha,
            closure.evaluation_input_closure_sha256(query_changed["evaluation"]),
        )
        self.assertNotEqual(
            suite_sha,
            closure.suite_input_descriptor_sha256(query_changed["suite"]),
        )

        self.assertEqual(
            semantic_sha,
            closure.corpus_semantic_namespace_sha256(receipt_changed["semantic"]),
        )
        self.assertNotEqual(
            corpus_sha,
            closure.corpus_input_closure_sha256(receipt_changed["corpus"]),
        )
        self.assertNotEqual(
            eval_sha,
            closure.evaluation_input_closure_sha256(receipt_changed["evaluation"]),
        )
        self.assertNotEqual(
            suite_sha,
            closure.suite_input_descriptor_sha256(receipt_changed["suite"]),
        )
        self.assertNotEqual(
            semantic_sha,
            closure.corpus_semantic_namespace_sha256(route_changed["semantic"]),
        )

        expected_probe = _non_authorizing_identity_stability_probe(base["semantic"])
        self.assertEqual(
            expected_probe,
            _non_authorizing_identity_stability_probe(query_changed["semantic"]),
        )
        self.assertEqual(
            expected_probe,
            _non_authorizing_identity_stability_probe(receipt_changed["semantic"]),
        )
        self.assertNotEqual(
            expected_probe,
            _non_authorizing_identity_stability_probe(route_changed["semantic"]),
        )

    def test_exact_regeneration_validation_and_hashes(self):
        world = _world()
        self.assertTrue(
            closure.validate_corpus_semantic_namespace(
                world["semantic"],
                pins=world["semantic_pins"],
                providers=world["semantic_providers"],
                root_entry_ids=world["semantic_roots"],
            )
        )
        self.assertTrue(
            closure.validate_corpus_input_closure(
                world["corpus"],
                semantic_namespace=world["semantic"],
                semantic_pins=world["semantic_pins"],
                semantic_providers=world["semantic_providers"],
                semantic_root_entry_ids=world["semantic_roots"],
                evidence_pins=world["evidence_pins"],
                evidence_providers=world["evidence_providers"],
                evidence_root_entry_ids=world["evidence_roots"],
            )
        )
        self.assertTrue(
            closure.validate_evaluation_input_closure(
                world["evaluation"],
                corpus_input_closure=world["corpus"],
                corpus_input_closure_pin=world["corpus_pin"],
                evaluation_pins=world["evaluation_pins"],
                evaluation_providers=world["evaluation_providers"],
                evaluation_root_entry_ids=world["evaluation_roots"],
                semantic_namespace=world["semantic"],
            )
        )
        self.assertTrue(
            closure.validate_suite_input_descriptor(
                world["suite"],
                corpus_input_closure=world["corpus"],
                corpus_input_closure_pin=world["corpus_pin"],
                evaluation_input_closure=world["evaluation"],
                evaluation_input_closure_pin=world["evaluation_pin"],
            )
        )
        for root_name, raw, digest in (
            (
                "semantic",
                closure.corpus_semantic_namespace_bytes(world["semantic"]),
                closure.corpus_semantic_namespace_sha256(world["semantic"]),
            ),
            (
                "corpus",
                closure.corpus_input_closure_bytes(world["corpus"]),
                closure.corpus_input_closure_sha256(world["corpus"]),
            ),
            (
                "evaluation",
                closure.evaluation_input_closure_bytes(world["evaluation"]),
                closure.evaluation_input_closure_sha256(world["evaluation"]),
            ),
            (
                "suite",
                closure.suite_input_descriptor_bytes(world["suite"]),
                closure.suite_input_descriptor_sha256(world["suite"]),
            ),
        ):
            self.assertEqual(hashlib.sha256(raw).hexdigest(), digest)
            self.assertEqual(
                (len(raw), digest), EXPECTED_SYNTHETIC_ROOT_IDENTITIES[root_name]
            )
            self.assertLess(len(raw), closure.MAX_INPUT_ROOT_BYTES)
            self.assertRegex(digest, r"^[0-9a-f]{64}$")

        mutated = copy.deepcopy(world["suite"])
        mutated["root_binding_count"] = 3
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError, "exact regeneration"
        ):
            closure.validate_suite_input_descriptor(
                mutated,
                corpus_input_closure=world["corpus"],
                corpus_input_closure_pin=world["corpus_pin"],
                evaluation_input_closure=world["evaluation"],
                evaluation_input_closure_pin=world["evaluation_pin"],
            )

    def test_exact_schema_length_and_sha_pins_fail_closed(self):
        world = _world()
        for field, replacement, message in (
            ("artifact_schema", "kio.wrong/v2", "artifact_schema drifted"),
            ("canonical_bytes", 1, "canonical byte length"),
            ("sha256", "0" * 64, "SHA-256 differs"),
        ):
            pins = copy.deepcopy(world["semantic_pins"])
            pins[0][field] = replacement
            if field == "artifact_schema":
                # Keep the pin's class syntactically valid; body identity must reject it.
                pins[0]["artifact_kind"] = "persona-pc-v2-wrong-body"
            with self.assertRaisesRegex(closure.PersonaV2InputClosureError, message):
                closure.build_corpus_semantic_namespace(
                    pins=pins,
                    providers=world["semantic_providers"],
                    root_entry_ids=world["semantic_roots"],
                )

        bad_provider = copy.deepcopy(world["semantic_providers"])
        bad_provider[0]["canonicalize"] = lambda value: b"{}"
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError, "differ from strict JSON"
        ):
            closure.build_corpus_semantic_namespace(
                pins=world["semantic_pins"],
                providers=bad_provider,
                root_entry_ids=world["semantic_roots"],
            )

    def test_duplicate_missing_and_unreferenced_entries_fail_closed(self):
        world = _world()

        duplicate_pins = world["semantic_pins"] + [world["semantic_pins"][0]]
        with self.assertRaisesRegex(closure.PersonaV2InputClosureError, "duplicate pin"):
            closure.build_corpus_semantic_namespace(
                pins=duplicate_pins,
                providers=world["semantic_providers"],
                root_entry_ids=world["semantic_roots"],
            )
        duplicate_providers = world["semantic_providers"] + [
            world["semantic_providers"][0]
        ]
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError, "duplicate provider"
        ):
            closure.build_corpus_semantic_namespace(
                pins=world["semantic_pins"],
                providers=duplicate_providers,
                root_entry_ids=world["semantic_roots"],
            )
        with self.assertRaisesRegex(closure.PersonaV2InputClosureError, "duplicate entries"):
            closure.build_corpus_semantic_namespace(
                pins=world["semantic_pins"],
                providers=world["semantic_providers"],
                root_entry_ids=["source-shard-p01", "source-shard-p01"],
            )
        duplicate_dependency = copy.deepcopy(world["semantic_pins"])
        duplicate_dependency[1]["dependency_ids"].append("route-body")
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError, "duplicate dependency"
        ):
            closure.build_corpus_semantic_namespace(
                pins=duplicate_dependency,
                providers=world["semantic_providers"],
                root_entry_ids=world["semantic_roots"],
            )
        with self.assertRaisesRegex(closure.PersonaV2InputClosureError, "missing=.*route"):
            closure.build_corpus_semantic_namespace(
                pins=world["semantic_pins"],
                providers=world["semantic_providers"][1:],
                root_entry_ids=world["semantic_roots"],
            )
        missing_dependency = copy.deepcopy(world["semantic_pins"])
        missing_dependency[1]["dependency_ids"] = ["missing-body"]
        with self.assertRaisesRegex(closure.PersonaV2InputClosureError, "missing dependency"):
            closure.build_corpus_semantic_namespace(
                pins=missing_dependency,
                providers=world["semantic_providers"],
                root_entry_ids=world["semantic_roots"],
            )

        orphan = _body(
            schema="kio.persona.pc-fact-graph/v2",
            kind="persona-pc-v2-fact-graph",
            payload={"fact": "orphan"},
        )
        with self.assertRaisesRegex(closure.PersonaV2InputClosureError, "unreferenced"):
            closure.build_corpus_semantic_namespace(
                pins=world["semantic_pins"]
                + [_pin("orphan-fact", "corpus-semantic", orphan)],
                providers=world["semantic_providers"]
                + [_provider("orphan-fact", orphan)],
                root_entry_ids=world["semantic_roots"],
            )

        ambiguous_aliases = copy.deepcopy(world["semantic_pins"])
        ambiguous_aliases[1]["binding_aliases"].append("route-body")
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError, "binding alias.*ambiguous"
        ):
            closure.build_corpus_semantic_namespace(
                pins=ambiguous_aliases,
                providers=world["semantic_providers"],
                root_entry_ids=world["semantic_roots"],
            )

        excessive_aliases = copy.deepcopy(world["semantic_pins"])
        excessive_aliases[0]["binding_aliases"] = [
            "route-body",
            *[
                f"route-alias-{index:03d}"
                for index in range(closure.MAX_BINDING_ALIASES_PER_ENTRY)
            ],
        ]
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError, "binding_aliases exceeds"
        ):
            closure.build_corpus_semantic_namespace(
                pins=excessive_aliases,
                providers=world["semantic_providers"],
                root_entry_ids=world["semantic_roots"],
            )

        reserved_alias = copy.deepcopy(world["semantic_pins"])
        reserved_alias[0]["binding_aliases"].append("corpus-input-closure")
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError, "reserved anchor"
        ):
            closure.build_corpus_semantic_namespace(
                pins=reserved_alias,
                providers=world["semantic_providers"],
                root_entry_ids=world["semantic_roots"],
            )

    def test_cycles_undeclared_hashes_and_closure_back_bindings_fail_closed(self):
        world = _world()
        cyclic = copy.deepcopy(world["semantic_pins"])
        cyclic[0]["dependency_ids"] = ["source-shard-p01"]
        with self.assertRaisesRegex(closure.PersonaV2InputClosureError, "cycle"):
            closure.build_corpus_semantic_namespace(
                pins=cyclic,
                providers=world["semantic_providers"],
                root_entry_ids=world["semantic_roots"],
            )

        leaf_b = _body(
            schema="kio.persona.pc-fact-graph/v2",
            kind="persona-pc-v2-fact-graph",
            payload={"leaf": "b"},
        )
        pin_b = _pin("leaf-b", "corpus-semantic", leaf_b)
        leaf_a = _body(
            schema="kio.persona.pc-source-profile-catalog/v2",
            kind="persona-pc-v2-source-profile-catalog",
            payload={"hidden_downstream_sha256": pin_b["sha256"]},
        )
        pin_a = _pin("leaf-a", "corpus-semantic", leaf_a)
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError, "unclassified SHA-256 field"
        ):
            closure.build_corpus_semantic_namespace(
                pins=[pin_a, pin_b],
                providers=[_provider("leaf-a", leaf_a), _provider("leaf-b", leaf_b)],
                root_entry_ids=["leaf-a", "leaf-b"],
            )

        missing_variant = _body(
            schema="kio.persona.pc-source-intent-origin-shard/v2",
            kind="persona-pc-v2-source-intent-origin-shard",
            payload={"intent_key": "p01-intent-pilot-syn-0001"},
            dependencies=(("variant-catalog", "f" * 64),),
        )
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError,
            "dependency SHA.*no known pin|dependency SHA.*no known internal or external pin",
        ):
            closure.build_corpus_semantic_namespace(
                pins=[
                    _pin(
                        "source-with-missing-variant",
                        "corpus-semantic",
                        missing_variant,
                    )
                ],
                providers=[
                    _provider("source-with-missing-variant", missing_variant)
                ],
                root_entry_ids=["source-with-missing-variant"],
            )

        envelope_body = _body(
            schema="kio.persona.pc-envelope/v2",
            kind="persona-pc-v2-envelope",
            payload={"value": "envelope"},
        )
        topology_body = _body(
            schema="kio.persona.pc-topology/v2",
            kind="persona-pc-v2-topology",
            payload={"value": "topology"},
        )
        envelope_pin = _pin("envelope", "corpus-semantic", envelope_body)
        topology_pin = _pin("topology", "corpus-semantic", topology_body)
        explicit_owner_mismatch = _body(
            schema="kio.persona.pc-route-affinity/v2",
            kind="persona-pc-v2-route-affinity-matrix",
            payload={"value": "bad-explicit-bindings"},
        )
        explicit_owner_mismatch["envelope_contract_sha256"] = envelope_pin[
            "sha256"
        ]
        explicit_owner_mismatch["topology_contract_sha256"] = envelope_pin[
            "sha256"
        ]
        explicit_owner_pin = _pin(
            "bad-route-affinity",
            "corpus-semantic",
            explicit_owner_mismatch,
            ("envelope", "topology"),
        )
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError,
            "explicit dependency field.*must bind 'topology'.*not 'envelope'",
        ):
            closure.build_corpus_semantic_namespace(
                pins=[envelope_pin, topology_pin, explicit_owner_pin],
                providers=[
                    _provider("envelope", envelope_body),
                    _provider("topology", topology_body),
                    _provider("bad-route-affinity", explicit_owner_mismatch),
                ],
                root_entry_ids=["bad-route-affinity"],
            )

        spoofed_topology = _body(
            schema="kio.persona.pc-fact-graph/v2",
            kind="persona-pc-v2-fact-graph",
            payload={"value": "not-topology"},
        )
        spoofed_topology_pin = _pin(
            "topology", "corpus-semantic", spoofed_topology
        )
        spoofed_owner_route = _body(
            schema="kio.persona.pc-route-affinity/v2",
            kind="persona-pc-v2-route-affinity-matrix",
            payload={"value": "spoofed-owner"},
        )
        spoofed_owner_route["topology_contract_sha256"] = (
            spoofed_topology_pin["sha256"]
        )
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError,
            "wrong artifact schema/kind identity",
        ):
            closure.build_corpus_semantic_namespace(
                pins=[
                    spoofed_topology_pin,
                    _pin(
                        "spoofed-owner-route",
                        "corpus-semantic",
                        spoofed_owner_route,
                        ("topology",),
                    ),
                ],
                providers=[
                    _provider("topology", spoofed_topology),
                    _provider("spoofed-owner-route", spoofed_owner_route),
                ],
                root_entry_ids=["spoofed-owner-route"],
            )

        malformed_dependency = _body(
            schema="kio.persona.pc-source-profile-catalog/v2",
            kind="persona-pc-v2-source-profile-catalog",
            payload={"value": "x"},
        )
        malformed_dependency["input_bindings"] = [
            {"entry_id": "missing-body", "sha256": "not-a-sha"}
        ]
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError, "must be exact lowercase SHA-256"
        ):
            closure.build_corpus_semantic_namespace(
                pins=[
                    _pin(
                        "malformed-dependency",
                        "corpus-semantic",
                        malformed_dependency,
                    )
                ],
                providers=[
                    _provider("malformed-dependency", malformed_dependency)
                ],
                root_entry_ids=["malformed-dependency"],
            )

        malformed_collections = (
            [{"entry_id": "missing-body"}],
            ["garbage"],
            [{}],
            {"missing-body": {"entry_id": "missing-body"}},
            "garbage",
            7,
        )
        for input_bindings in malformed_collections:
            malformed_collection = _body(
                schema="kio.persona.pc-source-profile-catalog/v2",
                kind="persona-pc-v2-source-profile-catalog",
                payload={"value": "x"},
            )
            malformed_collection["input_bindings"] = input_bindings
            with self.subTest(input_bindings=input_bindings):
                with self.assertRaisesRegex(
                    closure.PersonaV2InputClosureError, "input_bindings"
                ):
                    closure.build_corpus_semantic_namespace(
                        pins=[
                            _pin(
                                "malformed-collection",
                                "corpus-semantic",
                                malformed_collection,
                            )
                        ],
                        providers=[
                            _provider(
                                "malformed-collection", malformed_collection
                            )
                        ],
                        root_entry_ids=["malformed-collection"],
                    )

        novel_sha_field = _body(
            schema="kio.persona.pc-source-profile-catalog/v2",
            kind="persona-pc-v2-source-profile-catalog",
            payload={"new_contract_sha256": "e" * 64},
        )
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError,
            "unclassified SHA-256 field.*new_contract_sha256",
        ):
            closure.build_corpus_semantic_namespace(
                pins=[
                    _pin(
                        "novel-sha-field",
                        "corpus-semantic",
                        novel_sha_field,
                    )
                ],
                providers=[_provider("novel-sha-field", novel_sha_field)],
                root_entry_ids=["novel-sha-field"],
            )

        for digest_key in (
            "dependency_digest",
            "closure_manifest_digest",
            "dependency_hash",
            "opaque",
        ):
            digest_field = _body(
                schema="kio.persona.pc-source-profile-catalog/v2",
                kind="persona-pc-v2-source-profile-catalog",
                payload={digest_key: "d" * 64},
            )
            with self.subTest(digest_key=digest_key):
                with self.assertRaisesRegex(
                    closure.PersonaV2InputClosureError,
                    "unclassified.*digest|closure/back-binding",
                ):
                    closure.build_corpus_semantic_namespace(
                        pins=[
                            _pin(
                                "digest-field",
                                "corpus-semantic",
                                digest_field,
                            )
                        ],
                        providers=[_provider("digest-field", digest_field)],
                        root_entry_ids=["digest-field"],
                    )

        digest_key_body = _body(
            schema="kio.persona.pc-source-profile-catalog/v2",
            kind="persona-pc-v2-source-profile-catalog",
            payload={"d" * 64: "value"},
        )
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError, "digest as an object key"
        ):
            closure.build_corpus_semantic_namespace(
                pins=[_pin("digest-key", "corpus-semantic", digest_key_body)],
                providers=[_provider("digest-key", digest_key_body)],
                root_entry_ids=["digest-key"],
            )

        for artifact_digest in ("A" * 64, "aA" * 32):
            opaque_case_variant = _body(
                schema="kio.persona.pc-source-profile-catalog/v2",
                kind="persona-pc-v2-source-profile-catalog",
                payload={"opaque": artifact_digest},
            )
            with self.subTest(opaque_case_variant=artifact_digest[:2]):
                with self.assertRaisesRegex(
                    closure.PersonaV2InputClosureError,
                    "unclassified artifact-looking digest",
                ):
                    closure.build_corpus_semantic_namespace(
                        pins=[
                            _pin(
                                "opaque-case-variant",
                                "corpus-semantic",
                                opaque_case_variant,
                            )
                        ],
                        providers=[
                            _provider(
                                "opaque-case-variant", opaque_case_variant
                            )
                        ],
                        root_entry_ids=["opaque-case-variant"],
                    )

            key_case_variant = _body(
                schema="kio.persona.pc-source-profile-catalog/v2",
                kind="persona-pc-v2-source-profile-catalog",
                payload={artifact_digest: "value"},
            )
            with self.subTest(key_case_variant=artifact_digest[:2]):
                with self.assertRaisesRegex(
                    closure.PersonaV2InputClosureError,
                    "digest as an object key",
                ):
                    closure.build_corpus_semantic_namespace(
                        pins=[
                            _pin(
                                "key-case-variant",
                                "corpus-semantic",
                                key_case_variant,
                            )
                        ],
                        providers=[
                            _provider("key-case-variant", key_case_variant)
                        ],
                        root_entry_ids=["key-case-variant"],
                    )

        back_binding = _body(
            schema="kio.persona.pc-source-profile-catalog/v2",
            kind="persona-pc-v2-source-profile-catalog",
            payload={"value": "x"},
        )
        back_binding["input_closure_manifest_sha256"] = "0" * 64
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError,
            "closure hash field|closure/back-binding",
        ):
            closure.build_corpus_semantic_namespace(
                pins=[_pin("back-binding", "corpus-semantic", back_binding)],
                providers=[_provider("back-binding", back_binding)],
                root_entry_ids=["back-binding"],
            )

        digest_back_binding = _body(
            schema="kio.persona.pc-source-profile-catalog/v2",
            kind="persona-pc-v2-source-profile-catalog",
            payload={"corpus_input_closure_digest": "0" * 64},
        )
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError, "closure/back-binding"
        ):
            closure.build_corpus_semantic_namespace(
                pins=[
                    _pin(
                        "digest-back-binding",
                        "corpus-semantic",
                        digest_back_binding,
                    )
                ],
                providers=[
                    _provider("digest-back-binding", digest_back_binding)
                ],
                root_entry_ids=["digest-back-binding"],
            )

        duplicate_nested_binding = copy.deepcopy(
            world["semantic_providers"][1]["body"]
        )
        duplicate_nested_binding["payload"]["nested"] = {
            "input_bindings": [
                copy.deepcopy(duplicate_nested_binding["input_bindings"][0])
            ]
        }
        duplicate_nested_pin = _pin(
            "source-shard-p01",
            "corpus-semantic",
            duplicate_nested_binding,
            ("route-body",),
        )
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError, "input bindings repeat SHA"
        ):
            closure.build_corpus_semantic_namespace(
                pins=[world["semantic_pins"][0], duplicate_nested_pin],
                providers=[
                    world["semantic_providers"][0],
                    _provider("source-shard-p01", duplicate_nested_binding),
                ],
                root_entry_ids=world["semantic_roots"],
            )

        opaque_known_digest = copy.deepcopy(
            world["semantic_providers"][1]["body"]
        )
        opaque_known_digest["payload"]["opaque"] = world["semantic_pins"][0][
            "sha256"
        ]
        opaque_known_pin = _pin(
            "source-shard-p01",
            "corpus-semantic",
            opaque_known_digest,
            ("route-body",),
        )
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError,
            "unclassified artifact-looking digest",
        ):
            closure.build_corpus_semantic_namespace(
                pins=[world["semantic_pins"][0], opaque_known_pin],
                providers=[
                    world["semantic_providers"][0],
                    _provider("source-shard-p01", opaque_known_digest),
                ],
                root_entry_ids=world["semantic_roots"],
            )

        shadow_binding = copy.deepcopy(world["semantic_providers"][1]["body"])
        shadow_binding["input_bindings"][0]["shadow"] = {
            "entry_id": "evil",
            "sha256": world["semantic_pins"][0]["sha256"],
        }
        shadow_pin = _pin(
            "source-shard-p01",
            "corpus-semantic",
            shadow_binding,
            ("route-body",),
        )
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError,
            "input bindings repeat SHA|does not match SHA owner",
        ):
            closure.build_corpus_semantic_namespace(
                pins=[world["semantic_pins"][0], shadow_pin],
                providers=[
                    world["semantic_providers"][0],
                    _provider("source-shard-p01", shadow_binding),
                ],
                root_entry_ids=world["semantic_roots"],
            )

        mismatched_binding_name = copy.deepcopy(
            world["semantic_providers"][1]["body"]
        )
        mismatched_binding_name["input_bindings"][0]["entry_id"] = "unknown-name"
        mismatched_binding_pin = _pin(
            "source-shard-p01",
            "corpus-semantic",
            mismatched_binding_name,
            ("route-body",),
        )
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError, "does not match SHA owner"
        ):
            closure.build_corpus_semantic_namespace(
                pins=[world["semantic_pins"][0], mismatched_binding_pin],
                providers=[
                    world["semantic_providers"][0],
                    _provider("source-shard-p01", mismatched_binding_name),
                ],
                root_entry_ids=world["semantic_roots"],
            )

        contradictory_binding_metadata = {
            "artifact_kind": "persona-pc-v2-not-the-owner",
            "artifact_schema": "kio.persona.pc-not-the-owner/v2",
            "artifact_schema_version": 3,
            "canonical_bytes": 1,
            "fixture_id": "wrong-fixture",
            "fixture_schema_version": 3,
        }
        for field, contradictory_value in contradictory_binding_metadata.items():
            contradictory_binding = copy.deepcopy(
                world["semantic_providers"][1]["body"]
            )
            contradictory_binding["input_bindings"][0][field] = (
                contradictory_value
            )
            contradictory_pin = _pin(
                "source-shard-p01",
                "corpus-semantic",
                contradictory_binding,
                ("route-body",),
            )
            with self.subTest(contradictory_binding_metadata=field):
                with self.assertRaisesRegex(
                    closure.PersonaV2InputClosureError,
                    f"input binding {field} contradicts exact SHA owner",
                ):
                    closure.build_corpus_semantic_namespace(
                        pins=[world["semantic_pins"][0], contradictory_pin],
                        providers=[
                            world["semantic_providers"][0],
                            _provider(
                                "source-shard-p01", contradictory_binding
                            ),
                        ],
                        root_entry_ids=world["semantic_roots"],
                    )

        mismatched_mapping_key = copy.deepcopy(
            world["semantic_providers"][1]["body"]
        )
        mismatched_mapping_key["input_bindings"] = {
            "unknown-name": copy.deepcopy(
                mismatched_mapping_key["input_bindings"][0]
            )
        }
        mismatched_mapping_pin = _pin(
            "source-shard-p01",
            "corpus-semantic",
            mismatched_mapping_key,
            ("route-body",),
        )
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError, "does not match SHA owner"
        ):
            closure.build_corpus_semantic_namespace(
                pins=[world["semantic_pins"][0], mismatched_mapping_pin],
                providers=[
                    world["semantic_providers"][0],
                    _provider("source-shard-p01", mismatched_mapping_key),
                ],
                root_entry_ids=world["semantic_roots"],
            )

        schema_back_binding = _body(
            schema="kio.persona.pc-source-profile-catalog/v2",
            kind="persona-pc-v2-source-profile-catalog",
            payload={"downstream_schema": closure.EVALUATION_INPUT_CLOSURE_SCHEMA},
        )
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError, "closure back-reference"
        ):
            closure.build_corpus_semantic_namespace(
                pins=[_pin("schema-back", "corpus-semantic", schema_back_binding)],
                providers=[_provider("schema-back", schema_back_binding)],
                root_entry_ids=["schema-back"],
            )

    def test_authority_compiled_relevance_and_final_ids_fail_closed(self):
        for mutation in (
            "authority",
            "g0",
            "nested-authority",
            "nonboolean-authority",
            "authorization-alias",
            "authorisation-alias",
            "permission-alias",
            "double-negative-capability",
            "enabled-capability",
            "allows-write",
            "can-solve",
        ):
            body = _body(
                schema="kio.persona.pc-source-profile-catalog/v2",
                kind="persona-pc-v2-source-profile-catalog",
                payload={"value": "x"},
            )
            if mutation == "authority":
                body["authority"]["authorizes_solver_execution"] = True
            elif mutation == "g0":
                body["g0_contract_frozen"] = True
            else:
                if mutation == "nested-authority":
                    body["payload"]["authority"] = {"authorizes_write": True}
                elif mutation == "authorization-alias":
                    body["payload"]["authorization_status"] = "granted"
                elif mutation == "authorisation-alias":
                    body["payload"]["authorisation"] = "granted"
                elif mutation == "permission-alias":
                    body["payload"]["permits_solver_execution"] = True
                elif mutation == "double-negative-capability":
                    body["payload"]["solver_execution_forbidden"] = False
                elif mutation == "enabled-capability":
                    body["payload"]["history_enabled"] = True
                elif mutation == "allows-write":
                    body["payload"]["allows_write"] = True
                elif mutation == "can-solve":
                    body["payload"]["can_solve"] = True
                else:
                    body["payload"]["authorizes_solver_execution"] = "yes"
            with self.assertRaisesRegex(
                closure.PersonaV2InputClosureError,
                "must (all )?(be|remain).*false|unsafe polarity|"
                "not exact allowlisted|exact.*field-name set",
            ):
                closure.build_corpus_semantic_namespace(
                    pins=[_pin("bad-authority", "corpus-semantic", body)],
                    providers=[_provider("bad-authority", body)],
                    root_entry_ids=["bad-authority"],
                )

        for capability_key in ("solver_enabled", "write_enabled", "g0_enabled"):
            body = _body(
                schema="kio.persona.pc-source-profile-catalog/v2",
                kind="persona-pc-v2-source-profile-catalog",
                payload={capability_key: True},
            )
            with self.subTest(capability_key=capability_key):
                with self.assertRaisesRegex(
                    closure.PersonaV2InputClosureError, "unsafe polarity"
                ):
                    closure.build_corpus_semantic_namespace(
                        pins=[_pin("bad-capability", "corpus-semantic", body)],
                        providers=[_provider("bad-capability", body)],
                        root_entry_ids=["bad-capability"],
                    )

        positive_capability_aliases = (
            "solver_execution_permission",
            "solver_execution_capability",
            "solver_execution_access",
            "solver_execution_approved",
            "write_permission",
            "history_mutation_permission",
            "g0_approval",
            "source_plan_permission",
            "solver_active",
            "can_execute",
        )
        for capability_key in positive_capability_aliases:
            body = _body(
                schema="kio.persona.pc-source-profile-catalog/v2",
                kind="persona-pc-v2-source-profile-catalog",
                payload={capability_key: True},
            )
            with self.subTest(positive_capability_alias=capability_key):
                with self.assertRaisesRegex(
                    closure.PersonaV2InputClosureError, "unsafe polarity"
                ):
                    closure.build_corpus_semantic_namespace(
                        pins=[_pin("bad-capability", "corpus-semantic", body)],
                        providers=[_provider("bad-capability", body)],
                        root_entry_ids=["bad-capability"],
                    )

        double_negative_capabilities = {
            "solver_not_enabled": False,
            "solver_unavailable": False,
            "solver_inactive": False,
            "cannot_solve": False,
            "history_not_disabled": True,
        }
        for capability_key, capability_value in double_negative_capabilities.items():
            body = _body(
                schema="kio.persona.pc-source-profile-catalog/v2",
                kind="persona-pc-v2-source-profile-catalog",
                payload={capability_key: capability_value},
            )
            with self.subTest(double_negative_capability=capability_key):
                with self.assertRaisesRegex(
                    closure.PersonaV2InputClosureError, "unsafe polarity"
                ):
                    closure.build_corpus_semantic_namespace(
                        pins=[_pin("bad-capability", "corpus-semantic", body)],
                        providers=[_provider("bad-capability", body)],
                        root_entry_ids=["bad-capability"],
                    )

        split_capability_claims = (
            {"solver": {"enabled": True}},
            {"write": {"permission": True}},
            {"history": {"active": True}},
            {"g0": {"approved": True}},
            {"source_plan": {"enabled": True}},
            {"execution": {"allowed": True}},
            {"solver": {"configuration": {"enabled": True}}},
            {
                "capability": {
                    "type": "solver_execution",
                    "granted": True,
                }
            },
            {"solver": ["enabled"]},
            {
                "permission": {
                    "resource": "physical_write",
                    "allowed": True,
                }
            },
            {"capabilities": ["solver_execution", "physical_write"]},
            {"permissions": ["solver_execution", "physical_write"]},
            {"solver_status": "authorized"},
            {"solver_status": "not_disabled"},
            {"physical_write_status": "not_forbidden"},
            {"source_plan_status": "unblocked"},
            {"g0_freeze_status": "not_prohibited"},
            {"history_mutation_status": "authorized"},
            {"solver_mode": "full-access"},
            {"solver_status": 1},
            {"solver_mode": 1},
            {"solver_status": {"code": 1}},
            {"solver_flag": "yes"},
            {"plan_source_enabled": True},
            {"g_zero_freeze_allowed": True},
            {"physical_file_modification_permitted": True},
            {"filesystem_mutation_allowed": True},
            {"may_persist_files": True},
            {"contract_freeze_permission": True},
        )
        for index, capability_payload in enumerate(split_capability_claims):
            body = _body(
                schema="kio.persona.pc-source-profile-catalog/v2",
                kind="persona-pc-v2-source-profile-catalog",
                payload=capability_payload,
            )
            with self.subTest(split_capability_claim=index):
                with self.assertRaisesRegex(
                    closure.PersonaV2InputClosureError, "unsafe polarity"
                ):
                    closure.build_corpus_semantic_namespace(
                        pins=[_pin("bad-capability", "corpus-semantic", body)],
                        providers=[_provider("bad-capability", body)],
                        root_entry_ids=["bad-capability"],
                    )

        inverted_authority_aliases = (
            "authorization_denied",
            "not_authorized",
            "unauthorized",
            "no_write_authority",
            "authority_absent",
            "non_authoritative",
        )
        for authority_key in inverted_authority_aliases:
            body = _body(
                schema="kio.persona.pc-source-profile-catalog/v2",
                kind="persona-pc-v2-source-profile-catalog",
                payload={authority_key: False},
            )
            with self.subTest(inverted_authority=authority_key):
                with self.assertRaisesRegex(
                    closure.PersonaV2InputClosureError,
                    "not exact allowlisted metadata",
                ):
                    closure.build_corpus_semantic_namespace(
                        pins=[_pin("bad-authority", "corpus-semantic", body)],
                        providers=[_provider("bad-authority", body)],
                        root_entry_ids=["bad-authority"],
                    )

        inside_authority_aliases = (
            "authorization_denied",
            "not_authorized",
            "unauthorized",
            "no_write_authority",
            "authority_absent",
            "non_authoritative",
            "solver_not_enabled",
            "cannot_solve",
        )
        for authority_key in inside_authority_aliases:
            body = _body(
                schema="kio.persona.pc-source-profile-catalog/v2",
                kind="persona-pc-v2-source-profile-catalog",
                payload={"value": "x"},
            )
            body["authority"][authority_key] = False
            with self.subTest(inside_authority=authority_key):
                with self.assertRaisesRegex(
                    closure.PersonaV2InputClosureError,
                    "authority must contain an exact.*field-name set",
                ):
                    closure.build_corpus_semantic_namespace(
                        pins=[_pin("bad-authority", "corpus-semantic", body)],
                        providers=[_provider("bad-authority", body)],
                        root_entry_ids=["bad-authority"],
                    )

        missing_authority_field = _body(
            schema="kio.persona.pc-source-profile-catalog/v2",
            kind="persona-pc-v2-source-profile-catalog",
            payload={"value": "x"},
        )
        del missing_authority_field["authority"]["authorizes_source_plan"]
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError,
            "authority must contain an exact.*field-name set",
        ):
            closure.build_corpus_semantic_namespace(
                pins=[
                    _pin(
                        "bad-authority",
                        "corpus-semantic",
                        missing_authority_field,
                    )
                ],
                providers=[
                    _provider("bad-authority", missing_authority_field)
                ],
                root_entry_ids=["bad-authority"],
            )

        generic_authority_on_known_schema = _body(
            schema="kio.persona.pc-source-profile-catalog/v2",
            kind="persona-pc-v2-source-profile-catalog",
            payload={"value": "x"},
        )
        generic_authority_on_known_schema["authority"] = {
            field: False for field in closure.AUTHORITY_FIELDS
        }
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError,
            "authority must contain an exact.*field-name set",
        ):
            closure.build_corpus_semantic_namespace(
                pins=[
                    _pin(
                        "bad-authority",
                        "corpus-semantic",
                        generic_authority_on_known_schema,
                    )
                ],
                providers=[
                    _provider(
                        "bad-authority", generic_authority_on_known_schema
                    )
                ],
                root_entry_ids=["bad-authority"],
            )

        relocated_capability_metadata = (
            (
                "kio.persona.pc-joint-solver-policy/v2",
                "pre_solve_prohibited_fields",
                ["source_id", "materialization_id"],
            ),
            (
                "kio.persona.pc-source-intent-origin-shard/v2",
                "allowed_history_cohort_ids",
                ["P", "X", "Y"],
            ),
        )
        for schema, capability_key, capability_value in relocated_capability_metadata:
            body = _body(
                schema=schema,
                kind="persona-pc-v2-relocated-capability-metadata",
                payload={"relocated": {capability_key: capability_value}},
            )
            with self.subTest(relocated_capability_metadata=capability_key):
                with self.assertRaisesRegex(
                    closure.PersonaV2InputClosureError, "unsafe polarity"
                ):
                    closure.build_corpus_semantic_namespace(
                        pins=[_pin("relocated-capability", "corpus-semantic", body)],
                        providers=[_provider("relocated-capability", body)],
                        root_entry_ids=["relocated-capability"],
                    )

        exact_execution_mode = _body(
            schema="kio.persona.pc-realism-profile/v2",
            kind="persona-pc-v2-realism-profile",
            payload={"value": "exact-execution-mode"},
        )
        exact_execution_mode["personas"] = [
            {
                "os_execution_mode": (
                    "declared-target-metadata-only-not-native-or-emulated"
                )
            }
        ]
        closure.build_corpus_semantic_namespace(
            pins=[
                _pin(
                    "exact-execution-mode",
                    "corpus-semantic",
                    exact_execution_mode,
                )
            ],
            providers=[
                _provider("exact-execution-mode", exact_execution_mode)
            ],
            root_entry_ids=["exact-execution-mode"],
        )
        drifted_execution_mode = copy.deepcopy(exact_execution_mode)
        drifted_execution_mode["personas"][0]["os_execution_mode"] = "native"
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError, "unsafe polarity"
        ):
            closure.build_corpus_semantic_namespace(
                pins=[
                    _pin(
                        "drifted-execution-mode",
                        "corpus-semantic",
                        drifted_execution_mode,
                    )
                ],
                providers=[
                    _provider(
                        "drifted-execution-mode", drifted_execution_mode
                    )
                ],
                root_entry_ids=["drifted-execution-mode"],
            )

        exact_history_assignment = _body(
            schema="kio.persona.pc-source-intent-origin-shard/v2",
            kind="persona-pc-v2-source-intent-origin-shard",
            payload={"value": "exact-history-assignment"},
        )
        exact_history_assignment["catalogs"] = {
            "quota_contexts": [
                {"history_cohort_assignment_status": "solver-unassigned"}
            ]
        }
        closure.build_corpus_semantic_namespace(
            pins=[
                _pin(
                    "exact-history-assignment",
                    "corpus-semantic",
                    exact_history_assignment,
                )
            ],
            providers=[
                _provider(
                    "exact-history-assignment", exact_history_assignment
                )
            ],
            root_entry_ids=["exact-history-assignment"],
        )
        drifted_history_assignment = copy.deepcopy(exact_history_assignment)
        drifted_history_assignment["catalogs"]["quota_contexts"][0][
            "history_cohort_assignment_status"
        ] = "solver-assigned"
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError, "unsafe polarity"
        ):
            closure.build_corpus_semantic_namespace(
                pins=[
                    _pin(
                        "drifted-history-assignment",
                        "corpus-semantic",
                        drifted_history_assignment,
                    )
                ],
                providers=[
                    _provider(
                        "drifted-history-assignment",
                        drifted_history_assignment,
                    )
                ],
                root_entry_ids=["drifted-history-assignment"],
            )

        subtree_body = _body(
            schema="kio.persona.pc-source-profile-catalog/v2",
            kind="persona-pc-v2-source-profile-catalog",
            payload={
                "history_cohort_templates": [
                    {
                        "required_event_template_keys": [
                            "history-template-w1-typed-small-edit-v1"
                        ]
                    }
                ]
            },
        )
        subtree_path = (
            "kio.persona.pc-source-profile-catalog/v2",
            ("payload", "history_cohort_templates"),
        )
        subtree_raw = _canonicalize(
            subtree_body["payload"]["history_cohort_templates"]
        )
        closure._EXACT_CAPABILITY_SUBTREE_PINS[subtree_path] = (
            len(subtree_raw),
            hashlib.sha256(subtree_raw).hexdigest(),
        )
        try:
            closure.build_corpus_semantic_namespace(
                pins=[
                    _pin("subtree-body", "corpus-semantic", subtree_body)
                ],
                providers=[_provider("subtree-body", subtree_body)],
                root_entry_ids=["subtree-body"],
            )
            tampered_subtree = copy.deepcopy(subtree_body)
            tampered_subtree["payload"]["history_cohort_templates"].append(
                {"solver": {"enabled": True}}
            )
            with self.assertRaisesRegex(
                closure.PersonaV2InputClosureError,
                "exact capability subtree canonical bytes/SHA pin drifted",
            ):
                closure.build_corpus_semantic_namespace(
                    pins=[
                        _pin(
                            "tampered-subtree",
                            "corpus-semantic",
                            tampered_subtree,
                        )
                    ],
                    providers=[
                        _provider("tampered-subtree", tampered_subtree)
                    ],
                    root_entry_ids=["tampered-subtree"],
                )
        finally:
            del closure._EXACT_CAPABILITY_SUBTREE_PINS[subtree_path]

        solver_metadata = _body(
            schema="kio.persona.pc-joint-solver-policy/v2",
            kind="persona-pc-v2-joint-solver-policy",
            payload={
                "authority_exact_false_fields": [
                    "authorizes_g0_freeze",
                    "unexpected-authority-field",
                ]
            },
        )
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError, "authority-like claim"
        ):
            closure.build_corpus_semantic_namespace(
                pins=[
                    _pin("solver-metadata", "corpus-semantic", solver_metadata)
                ],
                providers=[_provider("solver-metadata", solver_metadata)],
                root_entry_ids=["solver-metadata"],
            )

        identity_boundary = _body(
            schema="kio.persona.pc-joint-solver-policy/v2",
            kind="persona-pc-v2-joint-solver-policy",
            payload={
                "final_identity_derivation": (
                    "source_id and materialization_id are derived only after exact "
                    "aggregate-and-intent assignment succeeds"
                )
            },
        )
        closure.build_corpus_semantic_namespace(
            pins=[
                _pin("identity-boundary", "corpus-semantic", identity_boundary)
            ],
            providers=[_provider("identity-boundary", identity_boundary)],
            root_entry_ids=["identity-boundary"],
        )
        drifted_identity_boundary = copy.deepcopy(identity_boundary)
        drifted_identity_boundary["payload"]["final_identity_derivation"] += " drift"
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError, "final identity data field"
        ):
            closure.build_corpus_semantic_namespace(
                pins=[
                    _pin(
                        "identity-boundary",
                        "corpus-semantic",
                        drifted_identity_boundary,
                    )
                ],
                providers=[
                    _provider("identity-boundary", drifted_identity_boundary)
                ],
                root_entry_ids=["identity-boundary"],
            )

        world = _world()
        query_pin = world["evaluation_pins"][0]
        source_pin = world["semantic_pins"][1]
        semantic_oracle_dependencies = (
            ("query-p01", query_pin["sha256"]),
            ("source-shard-p01", source_pin["sha256"]),
        )
        relational_oracle = _body(
            schema="kio.persona.pc-semantic-oracle/v2",
            kind="persona-pc-v2-semantic-oracle",
            payload={"value": "relational-history-template-check"},
            dependencies=semantic_oracle_dependencies,
        )
        relational_oracle["persona_id"] = "p01"
        relational_oracle["positive_oracle_rows"] = [
            {
                "evidence_contract": {
                    "history_event_template_key": (
                        "history-event-template-p01-m3-2-old-wording-01-"
                        "typed-revision"
                    )
                },
                "query_intent_key": "query-p01-m3-2-old-wording-01",
                "scenario_id": "M3-2",
                "stratum_id": "old-wording",
            },
            {
                "evidence_contract": {
                    "history_event_template_key": (
                        "history-event-template-p01-m3-2-rename-move-01-"
                        "same-scope-rename"
                    )
                },
                "query_intent_key": "query-p01-m3-2-rename-move-01",
                "scenario_id": "M3-2",
                "stratum_id": "rename-move",
            },
            {
                "evidence_contract": {
                    "history_event_template_key": (
                        "history-event-template-p01-m3-2-rename-move-02-"
                        "searchable-cross-scope-move"
                    )
                },
                "query_intent_key": "query-p01-m3-2-rename-move-02",
                "scenario_id": "M3-2",
                "stratum_id": "rename-move",
            },
            {
                "evidence_contract": {
                    "history_event_template_key": (
                        "history-event-template-p01-m3-2-"
                        "locale-language-history-07-typed-revision"
                    )
                },
                "query_intent_key": (
                    "query-p01-m3-2-locale-language-history-07"
                ),
                "scenario_id": "M3-2",
                "stratum_id": "locale-language-history",
            },
            {
                "evidence_contract": {
                    "history_event_template_key": (
                        "history-event-template-p01-m3-3-"
                        "locale-language-lifecycle-10-archive"
                    )
                },
                "query_intent_key": (
                    "query-p01-m3-3-locale-language-lifecycle-10"
                ),
                "scenario_id": "M3-3",
                "stratum_id": "locale-language-lifecycle",
            },
        ]

        def build_relational_oracle(body):
            oracle_pin = _pin(
                "oracle-p01",
                "evaluation",
                body,
                ("query-p01", "source-shard-p01"),
            )
            return closure.build_evaluation_input_closure(
                corpus_input_closure=world["corpus"],
                corpus_input_closure_pin=world["corpus_pin"],
                evaluation_pins=[query_pin, oracle_pin],
                evaluation_providers=[
                    world["evaluation_providers"][0],
                    _provider("oracle-p01", body),
                ],
                evaluation_root_entry_ids=["oracle-p01"],
                semantic_namespace=world["semantic"],
            )

        build_relational_oracle(relational_oracle)
        relational_drifts = []
        query_key_drift = copy.deepcopy(relational_oracle)
        query_key_drift["positive_oracle_rows"][0]["query_intent_key"] = (
            "query-p01-m3-2-old-wording-02"
        )
        relational_drifts.append(query_key_drift)
        ordinal_drift = copy.deepcopy(relational_oracle)
        ordinal_drift["positive_oracle_rows"][0]["query_intent_key"] = (
            "query-p01-m3-2-old-wording-11"
        )
        ordinal_drift["positive_oracle_rows"][0]["evidence_contract"][
            "history_event_template_key"
        ] = "history-event-template-p01-m3-2-old-wording-11-typed-revision"
        relational_drifts.append(ordinal_drift)
        operation_drift = copy.deepcopy(relational_oracle)
        operation_drift["positive_oracle_rows"][1]["evidence_contract"][
            "history_event_template_key"
        ] = (
            "history-event-template-p01-m3-2-rename-move-01-"
            "searchable-cross-scope-move"
        )
        relational_drifts.append(operation_drift)
        for index, drifted_oracle in enumerate(relational_drifts):
            with self.subTest(semantic_oracle_relational_drift=index):
                with self.assertRaisesRegex(
                    closure.PersonaV2InputClosureError, "unsafe polarity"
                ):
                    build_relational_oracle(drifted_oracle)

        receipt_metadata = _body(
            schema="kio.persona.pc-review-evidence/v2",
            kind="persona-pc-v2-review-evidence",
            payload={"review": "negative"},
        )
        receipt_metadata["authoritative_review_blockers"] = [
            "arbitrary-unpinned-blocker"
        ]
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError, "authority-like claim"
        ):
            closure.build_corpus_input_closure(
                semantic_namespace=world["semantic"],
                semantic_pins=world["semantic_pins"],
                semantic_providers=world["semantic_providers"],
                semantic_root_entry_ids=world["semantic_roots"],
                evidence_pins=[
                    _pin("receipt-metadata", "evidence", receipt_metadata)
                ],
                evidence_providers=[
                    _provider("receipt-metadata", receipt_metadata)
                ],
                evidence_root_entry_ids=["receipt-metadata"],
            )

        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError, "formal_relevance_compiled.*false"
        ):
            _world(formal_compiled=True)
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError,
            "prohibited pre-solve identifier|final identity data field",
        ):
            _world(oracle_final_id=True)
        final_ids = copy.deepcopy(world["semantic_providers"][0]["body"])
        final_ids["payload"]["final_source_ids"] = ["source-final-001"]
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError, "final identity data field"
        ):
            closure.build_corpus_semantic_namespace(
                pins=[_pin("route-body", "corpus-semantic", final_ids)],
                providers=[_provider("route-body", final_ids)],
                root_entry_ids=["route-body"],
            )

        compiled_query = copy.deepcopy(world["evaluation_providers"][0]["body"])
        compiled_query["payload"]["compiled_relevance"] = {
            "raw-hash": ["section-1"]
        }
        compiled_query_pin = _pin(
            "query-p01",
            "evaluation",
            compiled_query,
            ("source-shard-p01",),
        )
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError, "compiled relevance data field"
        ):
            closure.build_evaluation_input_closure(
                corpus_input_closure=world["corpus"],
                corpus_input_closure_pin=world["corpus_pin"],
                evaluation_pins=[compiled_query_pin],
                evaluation_providers=[_provider("query-p01", compiled_query)],
                evaluation_root_entry_ids=["query-p01"],
                semantic_namespace=world["semantic"],
            )

        bad_query = copy.deepcopy(world["evaluation_providers"][0]["body"])
        bad_query["payload"]["query_text"] = "rendered text is downstream"
        bad_query_pin = _pin(
            "query-p01",
            "evaluation",
            bad_query,
            ("source-shard-p01",),
        )
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError,
            "prohibited evaluation input field 'query_text'",
        ):
            closure.build_evaluation_input_closure(
                corpus_input_closure=world["corpus"],
                corpus_input_closure_pin=world["corpus_pin"],
                evaluation_pins=[bad_query_pin],
                evaluation_providers=[_provider("query-p01", bad_query)],
                evaluation_root_entry_ids=["query-p01"],
                semantic_namespace=world["semantic"],
            )
        for forbidden_key in ("query_text", "answer", "distractors"):
            leaky_corpus_body = _body(
                schema="kio.persona.pc-source-profile-catalog/v2",
                kind="persona-pc-v2-source-profile-catalog",
                payload={forbidden_key: "evaluation-only-semantics"},
            )
            with self.subTest(corpus_forbidden_key=forbidden_key):
                with self.assertRaisesRegex(
                    closure.PersonaV2InputClosureError,
                    "prohibited corpus-side query/oracle semantic field",
                ):
                    closure.build_corpus_semantic_namespace(
                        pins=[
                            _pin(
                                "leaky-corpus-body",
                                "corpus-semantic",
                                leaky_corpus_body,
                            )
                        ],
                        providers=[
                            _provider("leaky-corpus-body", leaky_corpus_body)
                        ],
                        root_entry_ids=["leaky-corpus-body"],
                    )

        leaky_receipt = copy.deepcopy(world["evidence_providers"][0]["body"])
        leaky_receipt["payload"]["query_texts"] = ["secret rendered query"]
        leaky_receipt_pin = _pin(
            "route-review-receipt",
            "evidence",
            leaky_receipt,
            ("route-body",),
        )
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError,
            "prohibited corpus-side query/oracle semantic field",
        ):
            closure.build_corpus_input_closure(
                semantic_namespace=world["semantic"],
                semantic_pins=world["semantic_pins"],
                semantic_providers=world["semantic_providers"],
                semantic_root_entry_ids=world["semantic_roots"],
                evidence_pins=[leaky_receipt_pin],
                evidence_providers=[
                    _provider("route-review-receipt", leaky_receipt)
                ],
                evidence_root_entry_ids=["route-review-receipt"],
            )
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError, "only a dependency-injected candidate"
        ):
            closure.require_canonical_g0_authority()

    def test_canonical_order_and_trusted_anchor_composition_fail_closed(self):
        body = _body(
            schema="kio.persona.pc-source-profile-catalog/v2",
            kind="persona-pc-v2-source-profile-catalog",
            payload={"z_ready": False, "a_complete": False},
        )
        pin = _pin("ordered-body", "corpus-semantic", body)
        first = closure.build_corpus_semantic_namespace(
            pins=[pin],
            providers=[_provider("ordered-body", body)],
            root_entry_ids=["ordered-body"],
        )
        reordered_body = {
            key: copy.deepcopy(body[key]) for key in reversed(list(body))
        }
        reordered_body["payload"] = {
            key: reordered_body["payload"][key]
            for key in reversed(list(reordered_body["payload"]))
        }
        second = closure.build_corpus_semantic_namespace(
            pins=[pin],
            providers=[_provider("ordered-body", reordered_body)],
            root_entry_ids=["ordered-body"],
        )
        self.assertEqual(
            closure.corpus_semantic_namespace_bytes(first),
            closure.corpus_semantic_namespace_bytes(second),
        )
        self.assertEqual(
            first["input_entries"][0]["propagated_false_status_paths"],
            [
                ["authority", "formal_capacity_gate_satisfied"],
                ["catalog_complete"],
                ["payload", "a_complete"],
                ["payload", "z_ready"],
            ],
        )

        world = _world()
        malformed_corpus = copy.deepcopy(world["corpus"])
        malformed_corpus["evidence_entries"] = []
        malformed_corpus["evidence_entry_count"] = 0
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError,
            "corpus-input-closure anchor differs from its exact trusted pin",
        ):
            closure.build_evaluation_input_closure(
                corpus_input_closure=malformed_corpus,
                corpus_input_closure_pin=world["corpus_pin"],
                evaluation_pins=world["evaluation_pins"],
                evaluation_providers=world["evaluation_providers"],
                evaluation_root_entry_ids=world["evaluation_roots"],
                semantic_namespace=world["semantic"],
            )

        malformed_evaluation = copy.deepcopy(world["evaluation"])
        malformed_evaluation["evaluation_entries"] = []
        malformed_evaluation["evaluation_entry_count"] = 0
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError,
            "evaluation-input-closure anchor differs from its exact trusted pin",
        ):
            closure.build_suite_input_descriptor(
                corpus_input_closure=world["corpus"],
                corpus_input_closure_pin=world["corpus_pin"],
                evaluation_input_closure=malformed_evaluation,
                evaluation_input_closure_pin=world["evaluation_pin"],
            )

        invalid_anchor_pin = copy.deepcopy(world["corpus_pin"])
        invalid_anchor_pin["canonical_bytes"] = float(
            invalid_anchor_pin["canonical_bytes"]
        )
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError,
            "expected anchor pin canonical_bytes is invalid",
        ):
            closure.build_evaluation_input_closure(
                corpus_input_closure=world["corpus"],
                corpus_input_closure_pin=invalid_anchor_pin,
                evaluation_pins=world["evaluation_pins"],
                evaluation_providers=world["evaluation_providers"],
                evaluation_root_entry_ids=world["evaluation_roots"],
                semantic_namespace=world["semantic"],
            )

        deep_anchor = copy.deepcopy(world["corpus"])
        nested = {}
        for _ in range(70):
            nested = {"next": nested}
        deep_anchor["unexpected_deep_value"] = nested
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError, "nesting depth"
        ):
            closure.build_evaluation_input_closure(
                corpus_input_closure=deep_anchor,
                corpus_input_closure_pin=world["corpus_pin"],
                evaluation_pins=world["evaluation_pins"],
                evaluation_providers=world["evaluation_providers"],
                evaluation_root_entry_ids=world["evaluation_roots"],
                semantic_namespace=world["semantic"],
            )

    def test_builders_enforce_root_cap_before_return(self):
        body = _body(
            schema="kio.persona.pc-source-profile-catalog/v2",
            kind="persona-pc-v2-source-profile-catalog",
            payload={"value": "x"},
        )
        original_cap = closure.MAX_INPUT_ROOT_BYTES
        closure.MAX_INPUT_ROOT_BYTES = 512
        try:
            with self.assertRaises(closure.PersonaV2InputClosureError):
                closure.build_corpus_semantic_namespace(
                    pins=[_pin("capped-body", "corpus-semantic", body)],
                    providers=[_provider("capped-body", body)],
                    root_entry_ids=["capped-body"],
                )
        finally:
            closure.MAX_INPUT_ROOT_BYTES = original_cap

    def test_exact_mixed_input_binding_metadata_and_aliases(self):
        dependency_ids = [
            "envelope",
            "topology",
            "joint-problem",
            "joint-solver-policy",
            "variant-catalog",
            "id-free-text-renderer",
            "id-free-text-validator",
            "id-free-pdf-text-renderer",
            "id-free-pdf-text-validator",
        ]
        pins = []
        providers = []
        pin_by_id = {}
        for index, entry_id in enumerate(dependency_ids):
            body = _body(
                schema="kio.persona.pc-synthetic-binding-leaf/v2",
                kind="persona-pc-v2-synthetic-binding-leaf",
                payload={"ordinal": index},
            )
            aliases = [entry_id]
            if entry_id in {
                "variant-catalog",
                "id-free-text-renderer",
                "id-free-text-validator",
                "id-free-pdf-text-renderer",
                "id-free-pdf-text-validator",
            }:
                aliases.append(entry_id.replace("-", "_"))
            pin = _pin(
                entry_id,
                "corpus-semantic",
                body,
                binding_aliases=aliases,
            )
            pins.append(pin)
            providers.append(_provider(entry_id, body))
            pin_by_id[entry_id] = pin

        consumer = _body(
            schema="kio.persona.pc-source-profile-catalog/v2",
            kind="persona-pc-v2-source-profile-catalog",
            payload={"value": "mixed-bindings"},
        )
        consumer["input_bindings"] = {
            "binding_order": dependency_ids,
            "id_free_text_renderer": {
                "name": "id-free-text-renderer",
                "sha256": pin_by_id["id-free-text-renderer"]["sha256"],
            },
            "id_free_text_validator": {
                "name": "id-free-text-validator",
                "sha256": pin_by_id["id-free-text-validator"]["sha256"],
            },
            "id_free_pdf_text_renderer": {
                "name": "id-free-pdf-text-renderer",
                "sha256": pin_by_id["id-free-pdf-text-renderer"]["sha256"],
            },
            "id_free_pdf_text_validator": {
                "name": "id-free-pdf-text-validator",
                "sha256": pin_by_id["id-free-pdf-text-validator"]["sha256"],
            },
            "planning_chain": [
                {"name": entry_id, "sha256": pin_by_id[entry_id]["sha256"]}
                for entry_id in dependency_ids[:4]
            ],
            "variant_catalog": {
                "name": "variant-catalog",
                "sha256": pin_by_id["variant-catalog"]["sha256"],
            },
        }
        consumer_pin = _pin(
            "source-profile-catalog",
            "corpus-semantic",
            consumer,
            dependency_ids,
        )
        value = closure.build_corpus_semantic_namespace(
            pins=[*pins, consumer_pin],
            providers=[*providers, _provider("source-profile-catalog", consumer)],
            root_entry_ids=["source-profile-catalog"],
        )
        self.assertEqual(value["entry_count"], 10)

        drifted = copy.deepcopy(consumer)
        drifted["input_bindings"]["binding_order"] = list(
            reversed(dependency_ids)
        )
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError, "input_bindings metadata.*drifted"
        ):
            closure.build_corpus_semantic_namespace(
                pins=[
                    *pins,
                    _pin(
                        "source-profile-catalog",
                        "corpus-semantic",
                        drifted,
                        dependency_ids,
                    ),
                ],
                providers=[
                    *providers,
                    _provider("source-profile-catalog", drifted),
                ],
                root_entry_ids=["source-profile-catalog"],
            )

        metadata_only = copy.deepcopy(consumer)
        metadata_only["input_bindings"] = {
            "binding_order": list(dependency_ids)
        }
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError,
            "binding_order must exactly cover",
        ):
            closure.build_corpus_semantic_namespace(
                pins=[
                    _pin(
                        "source-profile-catalog",
                        "corpus-semantic",
                        metadata_only,
                    )
                ],
                providers=[
                    _provider("source-profile-catalog", metadata_only)
                ],
                root_entry_ids=["source-profile-catalog"],
            )

        partial = copy.deepcopy(consumer)
        del partial["input_bindings"]["variant_catalog"]
        partial_dependency_ids = [
            entry_id for entry_id in dependency_ids if entry_id != "variant-catalog"
        ]
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError,
            "binding_order must exactly cover",
        ):
            closure.build_corpus_semantic_namespace(
                pins=[
                    *[
                        pin
                        for pin in pins
                        if pin["entry_id"] != "variant-catalog"
                    ],
                    _pin(
                        "source-profile-catalog",
                        "corpus-semantic",
                        partial,
                        partial_dependency_ids,
                    ),
                ],
                providers=[
                    *[
                        provider
                        for provider in providers
                        if provider["entry_id"] != "variant-catalog"
                    ],
                    _provider("source-profile-catalog", partial),
                ],
                root_entry_ids=["source-profile-catalog"],
            )

        metadata_in_leaf = copy.deepcopy(consumer)
        metadata_in_leaf["input_bindings"] = {
            "binding_order": list(dependency_ids),
            "entry_id": "envelope",
            "sha256": pin_by_id["envelope"]["sha256"],
        }
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError,
            "metadata cannot be embedded in a binding leaf",
        ):
            closure.build_corpus_semantic_namespace(
                pins=[
                    pin_by_id["envelope"],
                    _pin(
                        "source-profile-catalog",
                        "corpus-semantic",
                        metadata_in_leaf,
                        ("envelope",),
                    ),
                ],
                providers=[
                    next(
                        provider
                        for provider in providers
                        if provider["entry_id"] == "envelope"
                    ),
                    _provider("source-profile-catalog", metadata_in_leaf),
                ],
                root_entry_ids=["source-profile-catalog"],
            )

    def test_long_acyclic_graph_uses_iterative_topological_order(self):
        pins = []
        providers = []
        previous_id = None
        previous_sha256 = None
        for index in range(1_100):
            entry_id = f"chain-{index:04d}"
            dependencies = ()
            dependency_ids = ()
            if previous_id is not None:
                dependencies = ((previous_id, previous_sha256),)
                dependency_ids = (previous_id,)
            body = _body(
                schema="kio.persona.pc-source-profile-catalog/v2",
                kind="persona-pc-v2-source-profile-catalog",
                payload={"ordinal": index},
                dependencies=dependencies,
            )
            pin = _pin(
                entry_id,
                "corpus-semantic",
                body,
                dependency_ids,
            )
            pins.append(pin)
            providers.append(_provider(entry_id, body))
            previous_id = entry_id
            previous_sha256 = pin["sha256"]

        value = closure.build_corpus_semantic_namespace(
            pins=pins,
            providers=providers,
            root_entry_ids=[previous_id],
        )
        self.assertEqual(value["entry_count"], 1_100)
        self.assertEqual(value["input_entries"][0]["entry_id"], "chain-0000")
        self.assertEqual(value["input_entries"][-1]["entry_id"], "chain-1099")

    def test_route_review_exact_digest_evidence_is_narrowly_allowlisted(self):
        route = _body(
            schema="kio.persona.pc-route-affinity/v2",
            kind="persona-pc-v2-route-affinity-matrix",
            payload={"route": "candidate"},
        )
        route_pin = _pin("route-affinity-body", "corpus-semantic", route)
        semantic = closure.build_corpus_semantic_namespace(
            pins=[route_pin],
            providers=[_provider("route-affinity-body", route)],
            root_entry_ids=["route-affinity-body"],
        )

        def receipt_with_checks(checks):
            receipt = _body(
                schema="kio.persona.pc-route-review-receipt/v2",
                kind="persona-pc-v2-route-review-receipt",
                payload={"review": "negative"},
                dependencies=(("route-affinity-body", route_pin["sha256"]),),
            )
            receipt["reviewed_route_artifact"] = {
                "canonical_body_sha256": route_pin["sha256"]
            }
            receipt["checks"] = checks
            return receipt

        exact_check = {
            "check_id": "exact-route-artifact-binding",
            "expected": route_pin["sha256"],
            "observed": route_pin["sha256"],
            "result": "pass",
        }
        receipt = receipt_with_checks([exact_check])
        closure.build_corpus_input_closure(
            semantic_namespace=semantic,
            semantic_pins=[route_pin],
            semantic_providers=[_provider("route-affinity-body", route)],
            semantic_root_entry_ids=["route-affinity-body"],
            evidence_pins=[
                _pin(
                    "negative-route-review-receipt",
                    "evidence",
                    receipt,
                    ("route-affinity-body",),
                )
            ],
            evidence_providers=[
                _provider("negative-route-review-receipt", receipt)
            ],
            evidence_root_entry_ids=["negative-route-review-receipt"],
        )

        for field, invalid_value in (
            ("expected", "not-a-digest"),
            ("observed", ""),
            ("expected", "x"),
        ):
            drifted_evidence = copy.deepcopy(receipt)
            drifted_evidence["checks"][0][field] = invalid_value
            with self.subTest(field=field, invalid_value=invalid_value):
                with self.assertRaisesRegex(
                    closure.PersonaV2InputClosureError,
                    "exact route-review digest evidence.*must equal",
                ):
                    closure.build_corpus_input_closure(
                        semantic_namespace=semantic,
                        semantic_pins=[route_pin],
                        semantic_providers=[
                            _provider("route-affinity-body", route)
                        ],
                        semantic_root_entry_ids=["route-affinity-body"],
                        evidence_pins=[
                            _pin(
                                "negative-route-review-receipt",
                                "evidence",
                                drifted_evidence,
                                ("route-affinity-body",),
                            )
                        ],
                        evidence_providers=[
                            _provider(
                                "negative-route-review-receipt",
                                drifted_evidence,
                            )
                        ],
                        evidence_root_entry_ids=[
                            "negative-route-review-receipt"
                        ],
                    )

        for structural_mutation in ("empty-checks", "missing-expected", "missing-observed"):
            malformed_evidence = copy.deepcopy(receipt)
            if structural_mutation == "empty-checks":
                malformed_evidence["checks"] = []
            else:
                del malformed_evidence["checks"][0][
                    structural_mutation.removeprefix("missing-")
                ]
            with self.subTest(structural_mutation=structural_mutation):
                with self.assertRaisesRegex(
                    closure.PersonaV2InputClosureError,
                    "route-review digest contract|exact route-review digest evidence",
                ):
                    closure.build_corpus_input_closure(
                        semantic_namespace=semantic,
                        semantic_pins=[route_pin],
                        semantic_providers=[
                            _provider("route-affinity-body", route)
                        ],
                        semantic_root_entry_ids=["route-affinity-body"],
                        evidence_pins=[
                            _pin(
                                "negative-route-review-receipt",
                                "evidence",
                                malformed_evidence,
                                ("route-affinity-body",),
                            )
                        ],
                        evidence_providers=[
                            _provider(
                                "negative-route-review-receipt",
                                malformed_evidence,
                            )
                        ],
                        evidence_root_entry_ids=[
                            "negative-route-review-receipt"
                        ],
                    )

        wrong_check = copy.deepcopy(receipt)
        wrong_check["checks"][0]["check_id"] = "arbitrary-check"
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError,
            "route-review digest contract",
        ):
            closure.build_corpus_input_closure(
                semantic_namespace=semantic,
                semantic_pins=[route_pin],
                semantic_providers=[_provider("route-affinity-body", route)],
                semantic_root_entry_ids=["route-affinity-body"],
                evidence_pins=[
                    _pin(
                        "negative-route-review-receipt",
                        "evidence",
                        wrong_check,
                        ("route-affinity-body",),
                    )
                ],
                evidence_providers=[
                    _provider("negative-route-review-receipt", wrong_check)
                ],
                evidence_root_entry_ids=["negative-route-review-receipt"],
            )

        extra_check = copy.deepcopy(receipt)
        extra_check["checks"].append(
            {
                "check_id": "arbitrary-check",
                "expected": route_pin["sha256"],
                "observed": "not-a-digest",
                "result": "pass",
            }
        )
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError,
            "unclassified artifact-looking digest",
        ):
            closure.build_corpus_input_closure(
                semantic_namespace=semantic,
                semantic_pins=[route_pin],
                semantic_providers=[_provider("route-affinity-body", route)],
                semantic_root_entry_ids=["route-affinity-body"],
                evidence_pins=[
                    _pin(
                        "negative-route-review-receipt",
                        "evidence",
                        extra_check,
                        ("route-affinity-body",),
                    )
                ],
                evidence_providers=[
                    _provider("negative-route-review-receipt", extra_check)
                ],
                evidence_root_entry_ids=["negative-route-review-receipt"],
            )

    def test_input_class_isolation_and_mismatched_roots_fail_closed(self):
        world = _world()
        semantic_as_evidence = copy.deepcopy(world["semantic_pins"])
        semantic_as_evidence[0]["input_class"] = "evidence"
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError, "input_class must be"
        ):
            closure.build_corpus_semantic_namespace(
                pins=semantic_as_evidence,
                providers=world["semantic_providers"],
                root_entry_ids=world["semantic_roots"],
            )

        receipt_as_semantic = copy.deepcopy(world["evidence_pins"])
        receipt_as_semantic[0]["input_class"] = "corpus-semantic"
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError, "not an admissible corpus-semantic"
        ):
            closure.build_corpus_semantic_namespace(
                pins=receipt_as_semantic,
                providers=world["evidence_providers"],
                root_entry_ids=world["evidence_roots"],
            )

        hybrid = _body(
            schema="kio.persona.pc-query-review-receipt/v2",
            kind="persona-pc-v2-query-review-receipt",
            payload={"neutral": "bytes"},
        )
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError,
            "evaluation identity is forbidden in evidence",
        ):
            closure.build_corpus_input_closure(
                semantic_namespace=world["semantic"],
                semantic_pins=world["semantic_pins"],
                semantic_providers=world["semantic_providers"],
                semantic_root_entry_ids=world["semantic_roots"],
                evidence_pins=[_pin("hybrid", "evidence", hybrid)],
                evidence_providers=[_provider("hybrid", hybrid)],
                evidence_root_entry_ids=["hybrid"],
            )
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError,
            "evidence identity is forbidden in evaluation",
        ):
            closure.build_evaluation_input_closure(
                corpus_input_closure=world["corpus"],
                corpus_input_closure_pin=world["corpus_pin"],
                evaluation_pins=[_pin("hybrid", "evaluation", hybrid)],
                evaluation_providers=[_provider("hybrid", hybrid)],
                evaluation_root_entry_ids=["hybrid"],
                semantic_namespace=world["semantic"],
            )

        other = _world(review_value="different-evidence")
        with self.assertRaisesRegex(
            closure.PersonaV2InputClosureError,
            "evaluation closure does not bind the supplied corpus closure",
        ):
            closure.build_suite_input_descriptor(
                corpus_input_closure=other["corpus"],
                corpus_input_closure_pin=other["corpus_pin"],
                evaluation_input_closure=world["evaluation"],
                evaluation_input_closure_pin=world["evaluation_pin"],
            )

    def test_hash_seed_does_not_change_canonical_roots(self):
        script = r'''
import json
from eval.test_persona_v2_input_closure import _world
from eval import persona_v2_input_closure as c
w = _world()
print(json.dumps([
    c.corpus_semantic_namespace_sha256(w["semantic"]),
    c.corpus_input_closure_sha256(w["corpus"]),
    c.evaluation_input_closure_sha256(w["evaluation"]),
    c.suite_input_descriptor_sha256(w["suite"]),
], separators=(",", ":")))
'''
        outputs = []
        for seed in ("1", "7", "31337"):
            env = dict(os.environ)
            env["PYTHONHASHSEED"] = seed
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=os.path.dirname(os.path.dirname(__file__)),
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            outputs.append(json.loads(result.stdout))
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[1], outputs[2])


if __name__ == "__main__":
    unittest.main()
