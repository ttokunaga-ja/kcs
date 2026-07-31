"""Live compatibility of the injected closure with current persona v2 leaves.

The closure implementation itself intentionally imports none of these modules.
This separate integration test makes the current candidate inventory explicit
and proves that no dependency SHA can disappear merely because its provider was
omitted from the injected registry.
"""

import hashlib
import unittest

from eval import persona_v2_contract as envelope
from eval import persona_v2_fact_graph as fact_graph
from eval import persona_v2_fact_membership as fact_membership
from eval import persona_v2_history_intent as history_intent
from eval import persona_v2_input_closure as closure
from eval import persona_v2_joint_problem as joint_problem
from eval import persona_v2_joint_solver_policy as solver_policy
from eval import persona_v2_overlay_contract as overlay
from eval import persona_v2_pdf_text_renderer as pdf_text_renderer
from eval import persona_v2_pdf_text_validator as pdf_text_validator
from eval import persona_v2_query_intent as query_intent
from eval import persona_v2_realism_profile as realism
from eval import persona_v2_route_affinity as route_affinity
from eval import persona_v2_route_review_receipt as route_review
from eval import persona_v2_semantic_oracle as semantic_oracle
from eval import persona_v2_source_intent as source_intent
from eval import persona_v2_source_profile_catalog as source_profile
from eval import persona_v2_text_renderer as text_renderer
from eval import persona_v2_text_validator as text_validator
from eval import persona_v2_topology as topology
from eval import persona_v2_variant_catalog as variant_catalog


PERSONA_ID = "p01"

# Updated only after the complete injected graph below passes.  These are
# candidate-root pins, not G0 or source-identity authority.
EXPECTED_ROOT_IDENTITIES = {
    "corpus": (
        3_496,
        "438bdb4d825d510ac2a8de2b7abd7edfe3446b8a4d93070c6f777c11e2640757",
    ),
    "evaluation": (
        5_032,
        "29e4de812125a0c87fb172e81e6bafa7f4d6908d863b7c7061d4a45b4042ce3d",
    ),
    "semantic": (
        48_210,
        "33a0a720e084d8bd732c7a36f7b0a89d90f79e55d8b5c761124c9e947a20b6d8",
    ),
    "suite": (
        2_609,
        "9217e519a382ff51e10305dc77a6e1b2ce4401f543f159ad190e72fb029a76b8",
    ),
}

_EXPLICIT_DEPENDENCY_SHA_FIELDS = frozenset(
    {
        "canonical_body_sha256",
        "envelope_contract_sha256",
        "joint_problem_sha256",
        "joint_solver_policy_sha256",
        "topology_contract_sha256",
    }
)


def _semantic_inputs():
    return [
        (
            "envelope",
            envelope.build_envelope_contract(),
            envelope.validate_envelope_contract,
            envelope.canonical_json_bytes,
        ),
        (
            "topology",
            topology.build_topology_contract(),
            topology.validate_topology_contract,
            topology.canonical_json_bytes,
        ),
        (
            "joint-problem",
            joint_problem.build_joint_problem(),
            joint_problem.validate_joint_problem,
            joint_problem.canonical_json_bytes,
        ),
        (
            "joint-solver-policy",
            solver_policy.build_joint_solver_policy(),
            solver_policy.validate_joint_solver_policy,
            solver_policy.canonical_json_bytes,
        ),
        (
            "realism-profile",
            realism.build_realism_profile(),
            realism.validate_realism_profile,
            realism.canonical_json_bytes,
        ),
        (
            "variant-catalog",
            variant_catalog.build_variant_catalog(),
            variant_catalog.validate_variant_catalog,
            variant_catalog.canonical_json_bytes,
        ),
        (
            "route-affinity-body",
            route_affinity.build_route_affinity(),
            route_affinity.validate_route_affinity,
            route_affinity.canonical_json_bytes,
        ),
        (
            "id-free-text-renderer",
            text_renderer.build_renderer_contract(),
            text_renderer.validate_renderer_contract,
            text_renderer.canonical_json_bytes,
        ),
        (
            "id-free-text-validator",
            text_validator.build_validator_contract(),
            text_validator.validate_validator_contract,
            text_validator.canonical_json_bytes,
        ),
        (
            "id-free-pdf-text-renderer",
            pdf_text_renderer.build_renderer_contract(),
            pdf_text_renderer.validate_renderer_contract,
            pdf_text_renderer.canonical_json_bytes,
        ),
        (
            "id-free-pdf-text-validator",
            pdf_text_validator.build_validator_contract(),
            pdf_text_validator.validate_validator_contract,
            pdf_text_validator.canonical_json_bytes,
        ),
        (
            "source-profile-catalog",
            source_profile.build_source_profile_catalog(),
            source_profile.validate_source_profile_catalog,
            source_profile.canonical_json_bytes,
        ),
        (
            "overlay-contract",
            overlay.build_overlay_contract(),
            overlay.validate_overlay_contract,
            overlay.canonical_json_bytes,
        ),
        (
            "fact-graph-p01",
            fact_graph.build_fact_graph(PERSONA_ID),
            lambda value: fact_graph.validate_fact_graph(PERSONA_ID, value),
            fact_graph.canonical_json_bytes,
        ),
        (
            "source-intent-p01",
            source_intent.build_source_intent_origin_shard(PERSONA_ID),
            lambda value: source_intent.validate_source_intent_origin_shard(
                PERSONA_ID, value
            ),
            source_intent.canonical_json_bytes,
        ),
        (
            "fact-membership-p01",
            fact_membership.build_fact_membership(PERSONA_ID),
            lambda value: fact_membership.validate_fact_membership(
                PERSONA_ID, value
            ),
            fact_membership.canonical_json_bytes,
        ),
        (
            "history-intent-p01",
            history_intent.build_history_intent(PERSONA_ID),
            lambda value: history_intent.validate_history_intent(
                PERSONA_ID, value
            ),
            history_intent.canonical_json_bytes,
        ),
    ]


def _dependency_digests(value, *, path=()):
    result = []
    if type(value) is list:
        for index, item in enumerate(value):
            result.extend(_dependency_digests(item, path=path + (index,)))
        return result
    if type(value) is not dict:
        return result
    for key, item in value.items():
        child = path + (key,)
        is_binding = key in _EXPLICIT_DEPENDENCY_SHA_FIELDS or (
            key == "sha256" and "input_bindings" in path
        )
        if type(item) is str and len(item) == 64 and all(
            character in "0123456789abcdef" for character in item
        ):
            if is_binding:
                alias = None
                if key == "sha256" and "input_bindings" in path:
                    alias = value.get("entry_id") or value.get("name")
                    if alias is None and path and type(path[-1]) is str:
                        alias = path[-1]
                result.append((child, item, alias))
            elif key == "sha256" or key.endswith("_sha256"):
                raise AssertionError(
                    f"unclassified live SHA-256 field at {child!r}"
                )
        result.extend(_dependency_digests(item, path=child))
    return result


def _inject(items, *, input_class, external_digest_to_id=None):
    if external_digest_to_id is None:
        external_digest_to_id = {}
    local_digest_to_id = {}
    raw_by_id = {}
    for entry_id, body, _validate, canonicalize in items:
        raw = canonicalize(body)
        digest = hashlib.sha256(raw).hexdigest()
        if digest in local_digest_to_id or digest in external_digest_to_id:
            raise AssertionError("duplicate live artifact body digest")
        local_digest_to_id[digest] = entry_id
        raw_by_id[entry_id] = raw
    all_digest_to_id = {**external_digest_to_id, **local_digest_to_id}
    aliases_by_digest = {
        digest: {entry_id} for digest, entry_id in all_digest_to_id.items()
    }
    for _entry_id, body, _validate, _canonicalize in items:
        for path, digest, alias in _dependency_digests(body):
            if digest not in all_digest_to_id:
                raise AssertionError("live dependency digest has no injected body")
            if alias is not None:
                aliases_by_digest[digest].add(alias)
            if (
                len(path) >= 2
                and path[-1] == "sha256"
                and "input_bindings" in path[:-1]
                and type(path[-2]) is str
                and path[-2] != "input_bindings"
            ):
                aliases_by_digest[digest].add(path[-2])
    pins = []
    providers = []
    referenced_local_ids = set()
    for entry_id, body, validate, canonicalize in items:
        dependencies = []
        for path, digest, _alias in _dependency_digests(body):
            if digest not in all_digest_to_id:
                raise AssertionError(
                    f"{entry_id} has unknown live dependency digest at {path!r}"
                )
            dependency_id = all_digest_to_id[digest]
            dependencies.append(dependency_id)
            if dependency_id in local_digest_to_id.values():
                referenced_local_ids.add(dependency_id)
        dependencies = sorted(set(dependencies), key=lambda value: value.encode())
        raw = raw_by_id[entry_id]
        pins.append(
            {
                "artifact_kind": body["artifact_kind"],
                "artifact_schema": body["artifact_schema"],
                "artifact_schema_version": body["artifact_schema_version"],
                "binding_aliases": sorted(
                    aliases_by_digest[hashlib.sha256(raw).hexdigest()]
                ),
                "canonical_bytes": len(raw),
                "dependency_ids": dependencies,
                "entry_id": entry_id,
                "fixture_id": body.get("fixture_id", envelope.FIXTURE_ID),
                "fixture_schema_version": body.get(
                    "fixture_schema_version", envelope.FIXTURE_SCHEMA_VERSION
                ),
                "input_class": input_class,
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
        providers.append(
            {
                "body": body,
                "canonicalize": canonicalize,
                "entry_id": entry_id,
                "validate": validate,
            }
        )
    roots = sorted(
        set(local_digest_to_id.values()) - referenced_local_ids,
        key=lambda value: value.encode(),
    )
    return pins, providers, roots, local_digest_to_id


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


def _build_live_roots():
    semantic_items = _semantic_inputs()
    semantic_pins, semantic_providers, semantic_roots, semantic_digest_ids = _inject(
        semantic_items, input_class="corpus-semantic"
    )
    semantic = closure.build_corpus_semantic_namespace(
        pins=semantic_pins,
        providers=semantic_providers,
        root_entry_ids=semantic_roots,
    )

    receipt = route_review.build_negative_route_review_receipt()
    evidence_pins, evidence_providers, evidence_roots, _ = _inject(
        [
            (
                "negative-route-review-receipt",
                receipt,
                route_review.validate_negative_route_review_receipt,
                route_review.canonical_json_bytes,
            )
        ],
        input_class="evidence",
        external_digest_to_id=semantic_digest_ids,
    )
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

    query = query_intent.build_query_intent(PERSONA_ID)
    oracle = semantic_oracle.build_semantic_oracle(PERSONA_ID)
    evaluation_pins, evaluation_providers, evaluation_roots, _ = _inject(
        [
            (
                "query-intent-p01",
                query,
                lambda value: query_intent.validate_query_intent(
                    PERSONA_ID, value
                ),
                query_intent.canonical_json_bytes,
            ),
            (
                "semantic-oracle-p01",
                oracle,
                lambda value: semantic_oracle.validate_semantic_oracle(
                    PERSONA_ID, value
                ),
                semantic_oracle.canonical_json_bytes,
            ),
        ],
        input_class="evaluation",
        external_digest_to_id=semantic_digest_ids,
    )
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
        "semantic": semantic,
        "semantic_pins": semantic_pins,
        "semantic_providers": semantic_providers,
        "semantic_roots": semantic_roots,
        "suite": suite,
    }


class PersonaV2InputClosureLiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live = _build_live_roots()

    def test_current_candidate_graph_is_exact_and_propagates_blockers(self):
        semantic = self.live["semantic"]
        by_id = {row["entry_id"]: row for row in semantic["input_entries"]}
        self.assertIn(
            "variant-catalog",
            by_id["source-intent-p01"]["dependency_ids"],
        )
        self.assertIn(
            "id-free-pdf-text-renderer",
            by_id["source-profile-catalog"]["dependency_ids"],
        )
        self.assertIn(
            "id-free-pdf-text-validator",
            by_id["source-profile-catalog"]["dependency_ids"],
        )
        self.assertIn(
            "source-intent-p01",
            by_id["fact-membership-p01"]["dependency_ids"],
        )
        self.assertIn(
            "fact-membership-p01",
            by_id["history-intent-p01"]["dependency_ids"],
        )
        self.assertIn(
            ["source_profile_catalog_complete"],
            by_id["source-profile-catalog"]["propagated_false_status_paths"],
        )
        self.assertIn(
            ["completion_claims", "eight_axis_ledger_schema_complete"],
            by_id["overlay-contract"]["propagated_false_status_paths"],
        )
        for root_name, byte_builder, digest_builder in (
            (
                "semantic",
                closure.corpus_semantic_namespace_bytes,
                closure.corpus_semantic_namespace_sha256,
            ),
            (
                "corpus",
                closure.corpus_input_closure_bytes,
                closure.corpus_input_closure_sha256,
            ),
            (
                "evaluation",
                closure.evaluation_input_closure_bytes,
                closure.evaluation_input_closure_sha256,
            ),
            (
                "suite",
                closure.suite_input_descriptor_bytes,
                closure.suite_input_descriptor_sha256,
            ),
        ):
            expected_bytes, expected_sha256 = EXPECTED_ROOT_IDENTITIES[root_name]
            actual = self.live[root_name]
            self.assertEqual(len(byte_builder(actual)), expected_bytes)
            self.assertEqual(digest_builder(actual), expected_sha256)

    def test_omitted_catalog_or_pdf_dependency_is_not_silently_ignored(self):
        for omitted_id in (
            "variant-catalog",
            "id-free-pdf-text-renderer",
            "id-free-pdf-text-validator",
        ):
            with self.subTest(omitted_id=omitted_id):
                pins = []
                for row in self.live["semantic_pins"]:
                    if row["entry_id"] == omitted_id:
                        continue
                    replacement = dict(row)
                    replacement["dependency_ids"] = [
                        dependency_id
                        for dependency_id in row["dependency_ids"]
                        if dependency_id != omitted_id
                    ]
                    pins.append(replacement)
                providers = [
                    provider
                    for provider in self.live["semantic_providers"]
                    if provider["entry_id"] != omitted_id
                ]
                roots = [
                    root_id
                    for root_id in self.live["semantic_roots"]
                    if root_id != omitted_id
                ]
                with self.assertRaisesRegex(
                    closure.PersonaV2InputClosureError,
                    "input dependency SHA has no known pin|dependency SHA.*no known pin",
                ):
                    closure.build_corpus_semantic_namespace(
                        pins=pins,
                        providers=providers,
                        root_entry_ids=roots,
                    )


if __name__ == "__main__":
    unittest.main()
